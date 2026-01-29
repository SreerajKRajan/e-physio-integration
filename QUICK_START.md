# ⚡ Quick Start Guide

Quick reference for running the project after initial setup.

---

## 🚀 Start All Services

### Development (3 Terminals)

**Terminal 1 - Django:**
```bash
cd e_physio_integration
python manage.py runserver
```

**Terminal 2 - Celery Worker:**
```bash
cd e_physio_integration
celery -A e_physio_integration worker --pool=solo --loglevel=info
```

**Terminal 3 - Celery Beat:**
```bash
cd e_physio_integration
celery -A e_physio_integration beat --loglevel=info
```

### Production (Systemd)

```bash
sudo systemctl start celery-worker
sudo systemctl start celery-beat
sudo systemctl start gunicorn
```

---

## 📋 One-Time Setup Commands

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Run migrations
python manage.py migrate

# 3. Set up periodic tasks
python manage.py setup_periodic_tasks

# 4. Initial GHL authentication
# Visit: http://your-domain.com/api/auth/connect
```

---

## 🔍 Quick Checks

**Check Redis:**
```bash
redis-cli ping
```

**Check Celery:**
```bash
celery -A e_physio_integration inspect active
```

**Check Tasks:**
```bash
python manage.py shell
```

```python
from django_celery_beat.models import PeriodicTask
PeriodicTask.objects.filter(enabled=True).values_list('name', 'last_run_at')
```

---

## 📚 Full Documentation

See `DEPLOYMENT_GUIDE.md` for complete deployment instructions.

---

**Last Updated**: January 30, 2026
