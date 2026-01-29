from decouple import config
import requests
from django.http import JsonResponse
import json
from django.shortcuts import redirect
from ghl_accounts.models import GHLAuthCredentials
from django.views.decorators.csrf import csrf_exempt
import logging
from django.views import View
from django.utils.decorators import method_decorator
import traceback
from ephysio.services.patients import sync_ghl_contact_to_ephysio

logger = logging.getLogger(__name__)


GHL_CLIENT_ID = config("GHL_CLIENT_ID")
GHL_CLIENT_SECRET = config("GHL_CLIENT_SECRET")
GHL_REDIRECTED_URI = config("GHL_REDIRECTED_URI")
TOKEN_URL = "https://services.leadconnectorhq.com/oauth/token"
SCOPE = config("SCOPE")

def auth_connect(request):
    auth_url = ("https://marketplace.gohighlevel.com/oauth/chooselocation?response_type=code&"
                f"redirect_uri={GHL_REDIRECTED_URI}&"
                f"client_id={GHL_CLIENT_ID}&"
                f"scope={SCOPE}"
                )
    return redirect(auth_url)



def callback(request):
    
    code = request.GET.get('code')

    if not code:
        return JsonResponse({"error": "Authorization code not received from OAuth"}, status=400)
    

    return redirect(f'{config("BASE_URI")}/api/auth/tokens?code={code}')


def tokens(request):
    authorization_code = request.GET.get("code")

    if not authorization_code:
        return JsonResponse({"error": "Authorization code not found"}, status=400)

    data = {
        "grant_type": "authorization_code",
        "client_id": GHL_CLIENT_ID,
        "client_secret": GHL_CLIENT_SECRET,
        "redirect_uri": GHL_REDIRECTED_URI,
        "code": authorization_code,
    }

    response = requests.post(TOKEN_URL, data=data)

    try:
        response_data = response.json()
        if not response_data:
            return

        obj, created = GHLAuthCredentials.objects.update_or_create(
            location_id= response_data.get("locationId"),
            defaults={
                "access_token": response_data.get("access_token"),
                "refresh_token": response_data.get("refresh_token"),
                "expires_in": response_data.get("expires_in"),
                "scope": response_data.get("scope"),
                "user_type": response_data.get("userType"),
                "company_id": response_data.get("companyId"),
                "user_id":response_data.get("userId"),

            }
        )
        return JsonResponse({
            "message": "Authentication successful",
            "access_token": response_data.get('access_token'),
            "token_stored": True
        })
        
    except requests.exceptions.JSONDecodeError:
        return JsonResponse({
            "error": "Invalid JSON response from API",
            "status_code": response.status_code,
            "response_text": response.text[:500]
        }, status=500)
        
        
import json
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from .models import ContactSync, AppointmentSync


@csrf_exempt
def ghl_webhook(request):
    if request.method != "POST":
        return JsonResponse({"error": "Invalid request method"}, status=405)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    event_type = data.get("type")
    print("🔥 GHL EVENT RECEIVED:", event_type)

    if not event_type:
        return JsonResponse({"error": "Missing event type"}, status=400)

    # -------------------------
    # ROUTING BY EVENT TYPE
    # -------------------------
    if event_type in ["ContactCreate", "ContactUpdate"]:
        return handle_contact_event(data)

    if event_type in ["AppointmentCreate", "AppointmentUpdate"]:
        return handle_appointment_event(data)

    print("⚠️ Unhandled GHL event:", event_type)
    return JsonResponse({"status": "ignored"})


def handle_contact_event(data):
    ghl_contact_id = data.get("id")
    email = data.get("email")
    phone = data.get("phone")
    first_name = data.get("firstName")
    last_name = data.get("lastName")

    if not ghl_contact_id:
        return JsonResponse({"error": "Missing contact id"}, status=400)

    sync = ContactSync.objects.filter(
        ghl_contact_id=ghl_contact_id
    ).first()

    if sync:
        print("✅ Contact already synced")
        sync.email = email
        sync.phone = phone
        sync.save()
    else:
        print("🆕 New contact")
        sync = ContactSync.objects.create(
            ghl_contact_id=ghl_contact_id,
            email=email,
            phone=phone,
            source="ghl"
        )

    sync_ghl_contact_to_ephysio({
        "ghl_contact_id": ghl_contact_id,
        "first_name": first_name,
        "last_name": last_name,
        "phone": phone,
        "email": email
    }, sync)

    return JsonResponse({"status": "contact synced"})

from django.http import JsonResponse
from django.utils.dateparse import parse_datetime
from .models import AppointmentSync, ContactSync
from ephysio.services.appointments import create_ephysio_appointment

def handle_appointment_event(data):
    print("📦 RAW APPOINTMENT PAYLOAD >>>", data)

    appointment = data.get("appointment", {})

    ghl_appointment_id = appointment.get("id")
    ghl_contact_id = appointment.get("contactId")

    start_time = parse_datetime(appointment.get("startTime"))
    end_time = parse_datetime(appointment.get("endTime"))
    status = appointment.get("appointmentStatus")

    if not ghl_appointment_id or not ghl_contact_id:
        return JsonResponse({"error": "Missing appointment or contact ID"}, status=400)

    if not start_time or not end_time:
        return JsonResponse({"error": "Invalid start/end time"}, status=400)

    # find synced patient
    contact_sync = ContactSync.objects.filter(
        ghl_contact_id=ghl_contact_id
    ).first()

    if not contact_sync:
        return JsonResponse({"error": "Patient not synced yet"}, status=400)

    appt_sync = AppointmentSync.objects.filter(
        ghl_appointment_id=ghl_appointment_id
    ).first()

    if appt_sync:
        print("🔁 Appointment already exists – skipping create")
        return JsonResponse({"status": "already exists"})

    print("🆕 Creating appointment")

    appt_sync = AppointmentSync.objects.create(
        ghl_appointment_id=ghl_appointment_id,
        ghl_contact_id=ghl_contact_id,
        ephysio_patient_id=contact_sync.ephysio_patient_id,
        start_time=start_time,
        end_time=end_time,
        status=status,
        source="ghl"  # Set source as 'ghl' since it's created from GHL webhook
    )

    sync_ghl_appointment_to_ephysio_create(appt_sync)

    return JsonResponse({"status": "appointment created"})

def sync_ghl_appointment_to_ephysio_create(appt_sync):
    print("📡 SYNC TO E-PHYSIO (CREATE)")
    try:
        result = create_ephysio_appointment(appt_sync)

        # Extract event ID from response
        # Response structure: {"id": 42109222, "events": [], ...}
        event_id = result.get("id")
        
        # Also check if ID is in events array (if present)
        if not event_id and result.get("events"):
            events = result.get("events", [])
            if events and len(events) > 0:
                event_id = events[0].get("id")
        
        if event_id:
            appt_sync.ephysio_appointment_id = str(event_id)
            appt_sync.save()
            print(f"✅ Appointment created in e-Physio with ID: {event_id}")
        else:
            print("⚠️ Warning: No event ID in response from e-Physio")
            print(f"Response: {result}")
            
    except Exception as e:
        print(f"❌ Error creating appointment in e-Physio: {str(e)}")
        # Don't raise - allow webhook to return success even if e-Physio creation fails
        # The appointment is already saved in our database
