# ✅ Quick Start - M-Pesa Telegram Bot SaaS

## Updated Setup (Fixed)

### ✨ What Changed

The project now supports **two ways** to run locally:

1. **With Docker** (full setup) - PostgreSQL, Redis, Celery
2. **Without Docker** (quick testing) - SQLite database

### 🚀 Option 1: Without Docker (Quickest - 2 minutes)

```bash
# Install dependencies (already done - .venv exists)
uv sync

# Run dev server
uv run python manage.py runserver
```

**That's it!** Django will use SQLite at `db.sqlite3`.

- Access admin: `http://localhost:8000/admin`
- No password yet? Create superuser:

```bash
uv run python manage.py createsuperuser
```

**Limitations:**
- No Redis → No Celery tasks (background jobs won't run)
- No PostgreSQL → Single-user testing only
- Good for: Testing models, API, admin interface

---

### 🐳 Option 2: With Docker (Full Stack - 10 minutes)

Uncomment/add `DATABASE_URL` in `.envs/.local/.django`:

```bash
DATABASE_URL=postgresql://postgres:postgres@postgres:5432/m_pesa_telegram_bot_local
```

Then start services:

```bash
# Start all services (Django, PostgreSQL, Redis, Celery, Celery Beat, Flower)
docker-compose -f docker-compose.local.yml up -d

# Wait 30 seconds for services to start, then run migrations
docker-compose -f docker-compose.local.yml exec django python manage.py migrate

# Create superuser
docker-compose -f docker-compose.local.yml exec django python manage.py createsuperuser

# Access services
# - Admin: http://localhost:8000/admin
# - Celery Dashboard: http://localhost:5555
# - Email Testing: http://localhost:8025
```

**Advantages:**
- Full production-like setup
- All Celery tasks work
- PostgreSQL (production DB)
- Better for testing integrations

---

## 📁 File Overview

All projects files are already created. Key files:

### **M-Pesa SaaS Core** (in `m_pesa_telegram_bot/contrib/`)
- `models.py` - 7 data models (Business, Channel, Payment, Subscription, etc.)
- `api.py` - Webhook endpoints (Telegram + M-Pesa)
- `tasks.py` - Celery async tasks
- `admin.py` - Django admin interface

### **Configuration** (in `config/`)
- `webhook_api.py` - Public webhook API
- `settings/base.py` - Core settings (updated to support SQLite)

### **Documentation** (in `copilot/` folder)
- `ARCHITECTURE.md` - System design
- `DEPLOYMENT.md` - Setup & deployment
- `IMPLEMENTATION_SUMMARY.md` - Overview

---

## ⚡ First Steps

1. **Run dev server:**
   ```bash
   uv run python manage.py runserver
   ```

2. **Go to admin:**
   - URL: `http://localhost:8000/admin`
   - Email: (your superuser email)
   - Password: (what you set)

3. **Create a business:**
   - Business name: "Test Channel"
   - Slug: "test-channel"
   - M-Pesa credentials: Use sandbox values (leave for now if testing)
   - Telegram token: Leave for now

4. **Test webhook (optional):**
   ```bash
   curl -X POST http://localhost:8000/webhooks/telegram/start/ \
     -H "Content-Type: application/json" \
     -d '{"update_id": 123, "message": {"from": 987, "text": "/start test-channel ch1 254700000000", "chat_id": 987}}'
   ```

---

## 🐛 If Something Fails

**Error: `ModuleNotFoundError: No module named 'mpesakit'`**
```bash
# Install M-Pesa package
uv pip install git+https://github.com/Byte-Barn/mpesakit.git
```

**Error: `django.core.exceptions.SuspiciousFileOperation`**
```bash
# Clear Django cache
uv run python manage.py clear_cache

# Or restart server
```

**Docker containers won't start?**
```bash
# Check docker is running
docker ps

# Check logs
docker-compose -f docker-compose.local.yml logs postgres
```

---

## 📚 Documentation

For comprehensive guides, see the `copilot/` folder:

- **`ARCHITECTURE.md`** - Complete system design & API reference
- **`DEPLOYMENT.md`** - Production deployment (Dokploy, Cloudflare)
- **`IMPLEMENTATION_SUMMARY.md`** - Feature overview & next steps

---

## ✅ You're Ready!

Start coding. All models, API endpoints, and tasks are already implemented.

```
Happy building! 🚀
```
