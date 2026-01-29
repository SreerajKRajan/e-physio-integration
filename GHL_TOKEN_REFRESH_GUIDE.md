# GHL Token Refresh - Automatic Implementation

## ✅ Implementation Complete

The GHL token refresh has been automatically implemented using Celery. The system will now automatically refresh GHL access tokens every **20 hours** to prevent expiration (tokens expire in 24 hours).

---

## 🔧 What Was Implemented

### 1. **Token Refresh Function**
- **Location**: `ghl_accounts/services/contacts.py`
- **Function**: `refresh_ghl_token()`
- **Purpose**: Uses the stored `refresh_token` to get a new `access_token` from GHL
- **Returns**: `(success: bool, message: str)`

### 2. **Celery Task**
- **Location**: `ghl_accounts/tasks.py`
- **Task Name**: `refresh_ghl_token_periodic`
- **Schedule**: Every 20 hours
- **Purpose**: Automatically calls `refresh_ghl_token()` to keep tokens fresh

### 3. **Periodic Task Setup**
- **Location**: `ghl_accounts/management/commands/setup_periodic_tasks.py`
- **Updated**: Now includes token refresh task setup
- **Schedule**: 20-hour interval

---

## 🚀 Setup Instructions

### Step 1: Run the Setup Command

```bash
cd e_physio_integration
python manage.py setup_periodic_tasks
```

This will create/update all periodic tasks including:
- Patient sync (every 1 hour)
- Appointment sync (every 1 hour)
- **Token refresh (every 20 hours)** ← NEW!

### Step 2: Verify Tasks Are Created

Check that the token refresh task is registered:

```bash
python manage.py shell
```

```python
from django_celery_beat.models import PeriodicTask
token_task = PeriodicTask.objects.filter(name__icontains='token').first()
print(f"Task: {token_task.name}")
print(f"Enabled: {token_task.enabled}")
print(f"Schedule: Every {token_task.interval.every} {token_task.interval.period}")
```

### Step 3: Start Celery Services

Make sure Celery Worker and Beat are running:

**Terminal 1 - Celery Worker:**
```bash
celery -A e_physio_integration worker --pool=solo --loglevel=info
```

**Terminal 2 - Celery Beat:**
```bash
celery -A e_physio_integration beat --loglevel=info
```

---

## 🧪 Testing the Token Refresh

### Option 1: Manual Test (Immediate)

Test the refresh function directly:

```bash
python manage.py shell
```

```python
from ghl_accounts.services.contacts import refresh_ghl_token
success, message = refresh_ghl_token()
print(f"Success: {success}")
print(f"Message: {message}")
```

### Option 2: Test via Celery Task (Immediate)

Test the Celery task:

```python
from ghl_accounts.tasks import refresh_ghl_token_periodic
result = refresh_ghl_token_periodic()
print(result)
```

### Option 3: Test via Celery (Async)

Test the task asynchronously:

```python
from ghl_accounts.tasks import refresh_ghl_token_periodic
task = refresh_ghl_token_periodic.delay()
print(f"Task ID: {task.id}")
# Check result later
result = task.get()
print(result)
```

### Option 4: Test with Shorter Interval (For Testing)

For testing purposes, you can temporarily set a shorter interval:

```bash
python manage.py shell
```

```python
from django_celery_beat.models import PeriodicTask, IntervalSchedule

# Create a 30-second interval for testing
test_schedule, _ = IntervalSchedule.objects.get_or_create(
    every=30,
    period=IntervalSchedule.SECONDS
)

# Update the token refresh task
token_task = PeriodicTask.objects.get(name='Refresh GHL Access Token (Every 20 Hours)')
token_task.interval = test_schedule
token_task.save()

print("Token refresh task updated to run every 30 seconds for testing")
```

**Remember to change it back to 20 hours after testing!**

---

## 📊 Monitoring

### Check Task Execution Logs

Watch the Celery worker logs for token refresh activity:

```
[INFO] Starting GHL token refresh task...
[INFO] Refreshing GHL access token...
[INFO] ✅ GHL token refreshed successfully. New token expires in 86400 seconds.
[INFO] GHL token refresh completed: {'status': 'success', ...}
```

### Check Token Status

Verify the token was refreshed in the database:

```python
from ghl_accounts.models import GHLAuthCredentials
auth = GHLAuthCredentials.objects.first()
print(f"Access Token: {auth.access_token[:20]}...")
print(f"Expires In: {auth.expires_in} seconds")
print(f"Last Updated: {auth.updated_at if hasattr(auth, 'updated_at') else 'N/A'}")
```

---

## ⚠️ Important Notes

1. **Initial Authentication Required**: You must authenticate once manually via `/api/auth/connect` before the automatic refresh can work.

2. **Refresh Token Must Exist**: The system needs a valid `refresh_token` in the database. If the refresh token expires or is invalid, you'll need to re-authenticate manually.

3. **Error Handling**: If token refresh fails, the task will log the error but won't crash. Check logs regularly to ensure tokens are being refreshed successfully.

4. **20-Hour Schedule**: The task runs every 20 hours, which is 4 hours before the 24-hour expiration. This provides a safety buffer.

5. **Multiple Locations**: If you have multiple GHL locations, the system uses the first `GHLAuthCredentials` record. Make sure the correct one is first if needed.

---

## 🔍 Troubleshooting

### Token Refresh Fails

**Error**: "No refresh token available"
- **Solution**: Re-authenticate manually via `/api/auth/connect`

**Error**: "Token refresh failed: 401"
- **Solution**: The refresh token may have expired. Re-authenticate manually.

**Error**: "Network error"
- **Solution**: Check internet connection and GHL API availability.

### Task Not Running

1. **Check Celery Beat is running**: `celery -A e_physio_integration beat --loglevel=info`
2. **Check task is enabled**: Verify in Django admin or via shell
3. **Check Redis is running**: Token refresh requires Redis for Celery

---

## ✅ Verification Checklist

- [ ] Token refresh function implemented (`refresh_ghl_token()`)
- [ ] Celery task created (`refresh_ghl_token_periodic`)
- [ ] Periodic task set up (every 20 hours)
- [ ] Celery Worker running
- [ ] Celery Beat running
- [ ] Initial authentication completed
- [ ] Token refresh tested manually
- [ ] Task appears in Celery Beat schedule

---

## 📝 Summary

✅ **Automatic token refresh is now active!**

The system will automatically refresh GHL tokens every 20 hours, ensuring your integration never loses access due to expired tokens. No manual intervention needed after initial setup!

---

**Last Updated**: January 30, 2026
