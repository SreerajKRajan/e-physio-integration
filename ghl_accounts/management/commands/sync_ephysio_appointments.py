from django.core.management.base import BaseCommand
from django.db import transaction
from ghl_accounts.models import AppointmentSync, ContactSync
from ephysio.services.appointments import get_ephysio_appointments, epoch_ms_to_datetime
from datetime import datetime, timedelta


class Command(BaseCommand):
    help = 'Sync all appointments from ephysio to AppointmentSync table using bulk_create'

    def add_arguments(self, parser):
        parser.add_argument(
            '--batch-size',
            type=int,
            default=1000,
            help='Number of records to create in each batch (default: 1000)',
        )
        parser.add_argument(
            '--from-date',
            type=str,
            help='Start date in YYYY-MM-DD format (default: uses API default timestamp)',
        )
        parser.add_argument(
            '--to-date',
            type=str,
            help='End date in YYYY-MM-DD format (default: uses API default timestamp)',
        )
        parser.add_argument(
            '--from-timestamp',
            type=int,
            help='Start timestamp in milliseconds (epoch ms). Overrides --from-date and default',
        )
        parser.add_argument(
            '--to-timestamp',
            type=int,
            help='End timestamp in milliseconds (epoch ms). Overrides --to-date and default',
        )

    def handle(self, *args, **options):
        batch_size = options['batch_size']
        
        # Calculate timestamps
        # Default timestamps from the API URL shared by user
        DEFAULT_FROM_TIMESTAMP = 1758911400000
        DEFAULT_TO_TIMESTAMP = 1795631400000
        
        from_timestamp = options.get('from_timestamp')
        to_timestamp = options.get('to_timestamp')
        
        if not from_timestamp:
            if options.get('from_date'):
                try:
                    from_date = datetime.strptime(options['from_date'], '%Y-%m-%d')
                    from_timestamp = int(from_date.timestamp() * 1000)
                except ValueError:
                    self.stdout.write(
                        self.style.ERROR('Invalid --from-date format. Use YYYY-MM-DD')
                    )
                    return
            else:
                # Use default timestamp from API
                from_timestamp = DEFAULT_FROM_TIMESTAMP
        
        if not to_timestamp:
            if options.get('to_date'):
                try:
                    to_date = datetime.strptime(options['to_date'], '%Y-%m-%d')
                    to_timestamp = int(to_date.timestamp() * 1000)
                except ValueError:
                    self.stdout.write(
                        self.style.ERROR('Invalid --to-date format. Use YYYY-MM-DD')
                    )
                    return
            else:
                # Use default timestamp from API
                to_timestamp = DEFAULT_TO_TIMESTAMP
        
        self.stdout.write(self.style.SUCCESS('Fetching appointments from ephysio...'))
        self.stdout.write(
            self.style.SUCCESS(
                f'Date range: {datetime.fromtimestamp(from_timestamp/1000).strftime("%Y-%m-%d")} '
                f'to {datetime.fromtimestamp(to_timestamp/1000).strftime("%Y-%m-%d")}'
            )
        )
        
        try:
            appointments = get_ephysio_appointments(from_timestamp, to_timestamp)
            self.stdout.write(self.style.SUCCESS(f'Found {len(appointments)} appointments'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Error fetching appointments: {str(e)}'))
            return

        if not appointments:
            self.stdout.write(self.style.WARNING('No appointments found'))
            return

        # Get existing appointments by ephysio_appointment_id
        existing_appointments = {
            str(appt.ephysio_appointment_id): appt
            for appt in AppointmentSync.objects.filter(
                ephysio_appointment_id__isnull=False
            )
        }

        # Get ContactSync records to link ghl_contact_id
        contact_sync_map = {
            str(contact.ephysio_patient_id): contact
            for contact in ContactSync.objects.filter(
                ephysio_patient_id__isnull=False
            )
        }

        # Prepare AppointmentSync objects for bulk creation and update
        appointments_to_create = []
        appointments_to_update = []

        for appointment in appointments:
            ephysio_appointment_id = str(appointment.get('id'))
            ephysio_patient_id = str(appointment.get('patientId'))
            
            if not ephysio_appointment_id or not ephysio_patient_id:
                continue
            
            # Convert timestamps to datetime
            start_time = epoch_ms_to_datetime(appointment.get('start'))
            end_time = epoch_ms_to_datetime(appointment.get('end'))
            
            if not start_time or not end_time:
                continue
            
            # Get ghl_contact_id from ContactSync if available
            ghl_contact_id = None
            contact_sync = contact_sync_map.get(ephysio_patient_id)
            if contact_sync and contact_sync.ghl_contact_id:
                ghl_contact_id = contact_sync.ghl_contact_id
            
            # Check if appointment already exists
            if ephysio_appointment_id in existing_appointments:
                # Update existing record
                appt_sync = existing_appointments[ephysio_appointment_id]
                appt_sync.start_time = start_time
                appt_sync.end_time = end_time
                appt_sync.status = str(appointment.get('status', '')) or None
                appt_sync.event_type_id = appointment.get('eventTypeId')
                appt_sync.user_id = appointment.get('user_id')
                appt_sync.client_id = appointment.get('clientId')
                appt_sync.admin_info_id = appointment.get('adminInfoId')
                appt_sync.ephysio_patient_id = ephysio_patient_id
                appt_sync.ghl_contact_id = ghl_contact_id
                appt_sync.source = 'ephysio'
                appointments_to_update.append(appt_sync)
            else:
                # Create new AppointmentSync object
                appt_sync = AppointmentSync(
                    ephysio_appointment_id=ephysio_appointment_id,
                    ephysio_patient_id=ephysio_patient_id,
                    ghl_contact_id=ghl_contact_id,
                    start_time=start_time,
                    end_time=end_time,
                    status=str(appointment.get('status', '')) or None,
                    event_type_id=appointment.get('eventTypeId'),
                    user_id=appointment.get('user_id'),
                    client_id=appointment.get('clientId'),
                    admin_info_id=appointment.get('adminInfoId'),
                    source='ephysio',
                    ghl_appointment_id=None  # Will be set when synced to GHL
                )
                appointments_to_create.append(appt_sync)

        # Bulk update existing appointments
        total_updated = 0
        if appointments_to_update:
            self.stdout.write(
                self.style.SUCCESS(
                    f'Updating {len(appointments_to_update)} existing appointments '
                    f'in batches of {batch_size}...'
                )
            )
            
            update_fields = [
                'start_time', 'end_time', 'status', 'event_type_id',
                'user_id', 'client_id', 'admin_info_id', 'ephysio_patient_id',
                'ghl_contact_id', 'source'
            ]
            
            with transaction.atomic():
                for i in range(0, len(appointments_to_update), batch_size):
                    batch = appointments_to_update[i:i + batch_size]
                    AppointmentSync.objects.bulk_update(batch, update_fields, batch_size=batch_size)
                    total_updated += len(batch)
                    self.stdout.write(
                        self.style.SUCCESS(
                            f'Updated batch {i // batch_size + 1}: {len(batch)} appointments '
                            f'(Total: {total_updated}/{len(appointments_to_update)})'
                        )
                    )

        # Bulk create new appointments in batches
        total_created = 0
        if appointments_to_create:
            self.stdout.write(
                self.style.SUCCESS(
                    f'Creating {len(appointments_to_create)} new appointments '
                    f'in batches of {batch_size}...'
                )
            )
            
            with transaction.atomic():
                for i in range(0, len(appointments_to_create), batch_size):
                    batch = appointments_to_create[i:i + batch_size]
                    AppointmentSync.objects.bulk_create(batch, ignore_conflicts=True)
                    total_created += len(batch)
                    self.stdout.write(
                        self.style.SUCCESS(
                            f'Created batch {i // batch_size + 1}: {len(batch)} appointments '
                            f'(Total: {total_created}/{len(appointments_to_create)})'
                        )
                    )

        # Summary
        self.stdout.write(self.style.SUCCESS('\n' + '='*50))
        self.stdout.write(self.style.SUCCESS('Sync Summary:'))
        self.stdout.write(self.style.SUCCESS(f'  Total appointments fetched: {len(appointments)}'))
        self.stdout.write(self.style.SUCCESS(f'  New appointments created: {total_created}'))
        self.stdout.write(self.style.SUCCESS(f'  Existing appointments updated: {total_updated}'))
        self.stdout.write(self.style.SUCCESS(f'  Appointments with GHL contact link: {sum(1 for a in appointments_to_create + appointments_to_update if a.ghl_contact_id)}'))
        self.stdout.write(self.style.SUCCESS('='*50))
