from django.core.management.base import BaseCommand
from django.db import transaction
from ghl_accounts.models import ContactSync
from ephysio.services.patients import get_active_patients


class Command(BaseCommand):
    help = 'Sync all active patients from ephysio to ContactSync table using bulk_create'

    def add_arguments(self, parser):
        parser.add_argument(
            '--batch-size',
            type=int,
            default=1000,
            help='Number of records to create in each batch (default: 1000)',
        )

    def handle(self, *args, **options):
        batch_size = options['batch_size']
        
        self.stdout.write(self.style.SUCCESS('Fetching active patients from ephysio...'))
        
        try:
            patients = get_active_patients()
            self.stdout.write(self.style.SUCCESS(f'Found {len(patients)} active patients'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Error fetching patients: {str(e)}'))
            return

        if not patients:
            self.stdout.write(self.style.WARNING('No patients found'))
            return

        # Get existing contacts by ephysio_patient_id
        existing_contacts = {
            str(contact.ephysio_patient_id): contact
            for contact in ContactSync.objects.filter(
                ephysio_patient_id__isnull=False
            )
        }

        # Prepare ContactSync objects for bulk creation and update
        contacts_to_create = []
        contacts_to_update = []

        for patient in patients:
            patient_id = str(patient.get('id'))
            
            # Check if contact already exists
            if patient_id in existing_contacts:
                # Update existing record
                contact = existing_contacts[patient_id]
                contact.phone = patient.get('phone', '') or None
                contact.email = patient.get('email', '') or None
                contact.first_name = patient.get('firstName', '') or None
                contact.last_name = patient.get('lastName', '') or None
                contact.salutation = patient.get('salutation', '') or None
                contact.street = patient.get('street', '') or None
                contact.zip = patient.get('zip', '') or None
                contact.city = patient.get('city', '') or None
                contact.birth_date = patient.get('birthDate', '') or None
                contact.sex = patient.get('sex')
                contact.source = 'ephysio'
                contacts_to_update.append(contact)
            else:
                # Create new ContactSync object
                contact = ContactSync(
                    ephysio_patient_id=patient_id,
                    phone=patient.get('phone', '') or None,
                    email=patient.get('email', '') or None,  # May not be in response
                    first_name=patient.get('firstName', '') or None,
                    last_name=patient.get('lastName', '') or None,
                    salutation=patient.get('salutation', '') or None,
                    street=patient.get('street', '') or None,
                    zip=patient.get('zip', '') or None,
                    city=patient.get('city', '') or None,
                    birth_date=patient.get('birthDate', '') or None,
                    sex=patient.get('sex'),
                    source='ephysio',
                    ghl_contact_id=None  # Will be set when synced to GHL
                )
                contacts_to_create.append(contact)

        # Bulk update existing contacts
        total_updated = 0
        if contacts_to_update:
            self.stdout.write(self.style.SUCCESS(f'Updating {len(contacts_to_update)} existing contacts in batches of {batch_size}...'))
            
            update_fields = [
                'phone', 'email', 'first_name', 'last_name', 'salutation',
                'street', 'zip', 'city', 'birth_date', 'sex', 'source'
            ]
            
            with transaction.atomic():
                for i in range(0, len(contacts_to_update), batch_size):
                    batch = contacts_to_update[i:i + batch_size]
                    ContactSync.objects.bulk_update(batch, update_fields, batch_size=batch_size)
                    total_updated += len(batch)
                    self.stdout.write(
                        self.style.SUCCESS(
                            f'Updated batch {i // batch_size + 1}: {len(batch)} contacts '
                            f'(Total: {total_updated}/{len(contacts_to_update)})'
                        )
                    )

        # Bulk create new contacts in batches
        total_created = 0
        if contacts_to_create:
            self.stdout.write(self.style.SUCCESS(f'Creating {len(contacts_to_create)} new contacts in batches of {batch_size}...'))
            
            with transaction.atomic():
                for i in range(0, len(contacts_to_create), batch_size):
                    batch = contacts_to_create[i:i + batch_size]
                    ContactSync.objects.bulk_create(batch, ignore_conflicts=True)
                    total_created += len(batch)
                    self.stdout.write(
                        self.style.SUCCESS(
                            f'Created batch {i // batch_size + 1}: {len(batch)} contacts '
                            f'(Total: {total_created}/{len(contacts_to_create)})'
                        )
                    )

        # Summary
        self.stdout.write(self.style.SUCCESS('\n' + '='*50))
        self.stdout.write(self.style.SUCCESS('Sync Summary:'))
        self.stdout.write(self.style.SUCCESS(f'  Total patients fetched: {len(patients)}'))
        self.stdout.write(self.style.SUCCESS(f'  New contacts created: {total_created}'))
        self.stdout.write(self.style.SUCCESS(f'  Existing contacts updated: {total_updated}'))
        self.stdout.write(self.style.SUCCESS('='*50))
