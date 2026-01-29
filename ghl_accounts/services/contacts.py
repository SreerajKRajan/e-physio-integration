import requests
from ghl_accounts.models import GHLAuthCredentials
from django.conf import settings
from decouple import config
import logging

logger = logging.getLogger(__name__)

GHL_BASE_URL = "https://services.leadconnectorhq.com"
TOKEN_URL = "https://services.leadconnectorhq.com/oauth/token"
GHL_CLIENT_ID = config("GHL_CLIENT_ID")
GHL_CLIENT_SECRET = config("GHL_CLIENT_SECRET")


def refresh_ghl_token():
    """
    Refresh GHL access token using refresh_token.
    
    Returns:
        tuple: (success: bool, message: str)
    """
    auth = GHLAuthCredentials.objects.first()
    
    if not auth:
        logger.error("No GHL authentication credentials found. Please authenticate first.")
        return False, "No authentication credentials found"
    
    if not auth.refresh_token:
        logger.error("No refresh token available. Please re-authenticate manually.")
        return False, "No refresh token available"
    
    try:
        # Prepare refresh token request
        data = {
            "grant_type": "refresh_token",
            "client_id": GHL_CLIENT_ID,
            "client_secret": GHL_CLIENT_SECRET,
            "refresh_token": auth.refresh_token,
        }
        
        logger.info("Refreshing GHL access token...")
        response = requests.post(TOKEN_URL, data=data, timeout=10)
        
        if response.status_code != 200:
            error_text = response.text
            logger.error(f"Failed to refresh GHL token: {response.status_code} - {error_text}")
            return False, f"Token refresh failed: {response.status_code} - {error_text}"
        
        response_data = response.json()
        
        # Update the auth credentials with new tokens
        auth.access_token = response_data.get("access_token")
        auth.refresh_token = response_data.get("refresh_token", auth.refresh_token)  # Keep old if not provided
        auth.expires_in = response_data.get("expires_in", auth.expires_in)
        
        # Update other fields if provided
        if response_data.get("scope"):
            auth.scope = response_data.get("scope")
        if response_data.get("userType"):
            auth.user_type = response_data.get("userType")
        if response_data.get("companyId"):
            auth.company_id = response_data.get("companyId")
        if response_data.get("userId"):
            auth.user_id = response_data.get("userId")
        if response_data.get("locationId"):
            auth.location_id = response_data.get("locationId")
        
        auth.save()
        
        logger.info(f"✅ GHL token refreshed successfully. New token expires in {auth.expires_in} seconds.")
        return True, "Token refreshed successfully"
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Network error while refreshing GHL token: {str(e)}")
        return False, f"Network error: {str(e)}"
    except Exception as e:
        logger.error(f"Unexpected error while refreshing GHL token: {str(e)}", exc_info=True)
        return False, f"Unexpected error: {str(e)}"


def get_ghl_auth():
    """
    Get GHL authentication credentials.
    Returns tuple of (access_token, location_id) or (None, None) if not found.
    """
    auth = GHLAuthCredentials.objects.first()
    
    if not auth:
        logger.error("No GHL authentication credentials found. Please authenticate first.")
        return None, None
    
    if not auth.location_id:
        logger.error("GHL location_id is missing. Please re-authenticate.")
        return None, None
    
    return auth.access_token, auth.location_id


def get_ghl_headers():
    """
    Get headers for GHL API requests.
    """
    access_token, location_id = get_ghl_auth()
    
    if not access_token:
        raise ValueError("GHL access token not available. Please authenticate first.")
    
    return {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Version": "2021-07-28"
    }


def get_ghl_contact(contact_id):
    """
    Get a contact from GHL by contact ID.
    
    Args:
        contact_id: GHL contact ID
    
    Returns:
        dict: Contact data if found, None otherwise
    """
    access_token, location_id = get_ghl_auth()
    
    if not access_token or not location_id:
        return None
    
    headers = get_ghl_headers()
    
    try:
        url = f"{GHL_BASE_URL}/contacts/{contact_id}"
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            result = response.json()
            # GHL API might return contact in 'contact' key or directly
            if 'contact' in result:
                return result['contact']
            return result
        elif response.status_code == 404:
            return None
        else:
            logger.warning(f"Error getting contact {contact_id}: {response.status_code}")
            return None
    except Exception as e:
        logger.error(f"Error getting contact by ID: {str(e)}")
        return None


def create_ghl_contact(contact_data):
    """
    Create a new contact in GHL.
    
    Args:
        contact_data: dict with contact information
    
    Returns:
        dict: Created contact data with ID, or dict with error info if failed
    """
    access_token, location_id = get_ghl_auth()
    
    if not access_token or not location_id:
        logger.error("GHL authentication not available")
        return {"error": "Authentication not available"}
    
    headers = get_ghl_headers()
    
    # Ensure locationId is in the payload
    contact_data['locationId'] = location_id
    
    try:
        url = f"{GHL_BASE_URL}/contacts/"
        response = requests.post(url, json=contact_data, headers=headers, timeout=10)
        
        if response.status_code in [200, 201]:
            result = response.json()
            # GHL API might return contact in 'contact' key or directly
            if 'contact' in result:
                return result
            elif 'id' in result:
                return {'contact': result}
            else:
                return result
        else:
            error_text = response.text
            try:
                error_data = response.json()
                error_message = error_data.get('message', error_text)
            except:
                error_message = error_text
            
            logger.error(f"Error creating GHL contact: {response.status_code} - {error_message}")
            return {"error": error_message, "status_code": response.status_code}
    except Exception as e:
        logger.error(f"Exception creating GHL contact: {str(e)}")
        return {"error": str(e)}


