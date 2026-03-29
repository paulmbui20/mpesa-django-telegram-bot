# M-Pesa Telegram Bot - SaaS Platform Architecture

Complete documentation of the system architecture, models, API endpoints, and Celery tasks.

## Table of Contents
1. [System Architecture](#system-architecture)
2. [Database Models](#database-models)
3. [API Endpoints](#api-endpoints)
4. [Celery Tasks](#celery-tasks)
5. [Subscription Lifecycle](#subscription-lifecycle)
6. [Development & Testing](#development--testing)

---

## System Architecture

### Multi-Tenancy Design

The platform uses **row-level multi-tenancy** with Foreign Key isolation:

```
Business (Tenant Root)
├── owner: User
├── mpesa_credentials: Consumer Key/Secret, Till Number, Passkey
├── telegram_bot_token: Unique bot token per business
└── webhook_secret: Security token for webhook validation

↓ All models inherit tenant isolation through business_id FK

├─ TelegramChannel
│  ├── TelegramChannelInvite
│  └─ Subscription → Payment
│
├─ TelegramUser
│  ├─ Subscription
│  └─ Payment
│
└─ PaymentCallback (Audit Log)
```

**Security Model**: Every query filters by `business_id` to ensure data isolation between tenants.

### Request Flow: User Subscribes to Channel

```
1. User sends /start command to Telegram bot
   ↓
2. Telegram sends update to /webhooks/telegram/start/
   ↓
3. Django processes and validates request
   ↓
4. API calls mpesakit.MpesaClient().stk_push()
   ↓
5. M-Pesa returns CheckoutRequestID, displays prompt on user's phone
   ↓
6. User enters PIN, sends OTP
   ↓
7. M-Pesa processes payment
   ↓
8. Daraja sends callback to /webhooks/mpesa/stk-callback/
   ↓
9. API marks Payment as completed
   ↓
10. Celery task send_telegram_invite() queued
    ↓
11. User receives Telegram message with channel invite link
    ↓
12. Subscription automatically managed:
    - Active for duration_days
    - Expires at scheduled time
    - Celery Beat removes user from channel on expiry
```

---

## Database Models

### Business
Represents a SaaS tenant (business/organization).

**Fields:**
- `owner`: FK to User (business owner)
- `name`: Business name (e.g., "Premium Content Hub")
- `slug`: URL-safe identifier (e.g., "premium-hub")
- `mpesa_consumer_key`: Daraja API key
- `mpesa_consumer_secret`: Daraja API secret
- `mpesa_till_number`: Till or Paybill number (e.g., "123456")
- `mpesa_shortcode_type`: 'till' or 'paybill'
- `mpesa_passkey`: Online LNM Passkey
- `telegram_bot_token`: Telegram Bot API token (unique)
- `webhook_secret`: HMAC secret for webhook signature verification
- `is_active`: Enable/disable business
- `is_verified`: Webhook verification status

**Relationships:**
- `telegram_channels`: ForeignKey reversed
- `payments`: ForeignKey reversed
- `subscriptions`: ForeignKey reversed
- `telegram_users`: ForeignKey reversed

**Indexes:**
- `(owner, is_active)`
- `slug`

---

### TelegramChannel
Represents a private Telegram channel managed by a business.

**Fields:**
- `business`: FK to Business (tenant)
- `name`: Channel name (e.g., "VIP News")
- `telegram_channel_id`: Telegram's numeric channel ID
- `description`: Channel description
- `price_ksh`: Subscription cost in Kenyan Shillings
- `duration_days`: How long subscription lasts (default: 30)
- `is_active`: Enable/disable channel

**Relationships:**
- `subscriptions`: ForeignKey reversed
- `payments`: ForeignKey reversed

**Constraints:**
- Unique together: `(business, telegram_channel_id)`

**Indexes:**
- `(business, is_active)`

---

### TelegramUser
End-user interacting with the Telegram bot.

**Fields:**
- `business`: FK to Business
- `telegram_user_id`: Telegram's numeric user ID (e.g., 987654321)
- `telegram_username`: @username if available
- `phone_number`: Phone number for M-Pesa (e.g., 254700000000)

**Relationships:**
- `subscriptions`: ForeignKey reversed
- `payments`: ForeignKey reversed

**Constraints:**
- Unique together: `(business, telegram_user_id)`

**Indexes:**
- `(business, telegram_user_id)`

---

### Payment
Tracks M-Pesa transaction for subscription.

**Fields:**
- `business`: FK to Business
- `telegram_user`: FK to TelegramUser
- `telegram_channel`: FK to TelegramChannel
- `checkout_request_id`: Daraja's STK push ID (unique, from response)
- `request_id`: Merchant request ID (internal tracking)
- `amount`: Payment amount in KSH
- `mpesa_receipt_number`: M-Pesa receipt on success
- `status`: 'pending', 'completed', 'failed', 'expired', 'cancelled'
- `initiated_at`: When STK push was initiated
- `completed_at`: When payment confirmed
- `expires_at`: When STK push expires (2 minutes after initiation)

**Relationships:**
- `callbacks`: PaymentCallback FK reversed
- `subscription`: Subscription OneToOne reversed

**Status Transitions:**
```
pending → completed → [creates Subscription, sends invite]
pending → failed/expired/cancelled → [no subscription]
```

**Indexes:**
- `(business, status)`
- `(telegram_user, status)`
- `checkout_request_id`
- `(status, expires_at)`

---

### PaymentCallback
Audit log of all Daraja callbacks (for debugging/compliance).

**Fields:**
- `business`: FK to Business
- `payment`: FK to Payment (nullable, in case callback arrives before Payment created)
- `callback_data`: JSONField with raw Daraja response
- `result_code`: Daraja result code (e.g., "0" for success)
- `result_description`: Human-readable result

**Indexes:**
- `(business, created)`

---

### Subscription
Links TelegramUser to TelegramChannel after successful payment.

**Fields:**
- `business`: FK to Business
- `telegram_user`: FK to TelegramUser
- `telegram_channel`: FK to TelegramChannel
- `payment`: OneToOne to Payment (the transaction that activated subscription)
- `started_at`: Subscription start timestamp
- `expires_at`: When subscription ends
- `status`: 'active', 'expired', 'cancelled'

**Methods:**
- `is_active()`: Returns True if status='active' and not past expiry
- `is_expired()`: Returns True if past expiry time
- `mark_expired()`: Sets status to 'expired' and saves

**Constraints:**
- Unique together: `(telegram_user, telegram_channel)` (one active sub per channel)

**Indexes:**
- `(business, status)`
- `(telegram_user, status)`
- `(status, expires_at)` ← Used by Celery Beat for expiry checks

---

### TelegramChannelInvite
Tracks invite link sent to user (for retry logic).

**Fields:**
- `business`: FK to Business
- `subscription`: FK to Subscription
- `telegram_channel`: FK to TelegramChannel
- `invite_link`: URL of the invite link
- `status`: 'pending', 'sent', 'accepted', 'failed', 'revoked'
- `attempt_count`: Number of retry attempts
- `last_attempted_at`: Timestamp of last attempt

**Retry Logic:**
- Exponential backoff: wait = 2^attempt_count minutes
- Max 3 attempts before giving up

**Indexes:**
- `(subscription, status)`
- `(business, status)`

---

## API Endpoints

### Webhook Base URLs

All webhooks are at `/webhooks/` (NO authentication required):

```
POST /webhooks/telegram/start/     (Telegram /start command)
POST /webhooks/mpesa/stk-callback/ (Daraja STK response)
```

### Telegram `/start` Endpoint

**Endpoint:** `POST /webhooks/telegram/start/`

**Request Body:**
```json
{
  "update_id": 123456789,
  "message": {
    "message_id": 1,
    "from": 987654321,
    "text": "/start premium-hub channel-001 254700000000",
    "chat_id": 987654321
  }
}
```

**Command Format:**
```
/start <business_slug> <channel_id> <phone_number>

Examples:
/start premium-hub news-channel 254700123456
/start sports-plus live-games 254798765432
```

**Responses:**

Success:
```json
{
  "ok": true,
  "message": "STK push initiated. Please check your phone.",
  "checkout_request_id": "ws_CO_DMZ_123456789_abcdef"
}
```

Error:
```json
{
  "ok": false,
  "error": "Phone number required. Please send: /start slug channel_id 2547XXXXXXX"
}
```

**Process:**
1. Extract business slug, channel ID, phone number from command
2. Fetch Business and TelegramChannel
3. Get or create TelegramUser
4. Call `initiate_mpesa_payment()`:
   - Initialize MpesaClient
   - Call `.stk_push()` to Daraja
   - Create Payment record in DB
5. Return success or error

---

### M-Pesa STK Callback Endpoint

**Endpoint:** `POST /webhooks/mpesa/stk-callback/`

**Request Body:**
```json
{
  "stkCallback": {
    "MerchantRequestID": "merchant-001",
    "CheckoutRequestID": "ws_CO_DMZ_123456789",
    "ResultCode": 0,
    "ResultDesc": "The service request has been accepted successfully.",
    "Amount": "100.00",
    "MpesaReceiptNumber": "ABCDEF123456",
    "TransactionDate": "20231215120000",
    "PhoneNumber": "254700000000"
  }
}
```

**Response:**
```json
{
  "ResponseCode": "0",
  "ResponseDescription": "Thanks for using M-Pesa"
}
```

**Result Codes:**
- `0`: Success - payment completed
- `1032`: User cancelled STK prompt
- Other codes: Various failures

**Process on Success (ResultCode=0):**
1. Find Payment by CheckoutRequestID
2. Update Payment.status = 'completed'
3. Create/update Subscription (active for duration_days)
4. Queue `send_telegram_invite.delay()` task
5. Return success to Daraja

**Process on Failure:**
1. Update Payment.status = 'failed' or 'cancelled' or 'expired'
2. Log callback
3. Return success (always acknowledge to Daraja)

---

## Celery Tasks

All tasks are in `m_pesa_telegram_bot/contrib/tasks.py`.

### Periodic Tasks (Celery Beat)

**Schedule:**
```python
CELERY_BEAT_SCHEDULE = {
    'check_subscription_expiry_daily': {
        'task': 'm_pesa_telegram_bot.contrib.tasks.check_subscription_expiry',
        'schedule': crontab(hour=2, minute=0),  # 2 AM daily
    },
    'retry_failed_invites_hourly': {
        'task': 'm_pesa_telegram_bot.contrib.tasks.retry_failed_invites',
        'schedule': crontab(minute=0),  # Every hour
    },
    'cleanup_expired_payments_weekly': {
        'task': 'm_pesa_telegram_bot.contrib.tasks.cleanup_expired_payments',
        'schedule': crontab(day_of_week=0, hour=3, minute=0),  # Sunday 3 AM
    },
}
```

### `check_subscription_expiry()`

**When:** Daily at 2 AM UTC

**What it does:**
1. Query all Subscriptions with `status='active'` and `expires_at < now`
2. For each expired subscription:
   - Mark as `status='expired'`
   - Queue `remove_user_from_channel.delay(subscription_id)`
3. Log results

**Why:** Automated cleanup ensures users are removed from channels when subscriptions lapse

---

### `remove_user_from_channel(subscription_id: int)`

**Triggered by:** `check_subscription_expiry()` or manual queue

**What it does:**
1. Fetch Subscription with related objects
2. Initialize Telegram Bot using `business.telegram_bot_token`
3. Call `bot.ban_chat_member()` to kick user from channel
4. Log success

**Error Handling:** If Telegram API fails, continue (user may already be gone)

---

### `send_telegram_invite(subscription_id: int)`

**Triggered by:** M-Pesa callback handler (on payment success)

**What it does:**
1. Fetch Subscription
2. Initialize Telegram Bot
3. Create/get TelegramChannelInvite record
4. Send message to user with invite link
5. Update invite status to 'sent'
6. Return status dict

**Message Format:**
```
🎉 Payment successful!

Your subscription to <channel_name> is now active.

Channel Link: <invite_link>

Valid for 30 days.
Expires at: 2024-01-14 12:00:00
```

**Error Handling:**
- If Telegram API fails, mark invite as 'failed'
- Track attempt count for retry
- Caught later by `retry_failed_invites()`

---

### `retry_failed_invites()`

**When:** Hourly (top of every hour)

**What it does:**
1. Find TelegramChannelInvite with `status='failed'` and `attempt_count < 3`
2. For each, check if enough time has passed since last attempt
   - Wait time = 2^attempt_count minutes (exponential backoff)
   - Attempt 1: wait 2 minutes
   - Attempt 2: wait 4 minutes
   - Attempt 3: wait 8 minutes
3. If ready, queue `send_telegram_invite.delay()`

---

### `handle_stk_push_timeout(payment_id: int)`

**Future/Optional:** Triggered by async task if callback never arrives

**What it does:**
1. Fetch Payment
2. If still 'pending' and past `expires_at`:
   - Mark status = 'expired'
   - Save to DB
3. User never charged, no subscription created

**Note:** Currently manual (see django-admin). Can be auto triggered on `/start`.

---

### `cleanup_expired_payments()`

**When:** Weekly on Sunday at 3 AM UTC

**What it does:**
1. Find Payments with `status='pending'` and `initiated_at < now - 24 hours`
2. Mark as `status='expired'` (safety net for stale records)
3. Log cleaned-up count

**Why:** Database hygiene; should rarely trigger if callbacks work correctly

---

## Subscription Lifecycle

### Sequence Diagram

```
User                Telegram Bot      Django API         M-Pesa         Database
  │                      │                  │              │              │
  └─ /start cmd ────────>│                  │              │              │
                         │─ webhook POST ──>│              │              │
                         │                  │─ validate ──>│              │
                         │                  │ business     │              │
                         │                  │ channel      │              │
                         │                  │              │              │
                         │                  │─ stk_push()─>│              │
                         │                  │<─ CheckoutID │              │
                         │                  │─────────────────── create Payment
                         │                  │              │   (pending) ─>│
                         │<─ STK prompt ────│              │              │
                         │                  │              │              │
  │─ enter PIN ──────────>│ (phone)         │              │              │
  │<─ OK sent ────────────│                 │              │              │
                         │                  │              │              │
                         │                  │<───── callback ────────────>│
                         │                  │ (stkCallback)              │
                         │                  │─────────────── update Payment
                         │                  │   (completed)  │
                         │                  │─────────────── create Subscription
                         │                  │   (active)     │
                         │                  │                │
                         │ queue send_telegram_invite        │
      Celery Worker      │                  │              (later)
          │              │                  │              │
          │─ send msg ──>│ (show invite)   │              │
          │              │                  │              │
  User is in channel for duration_days
                         │              │
                         │        (after 30d)
    Celery Beat ─── check_subscription_expiry
          │
          └─ remove_user_from_channel ──>│ (kick from channel)
                         │              │
                         │
```

---

## Development & Testing

### Running Tests Locally

```bash
# Run all tests
docker-compose -f docker-compose.local.yml exec django pytest

# Run specific test file
docker-compose -f docker-compose.local.yml exec django pytest m_pesa_telegram_bot/contrib/tests/

# Run with coverage
docker-compose -f docker-compose.local.yml exec django pytest --cov=m_pesa_telegram_bot
```

### Creating Migrations

```bash
# After updating models.py
docker-compose -f docker-compose.local.yml exec django python manage.py makemigrations

# Apply migrations
docker-compose -f docker-compose.local.yml exec django python manage.py migrate
```

### Testing M-Pesa Integration

```bash
# SSH into Django container
docker-compose -f docker-compose.local.yml exec django bash

# Open Django shell
python manage.py shell

# Test mpesakit
from mpesakit import MpesaClient

client = MpesaClient(
    client_key="<daraja-key>",
    client_secret="<daraja-secret>",
    environment="sandbox"
)

# Initiate STK push
response = client.stk_push(
    phone_number="254700000000",
    amount=100,
    account_reference="TEST001",
    transaction_desc="Test",
    till_number="123456",
    passkey="<online-passkey>"
)

print(response)
# Expected: {'ResponseCode': '0', 'CheckoutRequestID': 'ws_CO_...', ...}
```

### Testing Telegram Integration

```bash
# In Django shell
from m_pesa_telegram_bot.contrib.models import Business, TelegramChannel, TelegramUser
from telegram import Bot

# Get business
biz = Business.objects.first()

# Initialize bot
bot = Bot(token=biz.telegram_bot_token)

# Send message
bot.send_message(
    chat_id=987654321,  # Your Telegram ID
    text="Test message from Django!"
)
```

### Manual Webhook Testing

```bash
# Using curl (test Telegram /start webhook)
curl -X POST http://localhost:8000/webhooks/telegram/start/ \
  -H "Content-Type: application/json" \
  -d '{
    "update_id": 123456789,
    "message": {
      "message_id": 1,
      "from": 987654321,
      "text": "/start test-biz ch-001 254700000000",
      "chat_id": 987654321
    }
  }'

# Using curl (test M-Pesa callback)
curl -X POST http://localhost:8000/webhooks/mpesa/stk-callback/ \
  -H "Content-Type: application/json" \
  -d '{
    "stkCallback": {
      "MerchantRequestID": "test-001",
      "CheckoutRequestID": "ws_CO_DMZ_123456789",
      "ResultCode": 0,
      "ResultDesc": "Success",
      "Amount": "100.00",
      "MpesaReceiptNumber": "ABC123",
      "TransactionDate": "20231215120000",
      "PhoneNumber": "254700000000"
    }
  }'
```

---

## Example: Adding a New Business

1. **Go to Django Admin** (http://localhost:8000/admin/)
2. **Add Business:**
   - Owner: Select user
   - Name: "My Channel"
   - Slug: "my-channel"
   - M-Pesa details: Insert Daraja credentials
   - Telegram Bot Token: Get from @BotFather
3. **Add Telegram Channel:**
   - Business: Select business you just created
   - Name: "Premium News"
   - Telegram Channel ID: (numeric ID, e.g., -1001234567890)
   - Price: 100 KSH
   - Duration: 30 days
4. **Set Webhooks:**
   - Go to Daraja portal, set callback URLs
   - Use Telegram Bot API to set webhook (`/setWebhook`)
5. **Test:**
   - Message bot: `/start my-channel premium-news 254700000000`
   - Approve STK prompt on phone
   - Receive invite link

---

For questions or issues, refer to [DEPLOYMENT.md](DEPLOYMENT.md).
