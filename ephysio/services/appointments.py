import requests
from ephysio.services.headers import get_ephysio_headers
from ephysio.services.auth import authenticate_ephysio
from ephysio.utils import datetime_to_epoch_ms
from datetime import datetime, timezone
from django.utils import timezone as django_timezone

BASE_URL = "https://ehealth.pharmedsolutions.ch/api/1.0"
EVENT_GET_URL = f"{BASE_URL}/events/events"  # For GET requests
EVENT_CREATE_URL = f"{BASE_URL}/events"  # For POST requests (actual endpoint from screenshots)
INVOICE_CREATE_URL = f"{BASE_URL}/invoices"  # For creating invoices

def get_or_create_invoice(patient_id, appointment_date):
    """
    Get existing invoice for patient or create a new one.
    
    Args:
        patient_id: e-Physio patient ID
        appointment_date: Appointment date (datetime object, should be UTC)
    
    Returns:
        int: Invoice ID
    """
    # Ensure appointment_date is UTC
    if django_timezone.is_naive(appointment_date):
        invoice_dt = appointment_date.replace(tzinfo=timezone.utc)
    else:
        invoice_dt = appointment_date.astimezone(timezone.utc)
    
    # Use the date part (set to a specific time like 18:30:00 UTC as seen in screenshots)
    # The invoice date should be the date of the appointment, not the exact time
    invoice_date_iso = invoice_dt.strftime("%Y-%m-%dT18:30:00.000Z")
    invoice_date_epoch = datetime_to_epoch_ms(invoice_dt.replace(hour=18, minute=30, second=0, microsecond=0))
    
    # First, try to get existing open invoices for the patient
    # Based on screenshot: GET /api/1.0/invoices/patients/{patientId}?open=true&date={timestamp}
    # Also try without date parameter to get all open invoices
    try:
        print(f"🔍 Checking for existing open invoices for patient {patient_id}...")
        
        # Try with date parameter first (as seen in screenshot)
        get_response = requests.get(
            f"{INVOICE_CREATE_URL}/patients/{patient_id}",
            headers=get_ephysio_headers(),
            params={
                "open": "true",
                "date": invoice_date_epoch
            },
            timeout=10
        )
        
        if get_response.status_code == 401:
            print("🔐 e-Physio token expired, re-authenticating...")
            authenticate_ephysio()
            get_response = requests.get(
                f"{INVOICE_CREATE_URL}/patients/{patient_id}",
                headers=get_ephysio_headers(),
                params={
                    "open": "true",
                    "date": invoice_date_epoch
                },
                timeout=10
            )
        
        if get_response.status_code == 200:
            invoices = get_response.json()
            print(f"📥 Invoice GET response: {invoices}")
            
            # Response might be a list or a single object
            if isinstance(invoices, list) and len(invoices) > 0:
                # Find open invoice (status 0 = open, not sent)
                open_invoice = next(
                    (inv for inv in invoices 
                     if inv.get("stati", {}).get("status") == 0 and 
                        inv.get("stati", {}).get("statusDetail") == 0),
                    None
                )
                if open_invoice:
                    invoice_id = open_invoice.get("id")
                    print(f"✅ Found existing open invoice: {invoice_id}")
                    return invoice_id
                else:
                    # If no open invoice, try any invoice with status 0
                    any_invoice = next(
                        (inv for inv in invoices if inv.get("stati", {}).get("status") == 0),
                        invoices[0] if invoices else None
                    )
                    if any_invoice:
                        invoice_id = any_invoice.get("id")
                        print(f"✅ Found existing invoice (may not be fully open): {invoice_id}")
                        return invoice_id
            elif isinstance(invoices, dict):
                # Single invoice object
                if invoices.get("id"):
                    invoice_id = invoices.get("id")
                    print(f"✅ Found existing invoice: {invoice_id}")
                    return invoice_id
        else:
            print(f"⚠️ GET invoices returned status {get_response.status_code}: {get_response.text}")
            
        # If date parameter didn't work, try without date
        print(f"🔍 Trying to get invoices without date parameter...")
        get_response2 = requests.get(
            f"{INVOICE_CREATE_URL}/patients/{patient_id}",
            headers=get_ephysio_headers(),
            params={"open": "true"},
            timeout=10
        )
        
        if get_response2.status_code == 200:
            invoices = get_response2.json()
            if isinstance(invoices, list) and len(invoices) > 0:
                open_invoice = next(
                    (inv for inv in invoices if inv.get("stati", {}).get("status") == 0),
                    invoices[0]
                )
                if open_invoice:
                    invoice_id = open_invoice.get("id")
                    print(f"✅ Found existing open invoice (without date filter): {invoice_id}")
                    return invoice_id
                    
    except Exception as e:
        print(f"⚠️ Could not check for existing invoices: {str(e)}")
        import traceback
        traceback.print_exc()
        # Continue to try creating new invoice
        pass
    
    # If no existing invoice found, we need to create one
    # But since invoice creation API structure is unclear, let's try a minimal approach
    # OR raise an error asking user to create invoice manually
    print(f"⚠️ No existing open invoice found for patient {patient_id}")
    print(f"⚠️ Invoice creation requires exact payload structure")
    print(f"⚠️ For now, raising error - invoice may need to be created manually in e-Physio")
    
    # Try to create invoice with minimal payload (might fail, but worth trying)
    # Based on error, we know /street is required - but exact structure unknown
    invoice_payload = {
        "user_id": 0,
        "patientId": int(patient_id),
        "dateDate": invoice_date_iso,
        "adminInfoId": 5770,
        "attributes": {
            "date": invoice_date_epoch,
            "law": "kvg",
            "treatmentCause": "disease",
            "isTiersPayant": True,
            "vat": False
        },
        "prescription": {
            "sessions": 9,
            "firstSession": 1
        },
        "stati": {
            "status": 0,
            "statusDetail": 0
        }
    }
    
    print(f"📤 Attempting to create invoice for patient {patient_id}...")
    print(f"📤 Invoice payload: {invoice_payload}")
    
    response = requests.post(
        INVOICE_CREATE_URL,
        json=invoice_payload,
        headers=get_ephysio_headers(),
        timeout=10
    )
    
    if response.status_code == 401:
        print("🔐 e-Physio token expired, re-authenticating...")
        authenticate_ephysio()
        response = requests.post(
            INVOICE_CREATE_URL,
            json=invoice_payload,
            headers=get_ephysio_headers(),
            timeout=10
        )
    
    if response.status_code != 200:
        error_text = response.text
        print(f"❌ Error creating invoice: {response.status_code} - {error_text}")
        # Don't raise - return None so appointment creation can continue without invoice
        # The appointment API will give a clearer error
        return None
    
    result = response.json()
    invoice_id = result.get("id") or result.get("invoice")
    
    if invoice_id:
        print(f"✅ Invoice created: {invoice_id}")
        return invoice_id
    else:
        print(f"⚠️ No invoice ID in response: {result}")
        return None


