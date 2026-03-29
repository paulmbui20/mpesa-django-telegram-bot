"""
Webhook API endpoints (separate from authenticated API).
These endpoints are public and handle Telegram bot and M-Pesa callbacks.
"""

from ninja import NinjaAPI, Router
from m_pesa_telegram_bot.contrib.api import telegram_router, mpesa_router

# Create a separate API instance for webhooks without authentication
webhook_api = NinjaAPI(
    title="M-Pesa Telegram Webhooks API",
    urls_namespace="webhook_api",
)

webhook_api.add_router("/telegram/", telegram_router)
webhook_api.add_router("/mpesa/", mpesa_router)
