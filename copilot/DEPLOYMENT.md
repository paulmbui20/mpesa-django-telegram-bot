# M-Pesa Telegram Bot SaaS - Deployment & Setup Guide

## Table of Contents
1. [Local Development Setup](#local-development-setup)
2. [Environment Variables](#environment-variables)
3. [Database Migrations](#database-migrations)
4. [Running Locally](#running-locally)
5. [Production Deployment with Dokploy](#production-deployment-with-dokploy)
6. [Cloudflare SSL/TLS Configuration](#cloudflare-ssltls-configuration)
7. [Webhook Registration](#webhook-registration)
8. [Dependencies & Installation](#dependencies--installation)

---

## Local Development Setup

### Prerequisites
- Python 3.14+
- `uv` package manager (already installed)
- Docker & Docker Compose
- Git

### Initial Setup

```bash
# Clone repository
git clone <your-repo-url>
cd m_pesa_telegram_bot

# Create local environment files
mkdir -p .envs/.local .envs/.production

# Copy example env files (if they exist)
cp .envs.example/.local/.django .envs/.local/.django  # Create this
cp .envs.example/.local/.postgres .envs/.local/.postgres  # Create this
```

### Environment Files

**`.envs/.local/.django`** (Local Django settings)
```bash
# Django Settings
DEBUG=True
DJANGO_SETTINGS_MODULE=config.settings.local
DJANGO_SECRET_KEY=<generate-a-secure-key>
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1,.local

# Database
DATABASE_URL=postgresql://postgres:postgres@postgres:5432/m_pesa_telegram_bot_local

# Redis (Celery Broker)
REDIS_URL=redis://redis:6379/0

# Email Configuration (Local - Uses Mailpit)
DJANGO_EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=mailpit
EMAIL_PORT=1025
EMAIL_HOST_USER=
EMAIL_HOST_PASSWORD=
EMAIL_USE_TLS=False

# M-Pesa Daraja (Sandbox Credentials - Get from Safaricom)
MPESA_CONSUMER_KEY=<your-daraja-consumer-key>
MPESA_CONSUMER_SECRET=<your-daraja-consumer-secret>

# Telegram API
# TELEGRAM_BOT_TOKEN will be set per-business in the admin panel

# Read .env file
DJANGO_READ_DOT_ENV_FILE=False
```

**`.envs/.local/.postgres`** (PostgreSQL)
```bash
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
POSTGRES_DB=m_pesa_telegram_bot_local
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres
POSTGRES_INITDB_ISOLATION_LEVEL=serializable
```

### Start Local Environment

```bash
# Build and start services
docker-compose -f docker-compose.local.yml up -d

# Wait for services to be ready (about 30 seconds)
sleep 30

# Run migrations
docker-compose -f docker-compose.local.yml exec django python manage.py migrate

# Create superuser
docker-compose -f docker-compose.local.yml exec django python manage.py createsuperuser

# Collect static files
docker-compose -f docker-compose.local.yml exec django python manage.py collectstatic --noinput

# View logs
docker-compose -f docker-compose.local.yml logs -f django
```

### Access Local Services

- **Django Admin**: http://localhost:8000/admin/
- **Mailpit (Email Testing)**: http://localhost:8025/
- **Celery Flower (Task Monitoring)**: http://localhost:5555/

---

## Environment Variables

### Required for Production

```bash
# Django Core
DEBUG=False
DJANGO_SETTINGS_MODULE=config.settings.production
DJANGO_SECRET_KEY=<generate-with: python -c 'from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())'>
DJANGO_ALLOWED_HOSTS=yourdomain.com,www.yourdomain.com,api.yourdomain.com
DJANGO_ADMIN_URL=admin/

# Database (PostgreSQL)
DATABASE_URL=postgresql://<user>:<password>@<host>:<port>/m_pesa_telegram_bot_prod

# Redis (Celery + Cache)
REDIS_URL=redis://<user>:<password>@<host>:<port>/1
REDIS_SSL=True  # If using Upstash or similar

# Email (SendGrid, Mailgun, etc.)
DJANGO_EMAIL_BACKEND=anymail.backends.sendgrid.EmailBackend
# Or use other backends: mailgun, mailjet, amazon_ses, etc.

# M-Pesa Daraja (Production Credentials)
MPESA_CONSUMER_KEY=<production-consumer-key>
MPESA_CONSUMER_SECRET=<production-consumer-secret>
MPESA_ENVIRONMENT=production  # 'sandbox' for testing, 'production' for live

# Sentry (Error Tracking)
SENTRY_DSN=https://<key>@<sentry-host>/1234

# HTTPS/SSL
SECURE_SSL_REDIRECT=True
SESSION_COOKIE_SECURE=True
CSRF_COOKIE_SECURE=True

# CORS (For frontend integrations)
CORS_ALLOWED_ORIGINS=https://yourdomain.com,https://admin.yourdomain.com
```

---

## Database Migrations

### Create Migration Files

```bash
docker-compose -f docker-compose.local.yml exec django python manage.py makemigrations
```

### Apply Migrations Locally

```bash
docker-compose -f docker-compose.local.yml exec django python manage.py migrate
```

### Deploy Migrations to Production

```bash
# SSH into Dokploy container
dokploy ssh <app-name>

# Run migrations
python manage.py migrate

# Or queue as a Celery task if preferred
python manage.py celery_migrate
```

---

## Running Locally

### Start All Services

```bash
# Bring up all services (Django, Postgres, Redis, Celery, Celery Beat, Flower)
docker-compose -f docker-compose.local.yml up

# Or run in background
docker-compose -f docker-compose.local.yml up -d
```

### Stop Services

```bash
docker-compose -f docker-compose.local.yml down

# Remove volumes too (careful - deletes data!)
docker-compose -f docker-compose.local.yml down -v
```

### View Logs

```bash
# All services
docker-compose -f docker-compose.local.yml logs -f

# Specific service
docker-compose -f docker-compose.local.yml logs -f django
docker-compose -f docker-compose.local.yml logs -f celeryworker
docker-compose -f docker-compose.local.yml logs -f celerybeat
```

### Testing Webhooks Locally

Use `ngrok` to expose local webhooks to Telegram and M-Pesa:

```bash
# Install ngrok
brew install ngrok  # Or download from ngrok.com

# Create ngrok subdomain
ngrok authtoken <your-authtoken>

# Expose port 8000
ngrok http 8000

# Note the URL, e.g., https://1234-567-89.ngrok.io

# In admin panel, set webhook URLs to:
# Telegram: https://1234-567-89.ngrok.io/webhooks/telegram/start/
# M-Pesa: https://1234-567-89.ngrok.io/webhooks/mpesa/stk-callback/
```

---

## Production Deployment with Dokploy

Dokploy is a self-hosted container deployment platform (similar to Heroku).

### Dokploy Setup

1. **Create Dokploy Account & Project**
   - Sign up at [dokploy.io](https://dokploy.io)
   - Create a new project

2. **Connect Git Repository**
   - Link your GitHub/GitLab repo
   - Dokploy will auto-detect Docker Compose file

3. **Repository Structure for Dokploy**

```
your-repo/
├── docker-compose.production.yml   # Dokploy reads this
├── Dockerfile                      # Optional: for custom builds
├── compose/
│   └── production/
│       ├── django/
│       │   ├── Dockerfile
│       │   ├── start
│       │   └── entrypoint
│       ├── postgres/
│       │   └── Dockerfile
│       ├── redis/
│       │   └── Dockerfile (if needed)
│       └── traefik/
│           └── Dockerfile
├── manage.py
└── .envs/
    └── .production/
        ├── .django
        └── .postgres
```

### Dokploy Configuration

#### Step 1: Environment Variables

In Dokploy dashboard, set environment variables:

```bash
# Core Django
DEBUG=False
DJANGO_SETTINGS_MODULE=config.settings.production
DJANGO_SECRET_KEY=<secure-key>
DJANGO_ALLOWED_HOSTS=yourdomain.com,api.yourdomain.com

# Database
DATABASE_URL=postgresql://user:pass@postgres:5432/m_pesa_telegram_bot

# Redis
REDIS_URL=redis://redis:6379/0

# Other required vars (see Environment Variables section above)
```

#### Step 2: Configure docker-compose.production.yml

**Key services to include:**
- Django web app (port 8000)
- PostgreSQL database
- Redis cache/broker
- Celery worker
- Celery Beat scheduler
- Flower (optional, for monitoring)
- Traefik (reverse proxy with SSL)

**Example** (already in repo):
```yaml
services:
  django:
    # ...
    environment:
      - DATABASE_URL=${DATABASE_URL}
      - REDIS_URL=${REDIS_URL}
      - DJANGO_SECRET_KEY=${DJANGO_SECRET_KEY}
    depends_on:
      - postgres
      - redis

  postgres:
    # ...
    volumes:
      - postgres_data:/var/lib/postgresql/data

  redis:
    # ...
    volumes:
      - redis_data:/data

  celeryworker:
    # Worker for async tasks
    # ...

  celerybeat:
    # Scheduler for periodic tasks
    # ...

  traefik:
    # Reverse proxy + SSL termination
    # Route traffic to Django
```

#### Step 3: Deploy

```bash
# Push to main branch - Dokploy auto-deploys
git add .
git commit -m "Deploy to Dokploy"
git push origin main

# Or trigger deployment manually in Dokploy dashboard
```

#### Step 4: Post-Deployment

```bash
# SSH into Dokploy container
dokploy ssh m-pesa-bot

# Run migrations
python manage.py migrate

# Create superuser
python manage.py createsuperuser

# Collect static files
python manage.py collectstatic --noinput
```

### Dokploy Monitoring

- View logs: **Logs** tab in Dokploy
- View resource usage: **Metrics** tab
- View running containers: **Services** tab
- Restart services: Click service → **Restart**

---

## Cloudflare SSL/TLS Configuration

Cloudflare provides **free SSL** and acts as a CDN + Web Application Firewall (WAF).

### Step 1: Transfer Domain to Cloudflare

1. Go to [cloudflare.com](https://cloudflare.com)
2. Add site → Enter your domain
3. Change nameservers at your domain registrar to Cloudflare's
4. Wait for DNS propagation (15 minutes - 48 hours)

### Step 2: SSL/TLS Settings

In Cloudflare Dashboard:

1. **Go to SSL/TLS → Overview**
   - Select **Flexible** (if self-signed cert on origin)
   - Or **Full** (if valid cert on origin)
   - Recommend: **Full (strict)** for production

2. **Set Minimum TLS Version: 1.2**

3. **Enable Always Use HTTPS** (automatic redirects)

4. **Enable HSTS** (HTTP Strict Transport Security)
   - Max Age: 12 months (31536000 seconds)
   - Include subdomains: Yes
   - Preload: Yes

5. **Configure Certificate Authority (CA) Issuance**
   - Let Cloudflare issue certs (automatic)

### Step 3: Firewall Rules

Protect your webhook endpoints from abuse:

**Cloudflare Dashboard → Security → WAF Rules**

1. **Create Rule: Protect M-Pesa Webhook**
   ```
   Path contains "/webhooks/mpesa/"
   Allow rate limiting (e.g., 100 requests/minute)
   ```

2. **Create Rule: Protect Telegram Webhook**
   ```
   Path contains "/webhooks/telegram/"
   Require valid IP range (optional: Telegram's IP ranges)
   ```

3. **Block Common Bots**
   - Enable challenge for suspicious traffic
   - Monitor and adjust

### Step 4: DNS Records

Point subdomains to Dokploy:

**Cloudflare Dashboard → DNS Records**

```
A Record:
  Name: api
  Content: <your-dokploy-ip>
  Proxy Status: Proxied (Cloudflare orange cloud)

A Record:
  Name: yourdomain.com (root)
  Content: <your-dokploy-ip>
  Proxy Status: Proxied

CNAME Record:
  Name: www
  Content: yourdomain.com
  Proxy Status: Proxied
```

### Step 5: Page Rules (Optional)

Cache static assets:

```
URL Pattern: example.com/static/*
Cache Level: Cache Everything
Browser Cache TTL: 1 year
```

### Step 6: Verify SSL

```bash
# Check SSL certificate
openssl s_client -connect api.yourdomain.com:443

# Should show: Certificate chain with Cloudflare/Let's Encrypt
```

---

## Webhook Registration

### Telegram Bot Webhooks

1. **Get Bot Token**
   - Message @BotFather on Telegram
   - Create new bot → Get token

2. **Set Webhook URL**

```bash
# In Django admin, create a Business and set telegram_bot_token

# OR use Telegram Bot API directly
curl -X POST https://api.telegram.org/bot<TOKEN>/setWebhook \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://api.yourdomain.com/webhooks/telegram/start/",
    "secret_token": "<webhook_secret_from_admin>",
    "allowed_updates": ["message"],
    "max_connections": 100,
    "drop_pending_updates": true
  }'

# Verify webhook
curl https://api.telegram.org/bot<TOKEN>/getWebhookInfo
```

### M-Pesa (Daraja) Callbacks

1. **Get Daraja Credentials** (Safaricom Developer Portal)
   - Consumer Key & Secret (OAuth credentials)
   - Till/Paybill number
   - Online Passkey (for STK Push)

2. **Register Callback URLs**

Via Safaricom Daraja Portal:

```
STK Push Callback URL: https://api.yourdomain.com/webhooks/mpesa/stk-callback/
Confirmation URL (Optional): https://api.yourdomain.com/webhooks/mpesa/confirmation/
Validation URL (Optional): https://api.yourdomain.com/webhooks/mpesa/validation/
```

3. **Test Callback**

```bash
# From Daraja portal or via mpesakit
python manage.py shell

from mpesakit import MpesaClient

client = MpesaClient(
    client_key="<consumer-key>",
    client_secret="<consumer-secret>",
    environment="sandbox"
)

response = client.stk_push(
    phone_number="254700000000",
    amount=100,
    account_reference="TEST001",
    transaction_desc="Test payment",
    till_number="<your-till>",
    passkey="<your-passkey>"
)
```

---

## Dependencies & Installation

### Add to pyproject.toml

Before deployment, ensure these packages are in dependencies:

```toml
[project]
dependencies = [
  # ... existing dependencies ...
  "mpesakit @ git+https://github.com/Byte-Barn/mpesakit.git",  # M-Pesa integration
  "python-telegram-bot[all]==21.2",  # Telegram bot library
  "django-ninja==1.6.2",  # Already in project
  "django-celery-beat==2.9.0",  # Already in project
  "celery==5.6.3",  # Already in project
]
```

### Install mpesakit

**Option 1: From PyPI** (if published)
```bash
pip install mpesakit
```

**Option 2: From GitHub** (current)
```bash
pip install git+https://github.com/Byte-Barn/mpesakit.git
```

**Option 3: Local Development**
```bash
git clone https://github.com/Byte-Barn/mpesakit.git
cd mpesakit
pip install -e .
```

### Update Docker Image

In `compose/production/django/Dockerfile`:

```dockerfile
FROM python:3.14-slim

# ... existing setup ...

# Install mpesakit
RUN pip install git+https://github.com/Byte-Barn/mpesakit.git

# ... rest of Dockerfile
```

---

## Troubleshooting

### Webhook Not Receiving Callbacks

1. **Check Cloudflare WAF** - May be blocking Telegram/Daraja IPs
   - Whitelist Telegram IPs: https://core.telegram.org/bots/webhooks#ip-range
   - Whitelist Daraja IPs: Check Safaricom docs

2. **Check Django Logs**
   ```bash
   docker-compose -f docker-compose.local.yml logs -f django | grep webhook
   ```

3. **Test Webhook Locally**
   ```bash
   # Use ngrok + curl to send test payload
   curl -X POST http://localhost:8000/webhooks/telegram/start/ \
     -H "Content-Type: application/json" \
     -d '{"update_id": 123456789, "message": {"message_id": 1, "from": 987, "text": "/start test", "chat_id": 987}}'
   ```

### Celery Tasks Not Running

1. Check Celery Worker logs
   ```bash
   docker-compose -f docker-compose.local.yml logs celeryworker
   ```

2. Check Redis connection
   ```bash
   docker-compose -f docker-compose.local.yml exec redis redis-cli ping
   # Should return: PONG
   ```

3. Monitor Flower
   - Open http://localhost:5555/
   - View active tasks and worker health

### Database Connection Issues

```bash
# Test PostgreSQL connection
docker-compose -f docker-compose.local.yml exec postgres \
  psql -U postgres -d m_pesa_telegram_bot_local -c "SELECT 1"

# View Django settings (check DATABASE_URL)
docker-compose -f docker-compose.local.yml exec django \
  python manage.py shell -c "from django.conf import settings; print(settings.DATABASES)"
```

---

## Best Practices

1. **Always use HTTPS** - Required for Telegram and Daraja webhooks
2. **Rotate secrets regularly** - API keys, consumer secrets, bot tokens
3. **Monitor Daraja transaction logs** - Reconcile with Django Payment records
4. **Set up alerts** - For failed payments, subscription expiry issues
5. **Regular backups** - Database backups on Dokploy/managed service
6. **Test in sandbox first** - Before moving to production with Daraja
7. **Implement rate limiting** - Protect webhooks from DDoS/abuse
8. **Log all transactions** - Audit trail for compliance

---

## Support & Resources

- **Django Ninja Docs**: https://django-ninja.rest-framework.com/
- **mpesakit GitHub**: https://github.com/Byte-Barn/mpesakit
- **Telegram Bot Webhooks**: https://core.telegram.org/bots/webhooks
- **Safaricom Daraja Docs**: https://developer.safaricom.co.ke/
- **Celery Basics**: https://docs.celeryq.dev/en/stable/getting-started/
- **Dokploy Docs**: https://dokploy.io/docs
- **Cloudflare SSL**: https://developers.cloudflare.com/ssl-tls/

