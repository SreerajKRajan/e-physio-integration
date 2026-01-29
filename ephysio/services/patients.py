import requests
from ephysio.services.headers import get_ephysio_headers
from ephysio.utils import normalize_phone
from ephysio.services.auth import authenticate_ephysio


BASE_URL = "https://ehealth.pharmedsolutions.ch/api/1.0"


def get_active_patients():
    response = requests.get(
        f"{BASE_URL}/patients",
        headers=get_ephysio_headers(),
        params={"status": 1},
        timeout=10
    )

    if response.status_code == 401:
        print("🔐 e-Physio token expired, re-authenticating...")
        authenticate_ephysio()

        response = requests.get(
            f"{BASE_URL}/patients",
            headers=get_ephysio_headers(),
            params={"status": 1},
            timeout=10
        )

    response.raise_for_status()
    return response.json()



def find_patient_by_phone(phone):
    if not phone:
        return None

    target = normalize_phone(phone)
    patients = get_active_patients()

    for patient in patients:
        p_phone = normalize_phone(patient.get("phone"))
        if p_phone == target:
            return patient

    return None

def create_patient(payload):
    print("📤 E-PHYSIO PAYLOAD >>>", payload)
    response = requests.post(
        f"{BASE_URL}/patients/request",
        headers=get_ephysio_headers(),
        json=payload,
        timeout=10
    )

    if response.status_code == 401:
        print("🔐 Token expired during create, re-authenticating...")
        authenticate_ephysio()

        response = requests.post(
            f"{BASE_URL}/patients/request",
            headers=get_ephysio_headers(),
            json=payload,
            timeout=10
        )

    if response.status_code != 200:
        print("❌ STATUS:", response.status_code)
        print("❌ RESPONSE:", response.text)

    response.raise_for_status()
    return response.json()


def sync_ghl_contact_to_ephysio(ghl_data, sync_obj):
    from ephysio.services.patients import find_patient_by_phone, create_patient
    from ephysio.services.payloads import build_patient_payload_from_ghl

    phone = ghl_data.get("phone")

    # 1️⃣ Check patient in e-Physio
    patient = find_patient_by_phone(phone)

    if patient:
        print("🔁 Patient exists in e-Physio, updating link")

        sync_obj.ephysio_patient_id = patient.get("id")
        sync_obj.save()

        # 🔜 Later: update patient API if needed

        return "updated"

    # 2️⃣ Patient NOT found → create
    print("🆕 Patient not found, creating in e-Physio")

    payload = build_patient_payload_from_ghl(ghl_data)
    result = create_patient(payload)

    sync_obj.ephysio_patient_id = result.get("id")
    sync_obj.save()

    return "created"
