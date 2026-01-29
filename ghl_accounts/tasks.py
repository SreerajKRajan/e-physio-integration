"""
Celery tasks for periodic syncing of patients and appointments.
"""
from celery import shared_task
from django.db import transaction
from django.utils import timezone
from ghl_accounts.models import ContactSync, AppointmentSync
from ephysio.services.patients import get_active_patients
from ephysio.services.appointments import get_ephysio_appointments, epoch_ms_to_datetime
from ghl_accounts.services.contacts import (
    get_ghl_auth,
    create_ghl_contact,
    build_ghl_contact_payload,
    refresh_ghl_token
)
from ghl_accounts.services.appointments import (
    create_ghl_appointment,
    build_ghl_appointment_payload
)
import logging

logger = logging.getLogger(__name__)


@shared_task(name='sync_patients_incremental')
def sync_patients_incremental():
    """
    Periodic task to sync patients from e-Physio to ContactSync and then to GHL.
    
    This task:
    1. Fetches all active patients from e-Physio
    2. Compares with existing ContactSync records
    3. Creates/updates ContactSync records for new/updated patients
    4. Syncs new patients (without ghl_contact_id) to GHL
    
    Runs every hour via Celery Beat.
    """
    logger.info("Starting incremental patient sync task...")
    
    try:
        # Fetch active patients from e-Physio
        logger.info("Fetching active patients from e-Physio...")
        patients = get_active_patients()
        logger.info(f"Found {len(patients)} active patients")
        
        if not patients:
            logger.warning("No patients found in e-Physio")
            return {
                'status': 'success',
                'message': 'No patients found',
                'created': 0,
                'updated': 0,
                'synced_to_ghl': 0
            }
        
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
        contacts_to_sync_to_ghl = []
        
        for patient in patients:
            patient_id = str(patient.get('id'))
            
            if not patient_id:
                continue
            
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
                # Preserve original source if it was created from GHL webhook.
                # Only mark as 'ephysio' if source is empty or already 'ephysio'.
                if not contact.source or contact.source == 'ephysio':
                    contact.source = 'ephysio'
                contacts_to_update.append(contact)
                
                # If this contact doesn't have ghl_contact_id, add to sync list
                if not contact.ghl_contact_id:
                    contacts_to_sync_to_ghl.append(contact)
            else:
                # Create new ContactSync object
                contact = ContactSync(
                    ephysio_patient_id=patient_id,
                    phone=patient.get('phone', '') or None,
                    email=patient.get('email', '') or None,
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
                # New contacts also need to be synced to GHL
                contacts_to_sync_to_ghl.append(contact)
        
        # Bulk update existing contacts
        total_updated = 0
        if contacts_to_update:
            logger.info(f"Updating {len(contacts_to_update)} existing contacts...")
            update_fields = [
                'phone', 'email', 'first_name', 'last_name', 'salutation',
                'street', 'zip', 'city', 'birth_date', 'sex', 'source'
            ]
            
            with transaction.atomic():
                ContactSync.objects.bulk_update(
                    contacts_to_update,
                    update_fields,
                    batch_size=1000
                )
                total_updated = len(contacts_to_update)
        
        # Bulk create new contacts
        total_created = 0
        created_patient_ids = []
        if contacts_to_create:
            logger.info(f"Creating {len(contacts_to_create)} new contacts...")
            created_patient_ids = [str(c.ephysio_patient_id) for c in contacts_to_create]
            with transaction.atomic():
                ContactSync.objects.bulk_create(
                    contacts_to_create,
                    ignore_conflicts=True,
                    batch_size=1000
                )
                total_created = len(contacts_to_create)
        
        # Prepare list of contacts to sync to GHL
        # Include: 1) Existing contacts without ghl_contact_id, 2) Newly created contacts
        contacts_to_sync_to_ghl = [
            c for c in contacts_to_sync_to_ghl if c.id  # Only already-saved contacts
        ]
        
        # Add newly created contacts (fetch from DB since bulk_create doesn't return IDs)
        if created_patient_ids:
            newly_created = ContactSync.objects.filter(
                ephysio_patient_id__in=created_patient_ids,
                ghl_contact_id__isnull=True
            )
            contacts_to_sync_to_ghl.extend(newly_created)
        
        # Sync new/updated contacts to GHL
        total_synced_to_ghl = 0
        if contacts_to_sync_to_ghl:
            logger.info(f"Syncing {len(contacts_to_sync_to_ghl)} contacts to GHL...")
            
            # Check GHL authentication
            access_token, location_id = get_ghl_auth()
            if not access_token or not location_id:
                logger.error("GHL authentication not available, skipping GHL sync")
            else:
                for contact in contacts_to_sync_to_ghl:
                    try:
                        payload = build_ghl_contact_payload(contact)
                        result = create_ghl_contact(payload)
                        
                        if result and not result.get('error'):
                            # Extract contact ID from response
                            contact_data = result.get('contact') or result
                            ghl_contact_id = contact_data.get('id') or result.get('id')
                            
                            if ghl_contact_id:
                                contact.ghl_contact_id = ghl_contact_id
                                contact.save(update_fields=['ghl_contact_id'])
                                total_synced_to_ghl += 1
                            else:
                                logger.warning(f"No ID in response for contact {contact.id}")
                        else:
                            error_msg = result.get('error', '') if isinstance(result, dict) else str(result)
                            error_lower = error_msg.lower()
                            # Check if it's a duplicate error
                            if ('duplicate' in error_lower or 
                                'already exists' in error_lower or
                                'does not allow duplicated' in error_lower):
                                # Contact already exists in GHL - this is expected for incremental sync
                                # We can't easily find the GHL contact ID without a search API
                                # So we'll just skip it (it's already in GHL)
                                logger.info(f"Contact {contact.id} already exists in GHL (duplicate - skipping)")
                            else:
                                logger.warning(f"Error syncing contact {contact.id} to GHL: {error_msg}")
                    except Exception as e:
                        logger.error(f"Exception syncing contact {contact.id} to GHL: {str(e)}")
        
        result = {
            'status': 'success',
            'message': 'Patient sync completed',
            'total_patients': len(patients),
            'created': total_created,
            'updated': total_updated,
            'synced_to_ghl': total_synced_to_ghl,
            'timestamp': timezone.now().isoformat()
        }
        
        logger.info(f"Patient sync completed: {result}")
        return result
        
    except Exception as e:
        error_msg = f"Error in incremental patient sync: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return {
            'status': 'error',
            'message': error_msg,
            'timestamp': timezone.now().isoformat()
        }


