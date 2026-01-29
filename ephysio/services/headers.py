from ephysio.services.auth import authenticate_ephysio
from ephysio.models import EPhysioAuth

def get_ephysio_headers():
    auth = EPhysioAuth.objects.first()

    if not auth:
        auth = authenticate_ephysio()

    return {
        "Authorization": f"Bearer {auth.token}",
        "X-CRYPTO-KEY": auth.crypto_key,
        "Content-Type": "application/json"
    }
