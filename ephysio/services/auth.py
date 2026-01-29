import requests
from django.conf import settings
from ephysio.models import EPhysioAuth

BASE_URL = "https://ehealth.pharmedsolutions.ch/api/1.0"

def authenticate_ephysio():
    response = requests.post(
        f"{BASE_URL}/token",
        json={
            "email": settings.EPHYSIO_EMAIL,
            "password": settings.EPHYSIO_PASSWORD
        },
        timeout=10
    )
    response.raise_for_status()

    data = response.json()

    auth, _ = EPhysioAuth.objects.update_or_create(
        id=1,
        defaults={
            "token": data["token"],
            "crypto_key": data["keys"][0]["key"],
            "practice_id": data["id"],
            "expires_at": data.get("exp")
        }
    )

    return auth