@shared_task(name='sync_appointments_incremental')
def sync_appointments_incremental():
    """
    Periodic task to sync appointments from e-Physio to AppointmentSync and then to GHL.
    
    This task:
    1. Fetches all appointments from e-Physio (using default date range)
    2. Compares with existing AppointmentSync records
    3. Creates/updates AppointmentSync records for new/updated appointments
    4. Links appointments to ghl_contact_id if patient exists in ContactSync
    5. Syncs new appointments (without ghl_appointment_id) to GHL
    
    Runs every hour via Celery Beat.
    """
    logger.info("Starting incremental appointment sync task...")
    
    try:
        # Default timestamps from the API URL shared by user
        DEFAULT_FROM_TIMESTAMP = 1758911400000
        DEFAULT_TO_TIMESTAMP = 1795631400000
        
        # Fetch appointments from e-Physio
        logger.info("Fetching appointments from e-Physio...")
        appointments = get_ephysio_appointments(DEFAULT_FROM_TIMESTAMP, DEFAULT_TO_TIMESTAMP)
        logger.info(f"Found {len(appointments)} appointments")
        
        if not appointments:
            logger.warning("No appointments found in e-Physio")
            return {
                'status': 'success',
                'message': 'No appointments found',
                'created': 0,
                'updated': 0,
                'synced_to_ghl': 0
            }
        
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
        appointments_to_sync_to_ghl = []
        
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
                # Preserve original source if it was created from GHL webhook
                # Only mark as 'ephysio' if source is empty or already 'ephysio'
                if not appt_sync.source or appt_sync.source == 'ephysio':
                    appt_sync.source = 'ephysio'
                appointments_to_update.append(appt_sync)
                
                # If this appointment doesn't have ghl_appointment_id and has ghl_contact_id, add to sync list
                if not appt_sync.ghl_appointment_id and ghl_contact_id:
                    appointments_to_sync_to_ghl.append(appt_sync)
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
                # New appointments with ghl_contact_id also need to be synced to GHL
                if ghl_contact_id:
                    appointments_to_sync_to_ghl.append(appt_sync)
        
        # Bulk update existing appointments
        total_updated = 0
        if appointments_to_update:
            logger.info(f"Updating {len(appointments_to_update)} existing appointments...")
            update_fields = [
                'start_time', 'end_time', 'status', 'event_type_id',
                'user_id', 'client_id', 'admin_info_id', 'ephysio_patient_id',
                'ghl_contact_id', 'source'
            ]
            
            with transaction.atomic():
                AppointmentSync.objects.bulk_update(
                    appointments_to_update,
                    update_fields,
                    batch_size=1000
                )
                total_updated = len(appointments_to_update)
        
        # Bulk create new appointments
        total_created = 0
        created_appointment_ids = []
        if appointments_to_create:
            logger.info(f"Creating {len(appointments_to_create)} new appointments...")
            created_appointment_ids = [str(a.ephysio_appointment_id) for a in appointments_to_create]
            with transaction.atomic():
                AppointmentSync.objects.bulk_create(
                    appointments_to_create,
                    ignore_conflicts=True,
                    batch_size=1000
                )
                total_created = len(appointments_to_create)
        
        # Prepare list of appointments to sync to GHL
        # Include: 1) Existing appointments without ghl_appointment_id, 2) Newly created appointments
        appointments_to_sync_to_ghl = [
            a for a in appointments_to_sync_to_ghl if a.id  # Only already-saved appointments
        ]
        
        # Add newly created appointments (fetch from DB since bulk_create doesn't return IDs)
        if created_appointment_ids:
            newly_created = AppointmentSync.objects.filter(
                ephysio_appointment_id__in=created_appointment_ids,
                ghl_appointment_id__isnull=True,
                ghl_contact_id__isnull=False
            )
            appointments_to_sync_to_ghl.extend(newly_created)
        
        # Sync new/updated appointments to GHL
        total_synced_to_ghl = 0
        if appointments_to_sync_to_ghl:
            logger.info(f"Syncing {len(appointments_to_sync_to_ghl)} appointments to GHL...")
            
            # Check GHL authentication
            access_token, location_id = get_ghl_auth()
            if not access_token or not location_id:
                logger.error("GHL authentication not available, skipping GHL sync")
            else:
                for appt_sync in appointments_to_sync_to_ghl:
                    # Only sync if we have ghl_contact_id
                    if not appt_sync.ghl_contact_id:
                        logger.warning(f"Appointment {appt_sync.id} missing ghl_contact_id, skipping GHL sync")
                        continue
                    
                    try:
                        result = create_ghl_appointment(appt_sync)
                        
                        if result and not result.get('error'):
                            # Extract appointment ID from response
                            appointment_data = result.get('appointment') or result
                            ghl_appointment_id = appointment_data.get('id') or result.get('id')
                            
                            if ghl_appointment_id:
                                appt_sync.ghl_appointment_id = ghl_appointment_id
                                appt_sync.save(update_fields=['ghl_appointment_id'])
                                total_synced_to_ghl += 1
                            else:
                                logger.warning(f"No ID in response for appointment {appt_sync.id}")
                        else:
                            error_msg = result.get('error', '') if isinstance(result, dict) else str(result)
                            error_lower = error_msg.lower()
                            # Check if it's a duplicate error
                            if ('duplicate' in error_lower or 
                                'already exists' in error_lower or
                                result.get('is_duplicate', False)):
                                # Appointment already exists in GHL - this is expected for incremental sync
                                logger.info(f"Appointment {appt_sync.id} already exists in GHL (duplicate - skipping)")
                            else:
                                logger.warning(f"Error syncing appointment {appt_sync.id} to GHL: {error_msg}")
                    except Exception as e:
                        logger.error(f"Exception syncing appointment {appt_sync.id} to GHL: {str(e)}")
        
        result = {
            'status': 'success',
            'message': 'Appointment sync completed',
            'total_appointments': len(appointments),
            'created': total_created,
            'updated': total_updated,
            'synced_to_ghl': total_synced_to_ghl,
            'timestamp': timezone.now().isoformat()
        }
        
        logger.info(f"Appointment sync completed: {result}")
        return result
        
    except Exception as e:
        error_msg = f"Error in incremental appointment sync: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return {
            'status': 'error',
            'message': error_msg,
            'timestamp': timezone.now().isoformat()
        }


@shared_task(name='refresh_ghl_token_periodic')
def refresh_ghl_token_periodic():
    """
    Periodic task to refresh GHL access token before it expires.
    
    GHL tokens expire in 24 hours. This task runs every 20 hours to ensure
    tokens are refreshed before expiration.
    
    Runs every 20 hours via Celery Beat.
    """
    logger.info("Starting GHL token refresh task...")
    
    try:
        success, message = refresh_ghl_token()
        
        if success:
            result = {
                'status': 'success',
                'message': message,
                'timestamp': timezone.now().isoformat()
            }
            logger.info(f"GHL token refresh completed: {result}")
            return result
        else:
            result = {
                'status': 'error',
                'message': message,
                'timestamp': timezone.now().isoformat()
            }
            logger.error(f"GHL token refresh failed: {result}")
            return result
            
    except Exception as e:
        error_msg = f"Error in GHL token refresh: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return {
            'status': 'error',
            'message': error_msg,
            'timestamp': timezone.now().isoformat()
        }
