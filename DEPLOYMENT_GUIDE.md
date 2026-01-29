# 🚀 Complete Deployment Guide

This guide covers everything you need to deploy and run the e-Physio ↔ GHL integration system in production.

---

## 📋 Table of Contents

1. [Prerequisites](#prerequisites)
2. [Environment Setup](#environment-setup)
3. [Database Setup](#database-setup)
4. [Redis Setup](#redis-setup)
5. [Initial Configuration](#initial-configuration)
6. [Running the Application](#running-the-application)
7. [Celery Setup](#celery-setup)
8. [Production Deployment](#production-deployment)
9. [Monitoring & Maintenance](#monitoring--maintenance)
10. [Troubleshooting](#troubleshooting)

---

## 1. Prerequisites

### Required Software

- **Python 3.8+**
- **PostgreSQL** (Database)
- **Redis** (Message broker for Celery)
- **Git** (Version control)

### Python Packages

All packages are listed in `requirements.txt`. Install with:

```bash
pip install -r requirements.txt
```

Key packages:
- Django
- celery
- redis
- django-celery-beat
- psycopg2-binary (PostgreSQL adapter)
- requests
- python-decouple

---

## 2. Environment Setup

### Step 1: Clone/Download Project

```bash
cd /path/to/your/project
# Or if using git:
git clone <repository-url>
cd e-physio_integration
```

### Step 2: Create Virtual Environment

**Windows:**
```bash
python -m venv venv
venv\Scripts\activate
```

**Linux/Mac:**
```bash
python3 -m venv venv
source venv/bin/activate
```

### Step 3: Install Dependencies

```bash
pip install -r requirements.txt
```

### Step 4: Environment Variables

Create a `.env` file in the project root with:

```env
# Django Settings
SECRET_KEY=your-secret-key-here
DEBUG=False
ALLOWED_HOSTS=your-domain.com,127.0.0.1

# Database
DB_NAME=your_db_name
DB_USER=your_db_user
DB_PASSWORD=your_db_password
DB_HOST=localhost
DB_PORT=5432

# GHL OAuth
GHL_CLIENT_ID=your_ghl_client_id
GHL_CLIENT_SECRET=your_ghl_client_secret
GHL_REDIRECTED_URI=https://your-domain.com/api/auth/callback
SCOPE=your_ghl_scope

# e-Physio API
EPHYSIO_API_URL=https://ehealth.pharmedsolutions.ch/api/1.0
EPHYSIO_USERNAME=your_ephysio_username
EPHYSIO_PASSWORD=your_ephysio_password

# Base URI (for OAuth redirects)
BASE_URI=https://your-domain.com

# Redis (if different from default)
REDIS_URL=redis://localhost:6379/0
```

---

## 3. Database Setup

### Step 1: Create PostgreSQL Database

```bash
# Connect to PostgreSQL
psql -U postgres

# Create database
CREATE DATABASE your_db_name;

# Create user (optional)
CREATE USER your_db_user WITH PASSWORD 'your_db_password';
GRANT ALL PRIVILEGES ON DATABASE your_db_name TO your_db_user;
\q
```

### Step 2: Run Migrations

```bash
cd e_physio_integration
python manage.py migrate
```

This creates all necessary tables:
- `ghl_accounts_ghlauthcredentials`
- `ghl_accounts_contactsync`
- `ghl_accounts_appointmentsync`
- `django_celery_beat_*` (for periodic tasks)

---

## 4. Redis Setup

### Windows

**Option 1: WSL (Recommended)**
```bash
# In WSL terminal
sudo apt update
sudo apt install redis-server
redis-server
```

**Option 2: Windows Service**
- Download Redis for Windows
- Install as Windows Service
- Start the service

**Option 3: Docker**
```bash
docker run -d -p 6379:6379 redis:latest
```

### Linux/Mac

```bash
# Ubuntu/Debian
sudo apt update
sudo apt install redis-server
sudo systemctl start redis-server
sudo systemctl enable redis-server

# Mac (Homebrew)
brew install redis
brew services start redis
```

### Verify Redis is Running

```bash
redis-cli ping
# Should return: PONG
```

---

## 5. Initial Configuration

### Step 1: Set Up Periodic Tasks

```bash
cd e_physio_integration
python manage.py setup_periodic_tasks
```

This creates:
- Patient sync task (every 1 hour)
- Appointment sync task (every 1 hour)
- GHL token refresh task (every 20 hours)

### Step 2: Initial GHL Authentication

**First-time authentication is required:**

1. Visit: `http://your-domain.com/api/auth/connect`
2. Authorize the application in GHL
3. You'll be redirected back and tokens will be stored

**Or manually trigger:**
```bash
# Open browser to:
http://your-domain.com/api/auth/connect
```

### Step 3: Create Superuser (Optional)

```bash
python manage.py createsuperuser
```

Useful for accessing Django admin to monitor tasks.

---

## 6. Running the Application

### Development Mode

**Terminal 1 - Django Server:**
```bash
cd e_physio_integration
python manage.py runserver 0.0.0.0:8000
```

**Terminal 2 - Celery Worker:**
```bash
cd e_physio_integration

# Windows
celery -A e_physio_integration worker --pool=solo --loglevel=info

# Linux/Mac
celery -A e_physio_integration worker --loglevel=info
```

**Terminal 3 - Celery Beat (Scheduler):**
```bash
cd e_physio_integration
celery -A e_physio_integration beat --loglevel=info
```

---

## 7. Celery Setup (Production)

### Option 1: Systemd (Linux)

Create service files:

**`/etc/systemd/system/celery-worker.service`:**
```ini
[Unit]
Description=Celery Worker Service
After=network.target redis.service postgresql.service

[Service]
Type=forking
User=your_user
Group=your_group
WorkingDirectory=/path/to/e-physio_integration/e_physio_integration
Environment="PATH=/path/to/venv/bin"
ExecStart=/path/to/venv/bin/celery -A e_physio_integration worker --pool=solo --loglevel=info --logfile=/var/log/celery/worker.log --pidfile=/var/run/celery/worker.pid --detach
ExecStop=/bin/kill -s TERM $MAINPID
Restart=always

[Install]
WantedBy=multi-user.target
```

**`/etc/systemd/system/celery-beat.service`:**
```ini
[Unit]
Description=Celery Beat Service
After=network.target redis.service postgresql.service

[Service]
Type=forking
User=your_user
Group=your_group
WorkingDirectory=/path/to/e-physio_integration/e_physio_integration
Environment="PATH=/path/to/venv/bin"
ExecStart=/path/to/venv/bin/celery -A e_physio_integration beat --loglevel=info --logfile=/var/log/celery/beat.log --pidfile=/var/run/celery/beat.pid --detach
ExecStop=/bin/kill -s TERM $MAINPID
Restart=always

[Install]
WantedBy=multi-user.target
```

**Enable and start services:**
```bash
sudo systemctl daemon-reload
sudo systemctl enable celery-worker
sudo systemctl enable celery-beat
sudo systemctl start celery-worker
sudo systemctl start celery-beat

# Check status
sudo systemctl status celery-worker
sudo systemctl status celery-beat
```

### Option 2: Supervisor (Linux/Mac)

**Install Supervisor:**
```bash
sudo apt install supervisor  # Ubuntu/Debian
brew install supervisor      # Mac
```

**`/etc/supervisor/conf.d/celery-worker.conf`:**
```ini
[program:celery-worker]
command=/path/to/venv/bin/celery -A e_physio_integration worker --pool=solo --loglevel=info
directory=/path/to/e-physio_integration/e_physio_integration
user=your_user
autostart=true
autorestart=true
redirect_stderr=true
stdout_logfile=/var/log/celery/worker.log
```

**`/etc/supervisor/conf.d/celery-beat.conf`:**
```ini
[program:celery-beat]
command=/path/to/venv/bin/celery -A e_physio_integration beat --loglevel=info
directory=/path/to/e-physio_integration/e_physio_integration
user=your_user
autostart=true
autorestart=true
redirect_stderr=true
stdout_logfile=/var/log/celery/beat.log
```

**Start services:**
```bash
sudo supervisorctl reread
sudo supervisorctl update
sudo supervisorctl start celery-worker
sudo supervisorctl start celery-beat
```

### Option 3: Windows Service (NSSM)

**Download NSSM:** https://nssm.cc/download

**Install Celery Worker:**
```bash
nssm install CeleryWorker "C:\path\to\venv\Scripts\celery.exe" "-A e_physio_integration worker --pool=solo --loglevel=info"
nssm set CeleryWorker AppDirectory "C:\path\to\e-physio_integration\e_physio_integration"
nssm start CeleryWorker
```

**Install Celery Beat:**
```bash
nssm install CeleryBeat "C:\path\to\venv\Scripts\celery.exe" "-A e_physio_integration beat --loglevel=info"
nssm set CeleryBeat AppDirectory "C:\path\to\e-physio_integration\e_physio_integration"
nssm start CeleryBeat
```

---

## 8. Production Deployment

### Django Settings for Production

Update `settings.py`:

```python
DEBUG = False
ALLOWED_HOSTS = ['your-domain.com', 'www.your-domain.com']

# Security settings
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'
```

### Web Server Setup

**Option 1: Gunicorn + Nginx (Linux)**

**Install Gunicorn:**
```bash
pip install gunicorn
```

**Run Gunicorn:**
```bash
gunicorn e_physio_integration.wsgi:application --bind 0.0.0.0:8000 --workers 4
```

**Nginx Configuration (`/etc/nginx/sites-available/e-physio`):**
```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /static/ {
        alias /path/to/e-physio_integration/e_physio_integration/static/;
    }
}
```

**Enable site:**
```bash
sudo ln -s /etc/nginx/sites-available/e-physio /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

**Option 2: IIS (Windows)**

Use `wfastcgi` or deploy via Docker.

### Static Files

```bash
python manage.py collectstatic --noinput
```

---

## 9. Monitoring & Maintenance

### Check Celery Status

```bash
# Check worker status
celery -A e_physio_integration inspect active

# Check registered tasks
celery -A e_physio_integration inspect registered

# Check scheduled tasks
celery -A e_physio_integration inspect scheduled
```

### View Logs

**Celery Worker Logs:**
```bash
tail -f /var/log/celery/worker.log
```

**Celery Beat Logs:**
```bash
tail -f /var/log/celery/beat.log
```

**Django Logs:**
```bash
tail -f /var/log/django/app.log
```

### Database Maintenance

**Backup:**
```bash
pg_dump -U your_user your_db_name > backup_$(date +%Y%m%d).sql
```

**Restore:**
```bash
psql -U your_user your_db_name < backup_20260130.sql
```

### Monitor Periodic Tasks

**Via Django Admin:**
1. Visit: `http://your-domain.com/admin/`
2. Navigate to: `Periodic Tasks` → `Periodic Tasks`
3. Check task status and last run times

**Via Shell:**
```bash
python manage.py shell
```

```python
from django_celery_beat.models import PeriodicTask
tasks = PeriodicTask.objects.filter(enabled=True)
for task in tasks:
    print(f"{task.name}: {task.last_run_at}")
```

---

## 10. Troubleshooting

### Celery Worker Not Starting

**Check Redis:**
```bash
redis-cli ping
```

**Check Python path:**
```bash
which python  # Linux/Mac
where python  # Windows
```

**Check logs:**
```bash
tail -f /var/log/celery/worker.log
```

### Tasks Not Running

1. **Verify Celery Beat is running:**
```bash
ps aux | grep celery-beat
```

2. **Check task registration:**
```bash
celery -A e_physio_integration inspect registered | grep sync
```

3. **Manually trigger task:**
```bash
python manage.py shell
```

```python
from ghl_accounts.tasks import sync_patients_incremental
result = sync_patients_incremental()
print(result)
```

### Token Refresh Failing

1. **Check refresh token exists:**
```bash
python manage.py shell
```

```python
from ghl_accounts.models import GHLAuthCredentials
auth = GHLAuthCredentials.objects.first()
print(f"Has refresh token: {bool(auth.refresh_token)}")
```

2. **Manually refresh:**
```python
from ghl_accounts.services.contacts import refresh_ghl_token
success, message = refresh_ghl_token()
print(f"Success: {success}, Message: {message}")
```

3. **Re-authenticate if needed:**
Visit: `http://your-domain.com/api/auth/connect`

### Database Connection Issues

1. **Test connection:**
```bash
python manage.py dbshell
```

2. **Check PostgreSQL is running:**
```bash
sudo systemctl status postgresql  # Linux
```

3. **Verify credentials in `.env`**

---

## 📝 Quick Command Reference

### Initial Setup (One-time)

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Run migrations
python manage.py migrate

# 3. Set up periodic tasks
python manage.py setup_periodic_tasks

# 4. Create superuser (optional)
python manage.py createsuperuser

# 5. Collect static files
python manage.py collectstatic --noinput
```

### Daily Operations

```bash
# Start Django (development)
python manage.py runserver

# Start Celery Worker
celery -A e_physio_integration worker --pool=solo --loglevel=info

# Start Celery Beat
celery -A e_physio_integration beat --loglevel=info
```

### Production Services

```bash
# Start services (systemd)
sudo systemctl start celery-worker
sudo systemctl start celery-beat
sudo systemctl start gunicorn

# Check status
sudo systemctl status celery-worker
sudo systemctl status celery-beat

# View logs
sudo journalctl -u celery-worker -f
sudo journalctl -u celery-beat -f
```

---

## ✅ Deployment Checklist

- [ ] Python 3.8+ installed
- [ ] PostgreSQL installed and running
- [ ] Redis installed and running
- [ ] Virtual environment created and activated
- [ ] Dependencies installed (`pip install -r requirements.txt`)
- [ ] `.env` file configured with all secrets
- [ ] Database created and migrations run
- [ ] Periodic tasks set up (`python manage.py setup_periodic_tasks`)
- [ ] GHL authentication completed (initial OAuth)
- [ ] Celery Worker service configured and running
- [ ] Celery Beat service configured and running
- [ ] Django/Gunicorn server running
- [ ] Web server (Nginx/Apache) configured
- [ ] SSL certificate installed (for HTTPS)
- [ ] Static files collected
- [ ] Logging configured
- [ ] Monitoring set up
- [ ] Backup strategy in place

---

## 🔗 Additional Resources

- **Integration Summary**: See `INTEGRATION_COMPLETE_SUMMARY.md`
- **Token Refresh Guide**: See `GHL_TOKEN_REFRESH_GUIDE.md`
- **Celery Setup**: See `CELERY_SETUP_GUIDE.md`

---

**Last Updated**: January 30, 2026
**Version**: 1.0