def create_ephysio_appointment(appt_sync):
    client_id = 5778  # From actual API payload
    
    # First, get or create invoice (required by API)
    invoice_id = get_or_create_invoice(
        appt_sync.ephysio_patient_id,
        appt_sync.start_time
    )
    
    if not invoice_id:
        # If we couldn't get/create invoice, we can't create the appointment
        # The API requires an invoice for appointments with treatment templates
        raise ValueError(
            "Cannot create appointment: No invoice found or created. "
            "Please ensure the patient has an open invoice in e-Physio, "
            "or provide the exact invoice creation API payload structure."
        )
    
    # Ensure datetimes are timezone-aware (UTC)
    # GHL sends times in UTC (ending with Z), so parse_datetime should already be timezone-aware
    # Convert to UTC timezone (Python's datetime.timezone.utc)
    if django_timezone.is_naive(appt_sync.start_time):
        # If naive, make it aware as UTC
        start_dt = appt_sync.start_time.replace(tzinfo=timezone.utc)
    else:
        # Convert to UTC if timezone-aware (handles any timezone)
        start_dt = appt_sync.start_time.astimezone(timezone.utc)
    
    if django_timezone.is_naive(appt_sync.end_time):
        # If naive, make it aware as UTC
        end_dt = appt_sync.end_time.replace(tzinfo=timezone.utc)
    else:
        # Convert to UTC if timezone-aware (handles any timezone)
        end_dt = appt_sync.end_time.astimezone(timezone.utc)
    
    # Convert datetime to required formats
    start_epoch = datetime_to_epoch_ms(start_dt)
    end_epoch = datetime_to_epoch_ms(end_dt)
    
    # Format dates as ISO strings (UTC) - must be in UTC
    start_date_iso = start_dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")
    end_date_iso = end_dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")
    
    # Extract hours and minutes as strings (2 digits) - in UTC
    start_hours = start_dt.strftime("%H")
    start_minutes = start_dt.strftime("%M")
    end_hours = end_dt.strftime("%H")
    end_minutes = end_dt.strftime("%M")
    
    # Payload structure matching the EXACT API payload from your screenshots
    payload = {
        "user_id": 0,
        "patientId": int(appt_sync.ephysio_patient_id),
        "eventTypeId": 29330,
        "clientId": client_id,
        "adminInfoId": 5770,
        "hasPresenceAdminInfo": False,
        "start": start_epoch,
        "end": end_epoch,
        "startDate": start_date_iso,
        "endDate": end_date_iso,
        "startDateHours": start_hours,
        "startDateMinutes": start_minutes,
        "endDateHours": end_hours,
        "endDateMinutes": end_minutes,
        "resourceIds": [f"c-{client_id}"],
        "sendReminder": False,
        "hasSmsReminder": False,
        "isSerialEvent": False,
        "newPatient": False,
        "reminderSent": False,
        "hasValidationErrors": False,
        "eventMetadata": {},
        "status": 5
    }
    
    # Add invoiceId if we have it (required by API)
    if invoice_id:
        payload["invoiceId"] = invoice_id

    print("📤 E-PHYSIO APPOINTMENT PAYLOAD >>>", payload)
    print(f"📤 E-PHYSIO ENDPOINT >>> {EVENT_CREATE_URL}")
    
    # Query parameters as seen in the working UI request
    query_params = {
        "ids": "",
        "isCancelMultiUser": "false",
        "changeSeries": "false",
        "changeAllDescriptions": "false"
    }
    print(f"📤 QUERY PARAMS >>> {query_params}")

    # Use query parameters (as seen in screenshots - this is what works in UI)
    # The screenshots showed POST to /events with query params returning 200 OK
    response = requests.post(
        EVENT_CREATE_URL,
        json=payload,
        headers=get_ephysio_headers(),
        params=query_params,
        timeout=10
    )

    if response.status_code == 401:
        print("🔐 e-Physio token expired, re-authenticating...")
        authenticate_ephysio()
        
        response = requests.post(
            EVENT_CREATE_URL,
            json=payload,
            headers=get_ephysio_headers(),
            timeout=10
        )

    print("📥 RESPONSE:", response.status_code, response.text)
    
    if response.status_code != 200:
        print("❌ STATUS:", response.status_code)
        print("❌ RESPONSE:", response.text)
        # Try to parse error details
        try:
            error_data = response.json()
            print(f"❌ ERROR DETAILS: {error_data}")
            if 'DETAIL' in error_data:
                print(f"❌ DETAIL: {error_data.get('DETAIL')}")
            if 'message' in error_data:
                print(f"❌ MESSAGE: {error_data.get('message')}")
        except:
            pass
    
    response.raise_for_status()

    return response.json()


