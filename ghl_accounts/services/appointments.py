import requests
from ghl_accounts.services.contacts import get_ghl_auth, get_ghl_headers
import logging
import time

logger = logging.getLogger(__name__)

GHL_BASE_URL = "https://services.leadconnectorhq.com"

# GHL Calendar constants
GHL_CALENDAR_ID = "OAnjgwIHOo7wiTj8Sk3q"
GHL_ASSIGNED_USER_ID = "QkbUv2Ttp1oCeY6hrKLl"

# Request settings
REQUEST_TIMEOUT = 30  # Increased from 10 to 30 seconds
MAX_RETRIES = 3
RETRY_DELAY = 2  # seconds


def build_ghl_appointment_payload(appt_sync):
    """
    Build GHL appointment payload from AppointmentSync model instance.
    
    Args:
        appt_sync: AppointmentSync model instance
    
    Returns:
        dict: GHL appointment payload
    """
    access_token, location_id = get_ghl_auth()
    
    if not access_token or not location_id:
        raise ValueError("GHL authentication not available")
    
    if not appt_sync.ghl_contact_id:
        raise ValueError("Appointment must have ghl_contact_id to sync to GHL")
    
    # Format datetime to ISO format with timezone
    start_time = appt_sync.start_time.isoformat()
    end_time = appt_sync.end_time.isoformat()
    
    # Build title - include ephysio appointment ID if available
    title = "Physio Appointment"
    if appt_sync.ephysio_appointment_id:
        title = f"Physio Appointment #{appt_sync.ephysio_appointment_id}"
    
    # Map ephysio status to GHL appointment status
    # ephysio status 5 seems to be completed/billed, use "confirmed" as default
    appointment_status = "confirmed"
    if appt_sync.status:
        # You can customize this mapping based on your ephysio status codes
        status_map = {
            "1": "scheduled",
            "2": "confirmed",
            "3": "in_progress",
            "4": "completed",
            "5": "confirmed",  # Assuming status 5 is confirmed/billed
        }
        appointment_status = status_map.get(str(appt_sync.status), "confirmed")
    
    payload = {
        "title": title,
        "meetingLocationType": "custom",
        "meetingLocationId": "custom_0",
        "overrideLocationConfig": True,
        "appointmentStatus": appointment_status,
        "assignedUserId": GHL_ASSIGNED_USER_ID,
        "description": f"Physiotherapy appointment for patient {appt_sync.ephysio_patient_id}",
        "address": "Zoom",
        "ignoreDateRange": False,
        "toNotify": False,
        "ignoreFreeSlotValidation": True,
        "calendarId": GHL_CALENDAR_ID,
        "locationId": location_id,
        "contactId": appt_sync.ghl_contact_id,
        "startTime": start_time,
        "endTime": end_time,
    }
    
    # Remove None values (though we shouldn't have any)
    payload = {k: v for k, v in payload.items() if v is not None}
    
    return payload


def create_ghl_appointment(appt_sync):
    """
    Create a new appointment in GHL with retry logic for transient errors.
    
    Args:
        appt_sync: AppointmentSync model instance
    
    Returns:
        dict: Created appointment data with ID, or dict with error info if failed
    """
    access_token, location_id = get_ghl_auth()
    
    if not access_token or not location_id:
        logger.error("GHL authentication not available")
        return {"error": "Authentication not available"}
    
    if not appt_sync.ghl_contact_id:
        logger.error(f"Appointment {appt_sync.id} missing ghl_contact_id")
        return {"error": "Missing ghl_contact_id"}
    
    headers = get_ghl_headers()
    payload = build_ghl_appointment_payload(appt_sync)
    url = f"{GHL_BASE_URL}/calendars/events/appointments"
    
    # Retry logic for transient errors
    for attempt in range(MAX_RETRIES):
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=REQUEST_TIMEOUT)
            
            if response.status_code in [200, 201]:
                result = response.json()
                # GHL API might return appointment in 'appointment' key or directly
                if 'appointment' in result:
                    return result
                elif 'id' in result:
                    return {'appointment': result}
                else:
                    return result
            
            # Check if it's a retryable error (5xx server errors)
            if response.status_code >= 500 and attempt < MAX_RETRIES - 1:
                error_text = response.text[:200] if len(response.text) > 200 else response.text
                logger.warning(
                    f"Server error {response.status_code} on attempt {attempt + 1}/{MAX_RETRIES}, "
                    f"retrying in {RETRY_DELAY}s... Error: {error_text[:100]}"
                )
                time.sleep(RETRY_DELAY * (attempt + 1))  # Exponential backoff
                continue
            
            # Non-retryable error (4xx client errors)
            error_text = response.text
            try:
                error_data = response.json()
                error_message = error_data.get('message', error_text[:200])
            except:
                error_message = error_text[:200] if len(error_text) > 200 else error_text
            
            logger.error(f"Error creating GHL appointment: {response.status_code} - {error_message}")
            return {"error": error_message, "status_code": response.status_code}
            
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
            # Retry on timeout or connection errors
            if attempt < MAX_RETRIES - 1:
                error_msg = str(e)[:100]  # Truncate long error messages
                logger.warning(
                    f"Network error on attempt {attempt + 1}/{MAX_RETRIES}, "
                    f"retrying in {RETRY_DELAY}s... Error: {error_msg}"
                )
                time.sleep(RETRY_DELAY * (attempt + 1))  # Exponential backoff
                continue
            else:
                # Final attempt failed
                logger.error(f"Exception creating GHL appointment after {MAX_RETRIES} attempts: {str(e)}")
                return {"error": f"Network error: {str(e)[:100]}"}
        
        except Exception as e:
            # Non-retryable exception
            logger.error(f"Exception creating GHL appointment: {str(e)}")
            return {"error": str(e)}
    
    # Should not reach here, but just in case
    return {"error": "Failed after all retry attempts"}
