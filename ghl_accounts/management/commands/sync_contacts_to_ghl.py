from django.core.management.base import BaseCommand
from django.db import transaction
from ghl_accounts.models import ContactSync
from ghl_accounts.services.contacts import (
    get_ghl_auth,
    create_ghl_contact,
    update_ghl_contact,
    build_ghl_contact_payload
)
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
import logging

logger = logging.getLogger(__name__)

# Rate limiting: max 10 requests per second, using 8 concurrent workers
MAX_REQUESTS_PER_SECOND = 10
CONCURRENT_WORKERS = 8

# Rate limiter
class RateLimiter:
    def __init__(self, max_calls_per_second):
        self.max_calls = max_calls_per_second
        self.min_interval = 1.0 / max_calls_per_second
        self.last_called = [0.0] * max_calls_per_second
        self.lock = Lock()
        self.index = 0
    
    def wait(self):
        """Wait if necessary to respect rate limit"""
        with self.lock:
            now = time.time()
            elapsed = now - self.last_called[self.index]
            if elapsed < self.min_interval:
                time.sleep(self.min_interval - elapsed)
            self.last_called[self.index] = time.time()
            self.index = (self.index + 1) % self.max_calls


class Command(BaseCommand):
    help = 'Sync all ContactSync records to GHL contacts with concurrent processing and rate limiting'

    def add_arguments(self, parser):
        parser.add_argument(
            '--workers',
            type=int,
            default=CONCURRENT_WORKERS,
            help=f'Number of concurrent workers (default: {CONCURRENT_WORKERS})',
        )
        parser.add_argument(
            '--source',
            type=str,
            choices=['ephysio', 'ghl', 'all'],
            default='ephysio',
            help='Source of contacts to sync (default: ephysio)',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Dry run mode - show what would be synced without making API calls',
        )

    def handle(self, *args, **options):
        workers = options['workers']
        source_filter = options['source']
        dry_run = options['dry_run']
        
        # Check GHL authentication
        access_token, location_id = get_ghl_auth()
        if not access_token or not location_id:
            self.stdout.write(
                self.style.ERROR('GHL authentication not available. Please authenticate first.')
            )
            return
        
        self.stdout.write(self.style.SUCCESS(f'GHL Location ID: {location_id}'))
        
        # Get contacts to sync
        if source_filter == 'all':
            contacts = ContactSync.objects.all()
        else:
            contacts = ContactSync.objects.filter(source=source_filter)
        
        # Filter out contacts that already have ghl_contact_id (unless we want to update them)
        # For now, we'll sync all contacts, but skip those that already have ghl_contact_id
        contacts_to_sync = contacts.filter(ghl_contact_id__isnull=True)
        already_synced = contacts.filter(ghl_contact_id__isnull=False).count()
        
        total = contacts_to_sync.count()
        
        if total == 0:
            self.stdout.write(
                self.style.WARNING(
                    f'No contacts to sync. {already_synced} contacts already have GHL contact IDs.'
                )
            )
            return
        
        self.stdout.write(self.style.SUCCESS(f'Found {total} contacts to sync'))
        if already_synced > 0:
            self.stdout.write(
                self.style.SUCCESS(f'{already_synced} contacts already synced (skipping)')
            )
        
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN MODE - No API calls will be made'))
            for contact in contacts_to_sync[:10]:  # Show first 10
                payload = build_ghl_contact_payload(contact)
                self.stdout.write(f"Would sync: {contact.first_name} {contact.last_name} - {contact.phone}")
            return
        
        # Rate limiter
        rate_limiter = RateLimiter(MAX_REQUESTS_PER_SECOND)
        
        # Statistics
        stats = {
            'created': 0,
            'updated': 0,
            'errors': 0,
            'skipped': 0
        }
        stats_lock = Lock()
        
        def sync_contact(contact):
            """Sync a single contact to GHL"""
            try:
                rate_limiter.wait()
                
                # If contact already has ghl_contact_id, update it
                if contact.ghl_contact_id:
                    payload = build_ghl_contact_payload(contact)
                    result = update_ghl_contact(contact.ghl_contact_id, payload)
                    
                    if result and not result.get('error'):
                        with stats_lock:
                            stats['updated'] += 1
                        return {'status': 'updated', 'contact': contact, 'ghl_id': contact.ghl_contact_id}
                    else:
                        error_msg = result.get('error', 'Update failed') if isinstance(result, dict) else 'Update failed'
                        with stats_lock:
                            stats['errors'] += 1
                        return {'status': 'error', 'contact': contact, 'error': error_msg}
                
                # Check if contact already exists in GHL by checking ContactSync table
                # If another ContactSync has the same phone/email and ghl_contact_id, use that
                # This helps avoid creating duplicates
                existing_ghl_contact = None
                if contact.phone:
                    existing = ContactSync.objects.filter(
                        phone=contact.phone,
                        ghl_contact_id__isnull=False
                    ).exclude(id=contact.id).first()
                    if existing:
                        existing_ghl_contact = existing.ghl_contact_id
                
                if not existing_ghl_contact and contact.email:
                    existing = ContactSync.objects.filter(
                        email=contact.email,
                        ghl_contact_id__isnull=False
                    ).exclude(id=contact.id).first()
                    if existing:
                        existing_ghl_contact = existing.ghl_contact_id
                
                if existing_ghl_contact:
                    # Update existing contact in GHL
                    payload = build_ghl_contact_payload(contact)
                    result = update_ghl_contact(existing_ghl_contact, payload)
                    
                    if result and not result.get('error'):
                        # Update ContactSync with GHL contact ID
                        contact.ghl_contact_id = existing_ghl_contact
                        contact.save(update_fields=['ghl_contact_id'])
                        
                        with stats_lock:
                            stats['updated'] += 1
                        return {'status': 'updated', 'contact': contact, 'ghl_id': existing_ghl_contact}
                    else:
                        error_msg = result.get('error', 'Update failed') if isinstance(result, dict) else 'Update failed'
                        with stats_lock:
                            stats['errors'] += 1
                        return {'status': 'error', 'contact': contact, 'error': error_msg}
                
                # Create new contact
                payload = build_ghl_contact_payload(contact)
                result = create_ghl_contact(payload)
                
                if result and not result.get('error'):
                    # Extract contact ID from response
                    contact_data = result.get('contact') or result
                    ghl_contact_id = contact_data.get('id') or result.get('id')
                    
                    if ghl_contact_id:
                        # Update ContactSync with GHL contact ID
                        contact.ghl_contact_id = ghl_contact_id
                        contact.save(update_fields=['ghl_contact_id'])
                        
                        with stats_lock:
                            stats['created'] += 1
                        return {'status': 'created', 'contact': contact, 'ghl_id': ghl_contact_id}
                    else:
                        with stats_lock:
                            stats['errors'] += 1
                        return {'status': 'error', 'contact': contact, 'error': 'No ID in response'}
                else:
                    # Check if it's a duplicate error
                    error_msg = result.get('error', '') if isinstance(result, dict) else str(result)
                    error_lower = error_msg.lower()
                    
                    # GHL returns "This location does not allow duplicated contacts" for duplicates
                    if ('duplicate' in error_lower or 
                        'already exists' in error_lower or
                        'does not allow duplicated' in error_lower):
                        # This is a duplicate - contact already exists in GHL
                        # We can't easily find it without a search API, so mark as skipped
                        with stats_lock:
                            stats['skipped'] += 1
                        return {'status': 'skipped', 'contact': contact, 'error': 'Duplicate in GHL'}
                    else:
                        with stats_lock:
                            stats['errors'] += 1
                        return {'status': 'error', 'contact': contact, 'error': error_msg}
                        
            except Exception as e:
                logger.error(f"Error syncing contact {contact.id}: {str(e)}")
                with stats_lock:
                    stats['errors'] += 1
                return {'status': 'error', 'contact': contact, 'error': str(e)}
        
        # Process contacts concurrently
        self.stdout.write(
            self.style.SUCCESS(
                f'Starting sync with {workers} concurrent workers '
                f'(max {MAX_REQUESTS_PER_SECOND} requests/second)...'
            )
        )
        
        start_time = time.time()
        processed = 0
        
        with ThreadPoolExecutor(max_workers=workers) as executor:
            # Submit all tasks
            future_to_contact = {
                executor.submit(sync_contact, contact): contact
                for contact in contacts_to_sync
            }
            
            # Process completed tasks
            for future in as_completed(future_to_contact):
                contact = future_to_contact[future]
                try:
                    result = future.result()
                    processed += 1
                    
                    if processed % 50 == 0:
                        elapsed = time.time() - start_time
                        rate = processed / elapsed if elapsed > 0 else 0
                        self.stdout.write(
                            self.style.SUCCESS(
                                f'Processed {processed}/{total} contacts '
                                f'({rate:.1f} contacts/sec)'
                            )
                        )
                    
                    # Log errors
                    if result['status'] == 'error':
                        self.stdout.write(
                            self.style.ERROR(
                                f"Error syncing {contact.first_name} {contact.last_name}: "
                                f"{result.get('error', 'Unknown error')}"
                            )
                        )
                        
                except Exception as e:
                    logger.error(f"Exception processing contact {contact.id}: {str(e)}")
                    with stats_lock:
                        stats['errors'] += 1
        
        # Final summary
        elapsed = time.time() - start_time
        self.stdout.write(self.style.SUCCESS('\n' + '='*60))
        self.stdout.write(self.style.SUCCESS('Sync Summary:'))
        self.stdout.write(self.style.SUCCESS(f'  Total contacts processed: {total}'))
        self.stdout.write(self.style.SUCCESS(f'  Created in GHL: {stats["created"]}'))
        self.stdout.write(self.style.SUCCESS(f'  Updated in GHL: {stats["updated"]}'))
        self.stdout.write(self.style.SUCCESS(f'  Skipped (duplicates): {stats["skipped"]}'))
        self.stdout.write(self.style.SUCCESS(f'  Errors: {stats["errors"]}'))
        self.stdout.write(self.style.SUCCESS(f'  Time taken: {elapsed:.2f} seconds'))
        self.stdout.write(self.style.SUCCESS(f'  Average rate: {total/elapsed:.2f} contacts/second'))
        self.stdout.write(self.style.SUCCESS('='*60))
