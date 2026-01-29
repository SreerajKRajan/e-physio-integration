def normalize_phone(phone):
    if not phone:
        return None

    phone = phone.replace(" ", "").replace("-", "")

    # Convert +41XXXXXXXXX → 0XXXXXXXXX
    if phone.startswith("+41"):
        phone = "0" + phone[3:]

    return phone

from datetime import date

def build_patient_payload_from_ghl(ghl):
    return {
        # Optional but safe
        "id": str(ghl.get("ghl_contact_id")),

        "firstName": ghl.get("first_name") or "Unknown",
        "lastName": ghl.get("last_name") or "Patient",

        "street": ghl.get("street") or "Unknown",
        "zip": ghl.get("zip") or "0000",
        "city": ghl.get("city") or "Unknown",

        # ✅ MUST be ISO format YYYY-MM-DD
        "birthDate": "1990-01-01",

        # ✅ MUST be 'm' or 'f'
        "sex": "m",

        # ✅ Integer
        "status": 1,

        # ✅ Keep international format (+41...)
        "phone": ghl.get("phone"),

        "email": ghl.get("email"),

        # ✅ Boolean (NOT string)
        "hasEmailConsent": True,

        "comment": "Created from GHL"
    }