def update_ghl_contact(contact_id, contact_data):
    """
    Update an existing contact in GHL.
    
    Args:
        contact_id: GHL contact ID
        contact_data: dict with contact information to update
    
    Returns:
        dict: Updated contact data, or dict with error if failed
    """
    access_token, location_id = get_ghl_auth()
    
    if not access_token or not location_id:
        logger.error("GHL authentication not available")
        return {"error": "Authentication not available"}
    
    headers = get_ghl_headers()
    
    # Don't include locationId in update (not needed)
    contact_data.pop('locationId', None)
    
    try:
        url = f"{GHL_BASE_URL}/contacts/{contact_id}"
        response = requests.put(url, json=contact_data, headers=headers, timeout=10)
        
        if response.status_code == 200:
            result = response.json()
            # GHL API might return contact in 'contact' key or directly
            if 'contact' in result:
                return result
            elif 'id' in result:
                return {'contact': result}
            else:
                return result
        else:
            error_text = response.text
            try:
                error_data = response.json()
                error_message = error_data.get('message', error_text)
            except:
                error_message = error_text
            
            logger.error(f"Error updating GHL contact {contact_id}: {response.status_code} - {error_message}")
            return {"error": error_message, "status_code": response.status_code}
    except Exception as e:
        logger.error(f"Exception updating GHL contact: {str(e)}")
        return {"error": str(e)}


def validate_and_clean_phone(phone):
    """
    Validate and clean phone number for GHL.
    GHL expects phone numbers in E.164 format (e.g., +1234567890) or valid format.
    
    Args:
        phone: Phone number string
    
    Returns:
        str: Cleaned phone number or None if invalid
    """
    if not phone:
        return None
    
    # Remove all whitespace
    phone = phone.strip().replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
    
    # If it already starts with +, keep it
    if phone.startswith("+"):
        # Validate it has digits after +
        if len(phone) > 1 and phone[1:].replace(" ", "").isdigit():
            return phone
        else:
            return None
    
    # If it starts with 00, replace with +
    if phone.startswith("00"):
        phone = "+" + phone[2:]
        return phone
    
    # If it's a Swiss number (starts with 41 or 0)
    if phone.startswith("41") and len(phone) >= 10:
        return "+" + phone
    elif phone.startswith("0") and len(phone) >= 10:
        # Convert 0XXXXXXXXX to +41XXXXXXXXX
        return "+41" + phone[1:]
    
    # If it's all digits and reasonable length, try to format
    if phone.isdigit() and len(phone) >= 10:
        # Assume it's a valid number, return as is (GHL will validate)
        return phone
    
    # If it doesn't match expected patterns, return None
    # This will cause the phone field to be omitted from payload
    logger.warning(f"Phone number format may be invalid: {phone}")
    return None


def build_ghl_contact_payload(contact_sync):
    """
    Build GHL contact payload from ContactSync model instance.
    
    Args:
        contact_sync: ContactSync model instance
    
    Returns:
        dict: GHL contact payload
    """
    # Build name
    first_name = contact_sync.first_name or ""
    last_name = contact_sync.last_name or ""
    full_name = f"{first_name} {last_name}".strip() or "Unknown"
    
    # Convert birth date from DD.MM.YYYY to YYYY-MM-DD
    date_of_birth = None
    if contact_sync.birth_date:
        try:
            # Parse DD.MM.YYYY format
            parts = contact_sync.birth_date.split('.')
            if len(parts) == 3:
                day, month, year = parts
                date_of_birth = f"{year}-{month.zfill(2)}-{day.zfill(2)}"
        except Exception as e:
            logger.warning(f"Could not parse birth date {contact_sync.birth_date}: {str(e)}")
    
    # NOTE: GHL API doesn't accept 'gender' field in create/update payload
    # Removing it to avoid 422 errors
    # If needed, it might be a custom field that needs to be set differently
    
    # Validate and clean phone number
    phone = validate_and_clean_phone(contact_sync.phone) if contact_sync.phone else None
    
    # Build address - GHL uses address1, city, state, postalCode
    # Note: We have street, zip, city but not state - might need to handle this
    address1 = contact_sync.street or None
    city = contact_sync.city or None
    postal_code = contact_sync.zip or None
    
    payload = {
        "firstName": first_name,
        "lastName": last_name,
        "name": full_name,
        "email": contact_sync.email or None,
        "address1": address1,
        "city": city,
        "postalCode": postal_code,
        # "state": None,  # We don't have state in ephysio data
        # "country": None,  # We don't have country
    }
    
    # Add phone only if it's valid
    if phone:
        payload["phone"] = phone
    
    # Add optional fields only if they exist
    if date_of_birth:
        payload["dateOfBirth"] = date_of_birth
    
    # Remove None values to avoid sending them
    payload = {k: v for k, v in payload.items() if v is not None}
    
    return payload
