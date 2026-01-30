# 🔄 e-Physio ↔ GHL Integration System

A comprehensive two-way integration system that synchronizes patients and appointments between **e-Physio** (Swiss physiotherapy management system) and **GoHighLevel (GHL)** (CRM platform) in real-time.

---

## 📋 Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Architecture](#architecture)
- [Tech Stack](#tech-stack)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Configuration](#configuration)
- [Usage](#usage)
- [API Endpoints](#api-endpoints)
- [Celery Tasks](#celery-tasks)
- [Project Structure](#project-structure)
- [Deployment](#deployment)
- [Documentation](#documentation)
- [Troubleshooting](#troubleshooting)
- [Contributing](#contributing)

---

## 🎯 Overview

This integration system provides seamless bidirectional synchronization between e-Physio and GoHighLevel:

- **Real-time Sync**: Webhook-based synchronization for immediate updates
- **Scheduled Sync**: Celery-based periodic synchronization to catch any missed updates
- **Automatic Token Management**: Automatic GHL token refresh to prevent expiration
- **Data Integrity**: Source tracking to prevent circular updates
- **Error Handling**: Robust error handling with retry mechanisms

---

## ✨ Features

### 🔄 Two-Way Patient Synchronization

- **GHL → e-Physio**: Real-time patient creation/updates via webhooks
- **e-Physio → GHL**: Hourly automated sync of new/updated patients
- **Duplicate Prevention**: Smart duplicate detection and handling
- **Source Tracking**: Tracks data origin to prevent sync loops

### 📅 Two-Way Appointment Synchronization

- **GHL → e-Physio**: Real-time appointment creation with automatic invoice handling
- **e-Physio → GHL**: Hourly automated sync of new/updated appointments
- **Invoice Management**: Automatic invoice lookup and creation for appointments
- **Patient Linking**: Automatic linking of appointments to synced patients

### 🔐 Authentication & Security

- **OAuth 2.0**: Secure GHL authentication flow
- **Automatic Token Refresh**: Tokens refreshed every 20 hours (before 24h expiration)
- **Secure Credentials**: Environment-based configuration

### ⚙️ Automation

- **Celery Tasks**: Background task processing for efficient syncing
- **Periodic Scheduling**: Configurable intervals for sync tasks
- **Bulk Operations**: Optimized database operations for large datasets
- **Rate Limiting**: Respects API rate limits with concurrent processing

---

## 🏗️ Architecture

```
┌─────────────┐                    ┌─────────────┐
│   e-Physio  │◄───────────────────►│     GHL     │
│     API     │                    │     API     │
└─────────────┘                    └─────────────┘
       ▲                                   │
       │                                   │
       │                                   │
       │                                   ▼
┌─────────────────────────────────────────────────┐
│         Django Application                      │
│  ┌──────────────────────────────────────────┐  │
│  │  Webhook Handlers (GHL → e-Physio)       │  │
│  └──────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────┐  │
│  │  Celery Tasks (e-Physio → GHL)           │  │
│  │  • Patient Sync (Hourly)                 │  │
│  │  • Appointment Sync (Hourly)             │  │
│  │  • Token Refresh (Every 20h)             │  │
│  └──────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────┐  │
│  │  Database (PostgreSQL)                   │  │
│  │  • ContactSync                            │  │
│  │  • AppointmentSync                        │  │
│  │  • GHLAuthCredentials                    │  │
│  └──────────────────────────────────────────┘  │
└─────────────────────────────────────────────────┘
       │
       ▼
┌─────────────┐
│    Redis    │  (Message Broker for Celery)
└─────────────┘
```

---

## 🛠️ Tech Stack

- **Backend Framework**: Django 6.0
- **Database**: PostgreSQL
- **Task Queue**: Celery with Redis
- **Task Scheduler**: Celery Beat (django-celery-beat)
- **HTTP Client**: Requests
- **Environment Management**: python-decouple

---

## 📦 Prerequisites

- Python 3.8+
- PostgreSQL 12+
- Redis 6+
- pip (Python package manager)

---

## 🚀 Installation

### 1. Clone the Repository

```bash
git clone <repository-url>
cd e-physio_integration
```

### 2. Create Virtual Environment

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

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Set Up Database

```bash
# Create PostgreSQL database
createdb your_db_name

# Run migrations
cd e_physio_integration
python manage.py migrate
```

### 5. Configure Environment Variables

Create a `.env` file in the project root:

```env
# Django
SECRET_KEY=your-secret-key-here
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1

# Database
DB_NAME=your_db_name
DB_USER=your_db_user
DB_PASSWORD=your_db_password
DB_HOST=localhost
DB_PORT=5432

# GHL OAuth
GHL_CLIENT_ID=your_ghl_client_id
GHL_CLIENT_SECRET=your_ghl_client_secret
GHL_REDIRECTED_URI=http://localhost:8000/api/auth/callback
SCOPE=your_ghl_scope

# e-Physio
EPHYSIO_EMAIL=your_ephysio_email
EPHYSIO_PASSWORD=your_ephysio_password

# Base URI
BASE_URI=http://localhost:8000
```

### 6. Set Up Periodic Tasks

```bash
python manage.py setup_periodic_tasks
```

### 7. Initial GHL Authentication

Visit the authentication URL in your browser:
```
http://localhost:8000/api/auth/connect
```

---

## ⚙️ Configuration

### Celery Configuration

Celery is configured in `settings.py`:

```python
CELERY_BROKER_URL = 'redis://localhost:6379/0'
CELERY_RESULT_BACKEND = 'redis://localhost:6379/0'
CELERY_TIMEZONE = 'UTC'
```

### Periodic Tasks

Tasks are configured via `setup_periodic_tasks` command:
- **Patient Sync**: Every 1 hour
- **Appointment Sync**: Every 1 hour
- **Token Refresh**: Every 20 hours

To change intervals, run:
```bash
python manage.py setup_periodic_tasks --interval 3600 --period hours
```

---

## 🎮 Usage

### Development Mode

Start all services in separate terminals:

**Terminal 1 - Django Server:**
```bash
cd e_physio_integration
python manage.py runserver
```

**Terminal 2 - Celery Worker:**
```bash
cd e_physio_integration

# Windows
celery -A e_physio_integration worker --pool=solo --loglevel=info

# Linux/Mac
celery -A e_physio_integration worker --loglevel=info
```

**Terminal 3 - Celery Beat:**
```bash
cd e_physio_integration
celery -A e_physio_integration beat --loglevel=info
```

### Production Mode

See [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) for production deployment instructions.

---

## 🌐 API Endpoints

### Authentication

- `GET /api/auth/connect` - Initiate GHL OAuth flow
- `GET /api/auth/callback` - OAuth callback handler
- `GET /api/auth/tokens` - Exchange authorization code for tokens

### Webhooks

- `POST /api/webhooks/` - GHL webhook endpoint
  - Handles: `ContactCreate`, `ContactUpdate`, `AppointmentCreate`, `AppointmentUpdate`

### Admin

- `GET /admin/` - Django admin interface

---

## 🔄 Celery Tasks

### Automatic Tasks (Scheduled)

1. **`sync_patients_incremental`**
   - **Schedule**: Every 1 hour
   - **Purpose**: Sync patients from e-Physio to GHL
   - **Actions**:
     - Fetches active patients from e-Physio
     - Updates `ContactSync` table
     - Creates new contacts in GHL

2. **`sync_appointments_incremental`**
   - **Schedule**: Every 1 hour
   - **Purpose**: Sync appointments from e-Physio to GHL
   - **Actions**:
     - Fetches appointments from e-Physio
     - Updates `AppointmentSync` table
     - Creates new appointments in GHL

3. **`refresh_ghl_token_periodic`**
   - **Schedule**: Every 20 hours
   - **Purpose**: Refresh GHL access token before expiration
   - **Actions**:
     - Uses refresh token to get new access token
     - Updates `GHLAuthCredentials` in database

### Manual Task Execution

```python
# In Django shell
from ghl_accounts.tasks import (
    sync_patients_incremental,
    sync_appointments_incremental,
    refresh_ghl_token_periodic
)

# Run immediately
result = sync_patients_incremental()
print(result)

# Or schedule via Celery
task = sync_patients_incremental.delay()
```

---

## 📁 Project Structure

```
e-physio_integration/
├── e_physio_integration/          # Main Django project
│   ├── settings.py                # Django settings
│   ├── urls.py                    # URL configuration
│   ├── celery.py                  # Celery configuration
│   └── wsgi.py                    # WSGI configuration
│
├── ghl_accounts/                   # GHL integration app
│   ├── models.py                  # Database models
│   ├── views.py                   # Webhook handlers
│   ├── tasks.py                   # Celery tasks
│   ├── services/                  # Service layer
│   │   ├── contacts.py           # GHL contact operations
│   │   └── appointments.py       # GHL appointment operations
│   └── management/commands/      # Management commands
│       ├── setup_periodic_tasks.py
│       ├── sync_ephysio_patients.py
│       ├── sync_contacts_to_ghl.py
│       └── ...
│
├── ephysio/                       # e-Physio integration app
│   └── services/                 # Service layer
│       ├── patients.py           # e-Physio patient operations
│       ├── appointments.py       # e-Physio appointment operations
│       └── auth.py              # e-Physio authentication
│
├── requirements.txt              # Python dependencies
├── .env                          # Environment variables (not in git)
├── README.md                     # This file
├── DEPLOYMENT_GUIDE.md           # Deployment instructions
├── QUICK_START.md                # Quick reference
└── INTEGRATION_COMPLETE_SUMMARY.md  # Integration overview
```

---

## 🚀 Deployment

For detailed deployment instructions, see [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md).

### Quick Production Checklist

- [ ] Set `DEBUG=False` in production
- [ ] Configure `ALLOWED_HOSTS`
- [ ] Set up SSL/HTTPS
- [ ] Configure production database
- [ ] Set up Redis
- [ ] Configure Celery services (systemd/supervisor)
- [ ] Set up web server (Nginx/Apache)
- [ ] Configure logging
- [ ] Set up monitoring
- [ ] Set up backups

---

## 📚 Documentation

- **[DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md)** - Complete deployment guide
- **[QUICK_START.md](QUICK_START.md)** - Quick reference for daily operations
- **[INTEGRATION_COMPLETE_SUMMARY.md](INTEGRATION_COMPLETE_SUMMARY.md)** - Integration overview
- **[GHL_TOKEN_REFRESH_GUIDE.md](GHL_TOKEN_REFRESH_GUIDE.md)** - Token refresh documentation

---

## 🔧 Troubleshooting

### Common Issues

**Celery tasks not running:**
- Check Redis is running: `redis-cli ping`
- Verify Celery worker is running: `celery -A e_physio_integration inspect active`
- Check Celery Beat is running: `ps aux | grep celery-beat`

**Token refresh failing:**
- Verify refresh token exists in database
- Check GHL credentials are correct
- Re-authenticate if refresh token expired

**Webhooks not working:**
- Verify webhook URL is accessible from internet
- Check GHL webhook configuration
- Review Django logs for errors

**Database connection issues:**
- Verify PostgreSQL is running
- Check database credentials in `.env`
- Test connection: `python manage.py dbshell`

For more troubleshooting, see [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md#troubleshooting).

---

## 📊 Database Models

### ContactSync
Stores synchronized patient/contact data with mappings between GHL and e-Physio IDs.

### AppointmentSync
Stores synchronized appointment data with mappings between GHL and e-Physio IDs.

### GHLAuthCredentials
Stores GHL OAuth tokens and credentials.

---

## 🔒 Security Considerations

- **Environment Variables**: Never commit `.env` file to version control
- **Secret Key**: Use strong, unique `SECRET_KEY` in production
- **HTTPS**: Always use HTTPS in production
- **Token Storage**: Tokens are stored securely in database
- **API Keys**: Keep API credentials secure and rotate regularly

---

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

---

## 📝 License

[Add your license here]

---

## 👥 Support

For issues, questions, or contributions, please open an issue on the repository.

---

## 🎉 Acknowledgments

- Built with Django and Celery
- Integrates with e-Physio and GoHighLevel APIs

---

**Last Updated**: January 30, 2026  
**Version**: 1.0.0
