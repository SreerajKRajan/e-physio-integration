# Celery Setup Guide - Periodic Patient Sync

## Overview

This guide explains how to set up Celery for periodic syncing of patients from e-Physio to GHL. The system will automatically fetch new/updated patients every hour and sync them to GHL.

## What Was Implemented

### 1. **Celery Configuration**
   - ✅ `e_physio_integration/celery.py` - Celery app configuration
   - ✅ Updated `settings.py` with Celery settings
   - ✅ Configured Redis as message broker and result backend

### 2. **Celery Task**
   - ✅ `ghl_accounts/tasks.py` - `sync_patients_incremental` task
   - ✅ Fetches all active patients from e-Physio
   - ✅ Compares with existing ContactSync records
   - ✅ Creates/updates ContactSync records
   - ✅ Automatically syncs new patients to GHL

### 3. **Periodic Task Setup**
   - ✅ Management command to set up periodic tasks
   - ✅ Configured to run every hour

## Prerequisites

### 1. Install Dependencies

```bash
pip install celery redis django-celery-beat
```

Or add to `requirements.txt`:
```
celery==5.3.4
redis==5.0.1
django-celery-beat==2.5.0
```

### 2. Install and Start Redis

**Windows:**
- Download Redis from: https://github.com/microsoftarchive/redis/releases
- Or use WSL: `wsl sudo apt-get install redis-server`
- Start Redis: `redis-server`

**Linux/Mac:**
```bash
sudo apt-get install redis-server  # Ubuntu/Debian
brew install redis                  # Mac
redis-server                        # Start Redis
```

**Verify Redis is running:**
```bash
redis-cli ping
# Should return: PONG
```

### 3. Run Database Migrations

```bash
python manage.py migrate
```

This will create the `django_celery_beat` tables for storing periodic task schedules.

## Setup Steps

### Step 1: Set Up Periodic Task

```bash
python manage.py setup_periodic_tasks
```

This command will:
- Create an interval schedule (every 1 hour)
- Create/update the periodic task for patient sync
- Enable the task

### Step 2: Start Celery Worker

In one terminal:

```bash
celery -A e_physio_integration worker --loglevel=info
```

### Step 3: Start Celery Beat (Scheduler)

In another terminal:

```bash
celery -A e_physio_integration beat --loglevel=info
```

**Or run both together:**

```bash
celery -A e_physio_integration worker --beat --loglevel=info
```

## How It Works

1. **Every Hour:**
   - Celery Beat triggers the `sync_patients_incremental` task
   
2. **Task Execution:**
   - Fetches all active patients from e-Physio API
   - Compares with existing `ContactSync` records by `ephysio_patient_id`
   - Creates new `ContactSync` records for new patients
   - Updates existing `ContactSync` records if patient data changed
   - For patients without `ghl_contact_id`, syncs them to GHL
   - Updates `ghl_contact_id` after successful GHL sync

3. **Logging:**
   - All operations are logged
   - Check logs for sync status and any errors

## Monitoring

### Check Task Status

```bash
# Using Django shell
python manage.py shell
```

```python
from django_celery_beat.models import PeriodicTask
from ghl_accounts.models import ContactSync

# Check periodic task status
task = PeriodicTask.objects.get(name='Sync Patients from e-Physio to GHL (Hourly)')
print(f"Task enabled: {task.enabled}")
print(f"Last run: {task.last_run_at}")
print(f"Next run: task.schedule.remaining_estimate(task.last_run_at)")

# Check recent syncs
recent = ContactSync.objects.filter(
    source='ephysio'
).order_by('-last_synced_at')[:10]
for contact in recent:
    print(f"{contact.first_name} {contact.last_name} - Synced: {contact.last_synced_at}")
```

### View Celery Logs

The Celery worker and beat processes will show:
- Task execution logs
- Success/failure messages
- Error details if any

### Disable/Enable Periodic Task

```python
from django_celery_beat.models import PeriodicTask

task = PeriodicTask.objects.get(name='Sync Patients from e-Physio to GHL (Hourly)')
task.enabled = False  # Disable
task.save()

task.enabled = True   # Enable
task.save()
```

Or use Django admin:
- Go to `/admin/django_celery_beat/periodictask/`
- Find the task and toggle the "Enabled" checkbox

## Configuration

### Change Sync Frequency

To change from hourly to every 30 minutes:

```python
from django_celery_beat.models import PeriodicTask, IntervalSchedule

# Create 30-minute schedule
schedule, _ = IntervalSchedule.objects.get_or_create(
    every=30,
    period=IntervalSchedule.MINUTES,
)

# Update task
task = PeriodicTask.objects.get(name='Sync Patients from e-Physio to GHL (Hourly)')
task.interval = schedule
task.save()
```

### Redis Configuration

If Redis is not on localhost or uses a different port, update `settings.py`:

```python
CELERY_BROKER_URL = 'redis://your-redis-host:6379/0'
CELERY_RESULT_BACKEND = 'redis://your-redis-host:6379/0'
```

## Troubleshooting

### Redis Connection Error

```
Error: [Errno 111] Connection refused
```

**Solution:** Make sure Redis is running:
```bash
redis-cli ping
```

### Task Not Running

1. Check if Celery Beat is running
2. Check if the periodic task is enabled:
   ```python
   from django_celery_beat.models import PeriodicTask
   task = PeriodicTask.objects.get(name='Sync Patients from e-Physio to GHL (Hourly)')
   print(task.enabled)
   ```
3. Check Celery logs for errors

### Task Running But No Sync Happening

1. Check e-Physio API connectivity
2. Check GHL authentication (`GHLAuthCredentials` must exist)
3. Check task logs for specific error messages

### Database Lock Errors

If you see database lock errors, reduce concurrency:
```bash
celery -A e_physio_integration worker --concurrency=2 --loglevel=info
```

## Production Deployment

For production, use a process manager like **supervisor** or **systemd**:

### Supervisor Example (`/etc/supervisor/conf.d/celery.conf`):

```ini
[program:celery_worker]
command=/path/to/venv/bin/celery -A e_physio_integration worker --loglevel=info
directory=/path/to/project
user=www-data
autostart=true
autorestart=true
redirect_stderr=true
stdout_logfile=/var/log/celery/worker.log

[program:celery_beat]
command=/path/to/venv/bin/celery -A e_physio_integration beat --loglevel=info
directory=/path/to/project
user=www-data
autostart=true
autorestart=true
redirect_stderr=true
stdout_logfile=/var/log/celery/beat.log
```

## Next Steps

After setting up patient sync, you can:
1. Set up appointment sync (similar pattern)
2. Add error notifications (email/Slack)
3. Add monitoring dashboards
4. Set up task retries for failed syncs

## Summary

✅ **Celery configured** with Redis  
✅ **Periodic task created** (runs every hour)  
✅ **Automatic patient sync** from e-Physio → ContactSync → GHL  
✅ **Management command** to set up tasks easily  

The system will now automatically keep patients in sync every hour!
