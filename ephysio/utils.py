import re

def normalize_phone(phone):
    if not phone:
        return None

    phone = re.sub(r"[^\d+]", "", phone)

    if phone.startswith("+"):
        phone = phone[1:]

    if phone.startswith("41"):
        phone = phone[2:]

    if not phone.startswith("0"):
        phone = "0" + phone

    return phone

def datetime_to_epoch_ms(dt):
    return int(dt.timestamp() * 1000)
