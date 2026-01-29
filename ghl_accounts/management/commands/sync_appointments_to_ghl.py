from django.core.management.base import BaseCommand
from ghl_accounts.models import AppointmentSync
from ghl_accounts.services.appointments import (
    get_ghl_auth,
    create_ghl_appointment,
    build_ghl_appointment_payload
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
    help = 'Sync all AppointmentSync records to GHL appointments with concurrent processing and rate limiting'

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
            help='Source of appointments to sync (default: ephysio)',
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
        
        # Get appointments to sync
        if source_filter == 'all':
            appointments = AppointmentSync.objects.all()
        else:
            appointments = AppointmentSync.objects.filter(source=source_filter)
        
        # Filter appointments that:
        # 1. Don't have ghl_appointment_id yet (not synced to GHL)
        # 2. Have ghl_contact_id (linked to a GHL contact)
        appointments_to_sync = appointments.filter(
            ghl_appointment_id__isnull=True,
            ghl_contact_id__isnull=False
        )
        already_synced = appointments.filter(ghl_appointment_id__isnull=False).count()
        missing_contact = appointments.filter(
            ghl_appointment_id__isnull=True,
            ghl_contact_id__isnull=True
        ).count()
        
        total = appointments_to_sync.count()
        
        if total == 0:
            self.stdout.write(
                self.style.WARNING(
                    f'No appointments to sync. '
                    f'{already_synced} appointments already have GHL appointment IDs. '
                    f'{missing_contact} appointments missing GHL contact link.'
                )
            )
            return
        
        self.stdout.write(self.style.SUCCESS(f'Found {total} appointments to sync'))
        if already_synced > 0:
            self.stdout.write(
                self.style.SUCCESS(f'{already_synced} appointments already synced (skipping)')
            )
        if missing_contact > 0:
            self.stdout.write(
                self.style.WARNING(
                    f'{missing_contact} appointments missing GHL contact link (skipping)'
                )
            )
        
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN MODE - No API calls will be made'))
            for appt in appointments_to_sync[:10]:  # Show first 10
                try:
                    payload = build_ghl_appointment_payload(appt)
                    self.stdout.write(
                        f"Would sync: Appointment #{appt.ephysio_appointment_id} "
                        f"for contact {appt.ghl_contact_id} "
                        f"on {appt.start_time.strftime('%Y-%m-%d %H:%M')}"
                    )
                except Exception as e:
                    self.stdout.write(
                        self.style.ERROR(f"Error building payload for appointment {appt.id}: {str(e)}")
                    )
            return
        
        # Rate limiter
        rate_limiter = RateLimiter(MAX_REQUESTS_PER_SECOND)
        
        # Statistics
        stats = {
            'created': 0,
            'errors': 0,
            'skipped': 0
        }
        stats_lock = Lock()
        
        def sync_appointment(appt):
            """Sync a single appointment to GHL"""
            try:
                rate_limiter.wait()
                
                # Create new appointment
                result = create_ghl_appointment(appt)
                
                if result and not result.get('error'):
                    # Extract appointment ID from response
                    appointment_data = result.get('appointment') or result
                    ghl_appointment_id = appointment_data.get('id') or result.get('id')
                    
                    if ghl_appointment_id:
                        # Update AppointmentSync with GHL appointment ID
                        appt.ghl_appointment_id = ghl_appointment_id
                        appt.save(update_fields=['ghl_appointment_id'])
                        
                        with stats_lock:
                            stats['created'] += 1
                        return {
                            'status': 'created',
                            'appointment': appt,
                            'ghl_id': ghl_appointment_id
                        }
                    else:
                        with stats_lock:
                            stats['errors'] += 1
                        return {
                            'status': 'error',
                            'appointment': appt,
                            'error': 'No ID in response'
                        }
                else:
                    # Check if it's a duplicate or validation error
                    error_msg = result.get('error', '') if isinstance(result, dict) else str(result)
                    error_lower = error_msg.lower()
                    
                    # GHL might return duplicate errors for appointments
                    if ('duplicate' in error_lower or 
                        'already exists' in error_lower or
                        'conflict' in error_lower):
                        # This is a duplicate - appointment already exists in GHL
                        with stats_lock:
                            stats['skipped'] += 1
                        return {
                            'status': 'skipped',
                            'appointment': appt,
                            'error': 'Duplicate in GHL'
                        }
                    else:
                        with stats_lock:
                            stats['errors'] += 1
                        return {
                            'status': 'error',
                            'appointment': appt,
                            'error': error_msg
                        }
                        
            except Exception as e:
                logger.error(f"Error syncing appointment {appt.id}: {str(e)}")
                with stats_lock:
                    stats['errors'] += 1
                return {
                    'status': 'error',
                    'appointment': appt,
                    'error': str(e)
                }
        
        # Process appointments concurrently
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
            future_to_appt = {
                executor.submit(sync_appointment, appt): appt
                for appt in appointments_to_sync
            }
            
            # Process completed tasks
            for future in as_completed(future_to_appt):
                appt = future_to_appt[future]
                try:
                    result = future.result()
                    processed += 1
                    
                    if processed % 50 == 0:
                        elapsed = time.time() - start_time
                        rate = processed / elapsed if elapsed > 0 else 0
                        self.stdout.write(
                            self.style.SUCCESS(
                                f'Processed {processed}/{total} appointments '
                                f'({rate:.1f} appointments/sec)'
                            )
                        )
                    
                    # Log errors
                    if result['status'] == 'error':
                        self.stdout.write(
                            self.style.ERROR(
                                f"Error syncing appointment #{appt.ephysio_appointment_id}: "
                                f"{result.get('error', 'Unknown error')}"
                            )
                        )
                        
                except Exception as e:
                    logger.error(f"Exception processing appointment {appt.id}: {str(e)}")
                    with stats_lock:
                        stats['errors'] += 1
        
        # Final summary
        elapsed = time.time() - start_time
        self.stdout.write(self.style.SUCCESS('\n' + '='*60))
        self.stdout.write(self.style.SUCCESS('Sync Summary:'))
        self.stdout.write(self.style.SUCCESS(f'  Total appointments processed: {total}'))
        self.stdout.write(self.style.SUCCESS(f'  Created in GHL: {stats["created"]}'))
        self.stdout.write(self.style.SUCCESS(f'  Skipped (duplicates): {stats["skipped"]}'))
        self.stdout.write(self.style.SUCCESS(f'  Errors: {stats["errors"]}'))
        self.stdout.write(self.style.SUCCESS(f'  Time taken: {elapsed:.2f} seconds'))
        if elapsed > 0:
            self.stdout.write(
                self.style.SUCCESS(f'  Average rate: {total/elapsed:.2f} appointments/second')
            )
        self.stdout.write(self.style.SUCCESS('='*60))
