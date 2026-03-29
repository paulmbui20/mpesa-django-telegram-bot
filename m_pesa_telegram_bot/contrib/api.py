"""
Django Ninja async API endpoints for Telegram and M-Pesa webhooks.
Handles real-time payment processing and Telegram bot interactions.
"""

import hashlib
import hmac
import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from django.conf import settings
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from ninja import NinjaAPI, Router
from pydantic import BaseModel, Field

from m_pesa_telegram_bot.contrib.models import (
    Business,
    Payment,
    PaymentCallback,
    Subscription,
    TelegramChannel,
    TelegramChannelInvite,
    TelegramUser,
)
from m_pesa_telegram_bot.contrib.tasks import (
    send_telegram_invite,
    remove_user_from_channel,
)

logger = logging.getLogger(__name__)

api = NinjaAPI(
    title="M-Pesa Telegram Bot API",
    urls_namespace="contrib_api",
)

# ============================================================================
# Telegram Webhook Models
# ============================================================================


class TelegramMessage(BaseModel):
    """Telegram message update schema."""

    message_id: int
    from_: int | None = Field(None, alias="from")
    text: str | None = None
    chat_id: int | None = None


class TelegramUpdate(BaseModel):
    """Telegram webhook update schema."""

    update_id: int
    message: TelegramMessage | None = None


# ============================================================================
# M-Pesa Webhook Models
# ============================================================================


class MpesaCallbackMetadata(BaseModel):
    """M-Pesa callback metadata item."""

    Name: str
    Value: Any


class MpesaCallbackData(BaseModel):
    """M-Pesa callback data structure."""

    MerchantRequestID: str
    CheckoutRequestID: str
    ResultCode: int
    ResultDesc: str
    Amount: str | None = None
    MpesaReceiptNumber: str | None = None
    TransactionDate: str | None = None
    PhoneNumber: str | None = None


class MpesaCallbackBody(BaseModel):
    """Complete M-Pesa callback payload."""

    stkCallback: MpesaCallbackData


# ============================================================================
# Telegram Router
# ============================================================================

telegram_router = Router(
    tags=["telegram"],
)


@telegram_router.post("/start/")
@csrf_exempt
async def handle_telegram_start(request, update: TelegramUpdate):
    """
    Handle Telegram /start command from users.
    Initiates M-Pesa STK push for subscription payment.

    Args:
        request: Django request object
        update: Telegram update containing user message

    Returns:
        Success/error response
    """
    if not update.message or not update.message.text:
        return {"ok": False, "error": "No message text"}

    try:
        telegram_user_id = str(update.message.from_)
        chat_id = update.message.chat_id
        text = update.message.text

        # Parse: /start <business_slug> <channel_id>
        parts = text.split()
        if len(parts) < 3:
            return {"ok": False, "error": "Invalid /start parameters"}

        business_slug = parts[1]
        channel_id = parts[2]

        # Fetch business
        try:
            business = await Business.objects.aget(slug=business_slug, is_active=True)
        except Business.DoesNotExist:
            logger.warning(f"Business not found: {business_slug}")
            return {"ok": False, "error": "Business not found"}

        # Check webhook secret validity
        # In production, verify Telegram X-Telegram-Bot-API-Secret-Token header

        # Fetch telegram channel
        try:
            channel = await TelegramChannel.objects.aget(
                business=business,
                telegram_channel_id=channel_id,
                is_active=True,
            )
        except TelegramChannel.DoesNotExist:
            logger.warning(f"Channel not found: {channel_id}")
            return {"ok": False, "error": "Channel not found"}

        # Get or create telegram user (with phone number from message or prompt)
        telegram_user, created = await TelegramUser.objects.aget_or_create(
            business=business,
            telegram_user_id=telegram_user_id,
            defaults={"telegram_username": ""},
        )

        # Extract phone number from message (e.g., /start slug channel_id 2547XXXXXXX)
        phone_number = None
        if len(parts) >= 4:
            phone_number = parts[3]
        else:
            # Optional: Prompt user for phone via Telegram
            logger.info(f"Phone number not provided for user {telegram_user_id}")
            return {
                "ok": False,
                "error": "Phone number required. Please send: /start slug channel_id 2547XXXXXXX",
            }

        # Update phone if provided
        if phone_number:
            telegram_user.phone_number = phone_number
            await telegram_user.asave()

        # Check if already subscribed
        existing_subscription = await Subscription.objects.filter(
            telegram_user=telegram_user,
            telegram_channel=channel,
            status="active",
        ).afirst()

        if existing_subscription and not existing_subscription.is_expired():
            return {
                "ok": False,
                "error": "Already subscribed to this channel",
            }

        # Import mpesakit here to avoid dependency issues
        try:
            from mpesakit import MpesaClient
        except ImportError:
            logger.error("mpesakit package not installed. Install with: pip install mpesakit")
            return {
                "ok": False,
                "error": "Payment service unavailable",
            }

        # Create payment and initiate M-Pesa STK push
        payment = await initiate_mpesa_payment(
            business=business,
            telegram_user=telegram_user,
            channel=channel,
            phone_number=phone_number,
        )

        if not payment:
            return {
                "ok": False,
                "error": "Failed to initiate payment",
            }

        logger.info(
            f"STK push initiated for user {telegram_user_id} "
            f"in channel {channel.name} "
            f"(Request: {payment.checkout_request_id})"
        )

        return {
            "ok": True,
            "message": "STK push initiated. Please check your phone.",
            "checkout_request_id": payment.checkout_request_id,
        }

    except Exception as e:
        logger.exception(f"Error handling /start command: {e}")
        return {"ok": False, "error": str(e)}


