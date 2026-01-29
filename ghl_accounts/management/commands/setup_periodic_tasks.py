"""
Management command to set up Celery Beat periodic tasks.
"""
from django.core.management.base import BaseCommand
from django_celery_beat.models import PeriodicTask, IntervalSchedule
import json


class Command(BaseCommand):
    help = 'Set up periodic Celery tasks for patient and appointment syncing'

    def add_arguments(self, parser):
        parser.add_argument(
            '--interval',
            type=int,
            default=3600,
            help='Interval in seconds (default: 3600 = 1 hour). Use 30 for testing.',
        )
        parser.add_argument(
            '--period',
            type=str,
            choices=['seconds', 'minutes', 'hours'],
            default='hours',
            help='Period unit (default: hours). Use "seconds" for testing.',
        )

    def handle(self, *args, **options):
        interval_value = options['interval']
        period_choice = options['period'].upper()
        
        # Map period choice to IntervalSchedule constant
        period_map = {
            'SECONDS': IntervalSchedule.SECONDS,
            'MINUTES': IntervalSchedule.MINUTES,
            'HOURS': IntervalSchedule.HOURS,
        }
        period = period_map.get(period_choice, IntervalSchedule.HOURS)
        
        # Create interval schedule
        schedule, created = IntervalSchedule.objects.get_or_create(
            every=interval_value,
            period=period,
        )
        
        if created:
            self.stdout.write(
                self.style.SUCCESS(f'Created interval schedule: Every {schedule.every} {schedule.period}')
            )
        else:
            # Update existing schedule if different
            if schedule.every != interval_value or schedule.period != period:
                schedule.every = interval_value
                schedule.period = period
                schedule.save()
                self.stdout.write(
                    self.style.SUCCESS(f'Updated interval schedule: Every {schedule.every} {schedule.period}')
                )
            else:
                self.stdout.write(
                    self.style.SUCCESS(f'Interval schedule already exists: Every {schedule.every} {schedule.period}')
                )
        
        # Create periodic task for patient sync
        patient_task, patient_created = PeriodicTask.objects.get_or_create(
            name='Sync Patients from e-Physio to GHL (Hourly)',
            defaults={
                'task': 'sync_patients_incremental',
                'interval': schedule,
                'enabled': True,
                'description': 'Fetches patients from e-Physio, updates ContactSync table, and syncs new patients to GHL. Runs every hour.',
            }
        )
        
        if patient_created:
            self.stdout.write(
                self.style.SUCCESS('Created periodic task: Sync Patients from e-Physio to GHL (Hourly)')
            )
        else:
            # Update existing task
            patient_task.task = 'sync_patients_incremental'
            patient_task.interval = schedule
            patient_task.enabled = True
            patient_task.description = 'Fetches patients from e-Physio, updates ContactSync table, and syncs new patients to GHL. Runs every hour.'
            patient_task.save()
            self.stdout.write(
                self.style.SUCCESS('Updated periodic task: Sync Patients from e-Physio to GHL (Hourly)')
            )
        
        # Create periodic task for appointment sync
        appointment_task, appointment_created = PeriodicTask.objects.get_or_create(
            name='Sync Appointments from e-Physio to GHL (Hourly)',
            defaults={
                'task': 'sync_appointments_incremental',
                'interval': schedule,
                'enabled': True,
                'description': 'Fetches appointments from e-Physio, updates AppointmentSync table, and syncs new appointments to GHL. Runs every hour.',
            }
        )
        
        if appointment_created:
            self.stdout.write(
                self.style.SUCCESS('Created periodic task: Sync Appointments from e-Physio to GHL (Hourly)')
            )
        else:
            # Update existing task
            appointment_task.task = 'sync_appointments_incremental'
            appointment_task.interval = schedule
            appointment_task.enabled = True
            appointment_task.description = 'Fetches appointments from e-Physio, updates AppointmentSync table, and syncs new appointments to GHL. Runs every hour.'
            appointment_task.save()
            self.stdout.write(
                self.style.SUCCESS('Updated periodic task: Sync Appointments from e-Physio to GHL (Hourly)')
            )
        
        # Create interval schedule for token refresh (20 hours)
        token_refresh_schedule, token_created = IntervalSchedule.objects.get_or_create(
            every=20,
            period=IntervalSchedule.HOURS,
        )
        
        if token_created:
            self.stdout.write(
                self.style.SUCCESS(f'Created interval schedule for token refresh: Every {token_refresh_schedule.every} {token_refresh_schedule.period}')
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(f'Token refresh interval schedule already exists: Every {token_refresh_schedule.every} {token_refresh_schedule.period}')
            )
        
        # Create periodic task for GHL token refresh
        token_task, token_created = PeriodicTask.objects.get_or_create(
            name='Refresh GHL Access Token (Every 20 Hours)',
            defaults={
                'task': 'refresh_ghl_token_periodic',
                'interval': token_refresh_schedule,
                'enabled': True,
                'description': 'Refreshes GHL access token every 20 hours to prevent expiration (tokens expire in 24 hours).',
            }
        )
        
        if token_created:
            self.stdout.write(
                self.style.SUCCESS('Created periodic task: Refresh GHL Access Token (Every 20 Hours)')
            )
        else:
            # Update existing task
            token_task.task = 'refresh_ghl_token_periodic'
            token_task.interval = token_refresh_schedule
            token_task.enabled = True
            token_task.description = 'Refreshes GHL access token every 20 hours to prevent expiration (tokens expire in 24 hours).'
            token_task.save()
            self.stdout.write(
                self.style.SUCCESS('Updated periodic task: Refresh GHL Access Token (Every 20 Hours)')
            )
        
        self.stdout.write(self.style.SUCCESS('\n' + '='*60))
        self.stdout.write(self.style.SUCCESS('Periodic Tasks Setup Complete!'))
        self.stdout.write(self.style.SUCCESS('='*60))
        self.stdout.write(self.style.SUCCESS('\nTask Details:'))
        self.stdout.write(self.style.SUCCESS(f'\n1. Patient Sync:'))
        self.stdout.write(self.style.SUCCESS(f'   Task Name: {patient_task.name}'))
        self.stdout.write(self.style.SUCCESS(f'   Task Function: {patient_task.task}'))
        self.stdout.write(self.style.SUCCESS(f'   Schedule: Every {schedule.every} {schedule.period}'))
        self.stdout.write(self.style.SUCCESS(f'   Enabled: {patient_task.enabled}'))
        self.stdout.write(self.style.SUCCESS(f'\n2. Appointment Sync:'))
        self.stdout.write(self.style.SUCCESS(f'   Task Name: {appointment_task.name}'))
        self.stdout.write(self.style.SUCCESS(f'   Task Function: {appointment_task.task}'))
        self.stdout.write(self.style.SUCCESS(f'   Schedule: Every {schedule.every} {schedule.period}'))
        self.stdout.write(self.style.SUCCESS(f'   Enabled: {appointment_task.enabled}'))
        self.stdout.write(self.style.SUCCESS(f'\n3. GHL Token Refresh:'))
        self.stdout.write(self.style.SUCCESS(f'   Task Name: {token_task.name}'))
        self.stdout.write(self.style.SUCCESS(f'   Task Function: {token_task.task}'))
        self.stdout.write(self.style.SUCCESS(f'   Schedule: Every {token_refresh_schedule.every} {token_refresh_schedule.period}'))
        self.stdout.write(self.style.SUCCESS(f'   Enabled: {token_task.enabled}'))
        self.stdout.write(self.style.SUCCESS('\nTo start Celery worker (Windows - REQUIRED: --pool=solo):'))
        self.stdout.write(self.style.WARNING('  celery -A e_physio_integration worker --pool=solo --loglevel=info'))
        self.stdout.write(self.style.SUCCESS('\nTo start Celery worker (Linux/Mac):'))
        self.stdout.write(self.style.WARNING('  celery -A e_physio_integration worker --loglevel=info'))
        self.stdout.write(self.style.SUCCESS('\nTo start Celery Beat:'))
        self.stdout.write(self.style.WARNING('  celery -A e_physio_integration beat --loglevel=info'))
        self.stdout.write(self.style.SUCCESS('='*60))