def get_ephysio_appointments(from_timestamp, to_timestamp):
    """
    Fetch appointments/events from ephysio API.
    
    Args:
        from_timestamp: Start timestamp in milliseconds (epoch ms). Required.
        to_timestamp: End timestamp in milliseconds (epoch ms). Required.
    
    Returns:
        list: List of appointment/event dictionaries
    """
    if from_timestamp is None or to_timestamp is None:
        raise ValueError("from_timestamp and to_timestamp are required")
    
    params = {
        "from": from_timestamp,
        "to": to_timestamp
    }
    
    response = requests.get(
        EVENT_GET_URL,
        headers=get_ephysio_headers(),
        params=params,
        timeout=30
    )
    
    if response.status_code == 401:
        print("🔐 e-Physio token expired, re-authenticating...")
        authenticate_ephysio()
        
        response = requests.get(
            EVENT_GET_URL,
            headers=get_ephysio_headers(),
            params=params,
            timeout=30
        )
    
    response.raise_for_status()
    return response.json()


def epoch_ms_to_datetime(epoch_ms):
    """
    Convert epoch milliseconds to datetime.
    
    Args:
        epoch_ms: Timestamp in milliseconds
    
    Returns:
        datetime: Python datetime object
    """
    if not epoch_ms:
        return None
    return datetime.fromtimestamp(epoch_ms / 1000.0)