async def initiate_mpesa_payment(
    business: Business,
    telegram_user: TelegramUser,
    channel: TelegramChannel,
    phone_number: str,
) -> Payment | None:
    """
    Initiate M-Pesa STK push for subscription payment using mpesakit.

    Args:
        business: Business tenant
        telegram_user: Telegram user initiating payment
        channel: Channel being subscribed to
        phone_number: Phone number for M-Pesa payment

    Returns:
        Payment object or None on failure
    """
    try:
        from mpesakit import MpesaClient

        # Initialize mpesakit client
        mpesa_client = MpesaClient(
            client_key=business.mpesa_consumer_key,
            client_secret=business.mpesa_consumer_secret,
            environment="sandbox",  # Use "production" in production
        )

        # Prepare payment details
        request_id = f"{business.id}-{telegram_user.telegram_user_id}-{timezone.now().timestamp()}"
        amount = int(channel.price_ksh)  # mpesakit expects integer in cents or base units

        # Initiate STK push
        response = await mpesa_client.stk_push(
            phone_number=phone_number,
            amount=amount,
            account_reference=request_id,
            transaction_desc=f"{channel.name} - 30 days subscription",
            till_number=business.mpesa_till_number,
            passkey=business.mpesa_passkey,
        )

        # Parse response
        if response.get("ResponseCode") != "0":
            logger.error(f"STK push failed: {response}")
            return None

        # Create payment record
        payment = await Payment.objects.acreate(
            business=business,
            telegram_user=telegram_user,
            telegram_channel=channel,
            checkout_request_id=response.get("CheckoutRequestID", ""),
            request_id=request_id,
            amount=Decimal(str(channel.price_ksh)),
            status="pending",
            initiated_at=timezone.now(),
            expires_at=timezone.now() + timedelta(minutes=2),  # STK expires in 2 minutes
        )

        logger.info(f"Payment created: {payment.id} (Request: {payment.checkout_request_id})")
        return payment

    except Exception as e:
        logger.exception(f"Error initiating M-Pesa payment: {e}")
        return None


# ============================================================================
# M-Pesa Router
# ============================================================================

mpesa_router = Router(
    tags=["mpesa"],
)


@mpesa_router.post("/stk-callback/")
@csrf_exempt
async def handle_mpesa_stk_callback(request, body: MpesaCallbackBody) -> dict:
    """
    Handle M-Pesa STK push callback from Daraja.
    Processes payment confirmation and creates subscription.

    Args:
        request: Django request object
        body: M-Pesa callback payload

    Returns:
        Response acknowledging callback receipt
    """
    try:
        callback_data = body.stkCallback
        checkout_request_id = callback_data.CheckoutRequestID
        result_code = callback_data.ResultCode
        result_desc = callback_data.ResultDesc

        # Find payment
        try:
            payment = await Payment.objects.aget(
                checkout_request_id=checkout_request_id,
            )
        except Payment.DoesNotExist:
            logger.warning(f"Payment not found for callback: {checkout_request_id}")
            return {
                "ResponseCode": "0",
                "ResponseDescription": "Callback received",
            }

        # Create callback audit record
        callback_record = await PaymentCallback.objects.acreate(
            business=payment.business,
            payment=payment,
            callback_data=callback_data.dict(),
            result_code=str(result_code),
            result_description=result_desc,
        )

        # Process based on result code
        if result_code == 0:
            # Payment successful
            await handle_successful_payment(payment, callback_data)
        elif result_code == 1032:
            # Request cancelled by user
            payment.status = "cancelled"
            await payment.asave()
            logger.info(f"Payment cancelled: {payment.id}")
        else:
            # Other failures
            payment.status = "failed"
            await payment.asave()
            logger.warning(f"Payment failed: {payment.id} (Code: {result_code})")

        return {
            "ResponseCode": "0",
            "ResponseDescription": "Thanks for using M-Pesa",
        }

    except Exception as e:
        logger.exception(f"Error processing M-Pesa callback: {e}")
        return {
            "ResponseCode": "1",
            "ResponseDescription": "Error processing callback",
        }


async def handle_successful_payment(
    payment: Payment,
    callback_data: MpesaCallbackData,
) -> None:
    """
    Process successful payment: create subscription and send invite link.

    Args:
        payment: Payment object
        callback_data: M-Pesa callback data
    """
    try:
        # Update payment
        payment.status = "completed"
        payment.completed_at = timezone.now()
        payment.mpesa_receipt_number = callback_data.MpesaReceiptNumber or ""
        await payment.asave()

        # Create or update subscription
        subscription, created = await Subscription.objects.aupdate_or_create(
            telegram_user=payment.telegram_user,
            telegram_channel=payment.telegram_channel,
            defaults={
                "business": payment.business,
                "payment": payment,
                "status": "active",
                "started_at": timezone.now(),
                "expires_at": timezone.now()
                + timedelta(days=payment.telegram_channel.duration_days),
            },
        )

        logger.info(f"Subscription created/updated: {subscription.id}")

        # Queue invite sending task
        await send_telegram_invite.adelay(subscription.id)

        logger.info(f"Invite sending queued for subscription: {subscription.id}")

    except Exception as e:
        logger.exception(f"Error handling successful payment: {e}")


# ============================================================================
# Register Routers
# ============================================================================

api.add_router("/telegram/", telegram_router)
api.add_router("/mpesa/", mpesa_router)
