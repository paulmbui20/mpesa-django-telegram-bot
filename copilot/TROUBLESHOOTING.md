# 🔧 Setup Troubleshooting Guide

## Problem: "DATABASE_URL" not set

### ✅ Fixed!
The project now automatically falls back to SQLite if `DATABASE_URL` is not set.

**What this means:**
- You can run without Docker
- Uses `db.sqlite3` for local testing
- No PostgreSQL needed to start developing

### How to use PostgreSQL (with Docker)

Set in `.envs/.local/.django`:
```bash
DATABASE_URL=postgresql://postgres:postgres@postgres:5432/m_pesa_telegram_bot_local
```

---

## Problem: "ModuleNotFoundError: No module named..."

### Common missing modules

**mpesakit:**
```bash
uv pip install git+https://github.com/Byte-Barn/mpesakit.git
```

**python-telegram-bot:**
```bash
uv pip install "python-telegram-bot[all]==21.2"
```

**Other dependencies:**
```bash
# Sync all dependencies from pyproject.toml
uv sync
```

---

## Problem: Django admin not loading

**Symptoms:** `http://localhost:8000/admin` shows 404 or doesn't load

### Solution: Run migrations

```bash
uv run python manage.py migrate
```

**Why?** Admin interface requires database tables.

---

## Problem: No migrations for contrib app

**Symptoms:** `django.db.utils.ProgrammingError: table doesn't exist`

### Solution

```bash
# Create migrations for contrib app
uv run python manage.py makemigrations contrib

# Apply migrations
uv run python manage.py migrate contrib
```

---

## Problem: "No such table" errors

**Symptoms:** App crashes saying a table doesn't exist

### Solution

```bash
# Clear old database
rm db.sqlite3

# Run all migrations
uv run python manage.py migrate

# Create admin user
uv run python manage.py createsuperuser

# Try again
uv run python manage.py runserver
```

---

## Problem: Static files not loading

**Symptoms:** CSS/JS not loading, admin looks broken

### Solution

```bash
uv run python manage.py collectstatic --noinput
```

---

## Problem: Port 8000 already in use

**Symptoms:** `Address already in use (:8000)`

### Solution

```bash
# Use a different port
uv run python manage.py runserver 8001

# Or kill the existing process
lsof -i :8000
kill -9 <PID>
```

---

## Problem: Redis connection error (using Docker)

**Symptoms:** `ConnectionError: Error 111 connecting to Redis`

### Solution

```bash
# Make sure Docker containers are running
docker-compose -f docker-compose.local.yml ps

# Start them if needed
docker-compose -f docker-compose.local.yml up -d redis

# Wait 5 seconds and try again
sleep 5
```

---

## Problem: "contrib" app not recognized

**Symptoms:** `django.core.exceptions.ImproperlyConfigured: No installed app with label 'contrib'`

### Check: Is contrib app in INSTALLED_APPS?

```bash
uv run python -c "from django.conf import settings; print('contrib' in settings.INSTALLED_APPS)"
```

**Should print: True**

---

## Problem: Webhook URLs return 404

**Symptoms:** Webhook endpoints not found

### Check: Are URLs registered?

```bash
uv run python manage.py show_urls | grep webhook
```

**Should show:**
```
/webhooks/telegram/start/
/webhooks/mpesa/stk-callback/
```

---

## Problem: Can't create superuser (with Docker)

**Symptoms:** `django.db.utils.OperationalError: could not connect to server`

### Solution

```bash
# Make sure PostgreSQL is running
docker-compose -f docker-compose.local.yml ps postgres

# If not, start it
docker-compose -f docker-compose.local.yml up -d postgres

# Wait 10 seconds for DB to initialize
sleep 10

# Try creating superuser again
docker-compose -f docker-compose.local.yml exec django python manage.py createsuperuser
```

---

## Problem: "ModuleNotFoundError" in models.py

**Symptoms:** Import errors when starting Django

### Solution: Check settings.py structure

```bash
# Verify settings are correct
uv run python -c "from config.settings.base import *; print('Settings loaded OK')"
```

---

## Problem: Celery tasks not running (using Docker)

**Symptoms:** Tasks queued but never execute

### Check: Is Celery worker running?

```bash
docker-compose -f docker-compose.local.yml ps celeryworker

# If not started, start it
docker-compose -f docker-compose.local.yml up -d celeryworker

# View logs
docker-compose -f docker-compose.local.yml logs celeryworker
```

---

## Problem: Environment variables not loading

**Symptoms:** `KeyError: 'SOME_VAR'` even though it's in `.envs/.local/.django`

### Check: Is `DJANGO_READ_DOT_ENV_FILE` set?

In `.envs/.local/.django`:
```bash
DJANGO_READ_DOT_ENV_FILE=False  # ← Should be False for docker-compose

# OR set to True if using local .env file
DJANGO_READ_DOT_ENV_FILE=True
```

**With Docker:**
- Use `env_file:` in docker-compose.yml ✅ (already configured)
- Don't need `DJANGO_READ_DOT_ENV_FILE=True`

**Without Docker:**
- Create `.env` file in project root
- Copy values from `.envs/.local/.django`
- Set `DJANGO_READ_DOT_ENV_FILE=True`

---

## Quick Diagnostic Commands

```bash
# Check Python environment
uv run python --version
uv run python -m pip list | grep -i django

# Check Django settings
uv run python manage.py shell -c "from django.conf import settings; print(f'DEBUG={settings.DEBUG}')"

# Check installed apps
uv run python manage.py shell -c "from django.conf import settings; print('\n'.join(settings.INSTALLED_APPS))"

# Check database
uv run python manage.py dbshell

# Check static files
uv run python manage.py findstatic --verbosity 2

# Run a test
uv run python manage.py test --verbosity 2
```

---

## ✅ If All Else Fails

1. **Remove virtual environment:**
   ```bash
   rm -rf .venv
   ```

2. **Recreate it:**
   ```bash
   uv sync
   ```

3. **Delete database:**
   ```bash
   rm db.sqlite3
   ```

4. **Run migrations:**
   ```bash
   uv run python manage.py migrate
   ```

5. **Create superuser:**
   ```bash
   uv run python manage.py createsuperuser
   ```

6. **Start fresh:**
   ```bash
   uv run python manage.py runserver
   ```

---

## Still Stuck?

Check the comprehensive guides:
- **`ARCHITECTURE.md`** - System design details
- **`DEPLOYMENT.md`** - Complete setup guide
- **`QUICK_START.md`** - Fast setup walkthrough
