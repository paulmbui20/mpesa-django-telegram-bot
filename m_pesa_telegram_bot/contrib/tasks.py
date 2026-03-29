"""
Celery tasks for asynchronous processing:
- Checking and managing subscription expiry
- Handling M-Pesa STK push timeouts
- Kicking expired users from Telegram channels
- Sending Telegram invites
"""

import logging
from datetime import timedelta
from typing import Optional

from celery import shared_task
from django.apps import apps
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task
def check_subscription_expiry():
    """
    Celery Beat scheduled task: Check for expired subscriptions daily.
    Marks expired subscriptions and kicks users from Telegram channels.

    Runs once per day (configure in celery_app.py):
    - 'check_subscription_expiry_daily': {
        'task': 'm_pesa_telegram_bot.contrib.tasks.check_subscription_expiry',
        'schedule': crontab(hour=2, minute=0),  # 2 AM daily
    }
    """
    try:
        Subscription = apps.get_model("contrib", "Subscription")
        Payment = apps.get_model("contrib", "Payment")

        now = timezone.now()

        # Find subscriptions that have expired but not yet marked
        expired_subscriptions = Subscription.objects.filter(
            status="active",
            expires_at__lt=now,
        )

        count = 0
        for subscription in expired_subscriptions:
            try:
                # Mark as expired
                subscription.mark_expired()
                logger.info(
                    f"Marked subscription {subscription.id} as expired "
                    f"({subscription.telegram_user} in {subscription.telegram_channel})"
                )

                # Queue task to remove user from channel
                remove_user_from_channel.delay(subscription.id)

                count += 1
            except Exception as e:
                logger.exception(f"Error marking subscription {subscription.id} as expired: {e}")

        logger.info(f"Checked subscription expiry: {count} subscriptions marked as expired")
        return {"marked_expired": count}

    except Exception as e:
        logger.exception("Error in check_subscription_expiry task")
        raise


@shared_task
def handle_stk_push_timeout(payment_id: int):
    """
    Celery task: Handle STK push that has timed out (2 minutes without response).
    Called by a delayed task if callback is never received.

    Args:
        payment_id: ID of the Payment object
    """
    try:
        Payment = apps.get_model("contrib", "Payment")

        try:
            payment = Payment.objects.get(id=payment_id)
        except Payment.DoesNotExist:
            logger.warning(f"Payment {payment_id} not found")
            return

        # Only mark as expired if still pending
        if payment.status != "pending":
            logger.info(f"Payment {payment_id} already processed (status: {payment.status})")
            return

        # Check if we're past the expiry time
        if timezone.now() <= payment.expires_at:
            logger.info(
                f"Payment {payment_id} not yet expired. "
                f"Expires at {payment.expires_at}"
            )
            return

        # Mark as expired
        payment.status = "expired"
        payment.save(update_fields=["status", "modified"])

        logger.info(f"STK push timeout after 2 minutes for payment {payment_id}")
        return {"payment_id": payment_id, "status": "expired"}

    except Exception as e:
        logger.exception(f"Error handling STK push timeout for payment {payment_id}: {e}")
        raise


@shared_task
def remove_user_from_channel(subscription_id: int):
    """
    Celery task: Remove user from Telegram channel after subscription expires.
    Calls Telegram Bot API to kick the user.

    Args:
        subscription_id: ID of the Subscription object
    """
    try:
        Subscription = apps.get_model("contrib", "Subscription")
        TelegramChannelInvite = apps.get_model("contrib", "TelegramChannelInvite")

        try:
            subscription = Subscription.objects.select_related(
                "telegram_user",
                "telegram_channel",
                "business",
            ).get(id=subscription_id)
        except Subscription.DoesNotExist:
            logger.warning(f"Subscription {subscription_id} not found")
            return

        try:
            from telegram import Bot
            from telegram.error import TelegramError
        except ImportError:
            logger.error("python-telegram-bot package not installed.")
            return

        try:
            # Initialize Telegram bot
            bot = Bot(token=subscription.business.telegram_bot_token)

            # Attempt to kick user from channel (use async context)
            import asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(
                    bot.ban_chat_member(
                        chat_id=int(subscription.telegram_channel.telegram_channel_id),
                        user_id=int(subscription.telegram_user.telegram_user_id),
                    )
                )
            finally:
                loop.close()

            logger.info(
                f"User {subscription.telegram_user.telegram_user_id} "
                f"removed from channel {subscription.telegram_channel.name}"
            )

            return {
                "subscription_id": subscription_id,
                "status": "user_removed",
            }

        except TelegramError as e:
            logger.warning(f"Telegram API error removing user from channel: {e}")
            # Log but don't fail - user may already be removed or channel may not exist
            return {
                "subscription_id": subscription_id,
                "status": "telegram_error",
                "error": str(e),
            }

    except Exception as e:
        logger.exception(f"Error removing user from channel for subscription {subscription_id}: {e}")
        raise


@shared_task
def send_telegram_invite(subscription_id: int) -> dict:
    """
    Celery task: Send Telegram channel invite link to user after successful payment.
    Uses python-telegram-bot to send a message with the invite link.

    Args:
        subscription_id: ID of the Subscription object

    Returns:
        dict: Status and results of the invite sending
    """
    try:
        Subscription = apps.get_model("contrib", "Subscription")
        TelegramChannelInvite = apps.get_model("contrib", "TelegramChannelInvite")

        try:
            subscription = Subscription.objects.select_related(
                "telegram_user",
                "telegram_channel",
                "business",
            ).get(id=subscription_id)
        except Subscription.DoesNotExist:
            logger.warning(f"Subscription {subscription_id} not found")
            return {"status": "error", "message": "Subscription not found"}

        try:
            from telegram import Bot
            from telegram.error import TelegramError
        except ImportError:
            logger.error("python-telegram-bot package not installed.")
            return {"status": "error", "message": "Telegram package not available"}

        try:
            # Initialize Telegram bot
            bot = Bot(token=subscription.business.telegram_bot_token)

            # Create or get channel invite record
            invite, created = TelegramChannelInvite.objects.get_or_create(
                business=subscription.business,
                subscription=subscription,
                telegram_channel=subscription.telegram_channel,
            )

            # In production, generate a unique invite link via Telegram API
            # For now, assume the channel has a public link or use Telegram's createChatInviteLink
            invite_link = subscription.telegram_channel.telegram_channel_id  # Placeholder

            try:
                # Send message to user with invite link
                message_text = (
                    f"🎉 Payment successful!\n\n"
                    f"Your subscription to {subscription.telegram_channel.name} is now active.\n\n"
                    f"Channel Link: {invite_link}\n\n"
                    f"Valid for {subscription.telegram_channel.duration_days} days.\n"
                    f"Expires at: {subscription.expires_at.strftime('%Y-%m-%d %H:%M:%S')}"
                )

                import asyncio
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    loop.run_until_complete(
                        bot.send_message(
                            chat_id=int(subscription.telegram_user.telegram_user_id),
                            text=message_text,
                            parse_mode="HTML",
                        )
                    )
                finally:
                    loop.close()

                invite.status = "sent"
                invite.invite_link = invite_link
                invite.attempt_count += 1
                invite.last_attempted_at = timezone.now()
                invite.save()

                logger.info(
                    f"Invite sent to user {subscription.telegram_user.telegram_user_id} "
                    f"for channel {subscription.telegram_channel.name}"
                )

                return {
                    "status": "success",
                    "subscription_id": subscription_id,
                    "user_id": subscription.telegram_user.telegram_user_id,
                }

            except TelegramError as e:
                # Log but continue - we'll retry later
                invite.status = "failed"
                invite.attempt_count += 1
                invite.last_attempted_at = timezone.now()
                invite.save()

                logger.warning(
                    f"Failed to send invite to user {subscription.telegram_user.telegram_user_id}: {e}"
                )

                return {
                    "status": "telegram_error",
                    "subscription_id": subscription_id,
                    "error": str(e),
                    "attempt_count": invite.attempt_count,
                }

        except Exception as e:
            logger.exception(f"Error sending Telegram invite: {e}")
            return {
                "status": "error",
                "subscription_id": subscription_id,
                "error": str(e),
            }

    except Exception as e:
        logger.exception(f"Error in send_telegram_invite task: {e}")
        raise


@shared_task
def retry_failed_invites() -> dict:
    """
    Celery task: Retry sending invites that previously failed.
    Scheduled to run periodically (e.g., every hour).

    Runs multiple times per day:
    - 'retry_failed_invites': {
        'task': 'm_pesa_telegram_bot.contrib.tasks.retry_failed_invites',
        'schedule': crontab(minute=0),  # Every hour
    }
    """
    try:
        TelegramChannelInvite = apps.get_model("contrib", "TelegramChannelInvite")

        # Find failed invites that haven't been attempted recently
        # Retry max 3 times with exponential backoff
        failed_invites = TelegramChannelInvite.objects.filter(
            status="failed",
            attempt_count__lt=3,
        ).select_related("subscription")

        retry_count = 0
        for invite in failed_invites:
            # Simple exponential backoff: wait minutes = 2^attempt_count
            minutes_since_last_attempt = (
                (timezone.now() - invite.last_attempted_at).total_seconds() / 60
            )
            min_wait_minutes = 2 ** invite.attempt_count

            if minutes_since_last_attempt >= min_wait_minutes:
                send_telegram_invite.delay(invite.subscription_id)
                retry_count += 1
                logger.info(f"Retrying invite {invite.id} (Attempt {invite.attempt_count + 1})")

        logger.info(f"Queued {retry_count} failed invites for retry")
        return {"retried": retry_count}

    except Exception as e:
        logger.exception("Error in retry_failed_invites task")
        raise


@shared_task
def cleanup_expired_payments() -> dict:
    """
    Celery task: Clean up expired pending payments and invoices.
    Periodic maintenance task scheduled weekly.

    Runs weekly:
    - 'cleanup_expired_payments': {
        'task': 'mpesakit.contrib.tasks.cleanup_expired_payments',
        'schedule': crontab(day_of_week=0, hour=3, minute=0),  # Sunday 3 AM
    }
    """
    try:
        Payment = apps.get_model("contrib", "Payment")

        now = timezone.now()

        # Find payments still pending after 24 hours (should have timed out)
        stale_pending = Payment.objects.filter(
            status="pending",
            initiated_at__lt=now - timedelta(hours=24),
        )

        count = 0
        for payment in stale_pending:
            payment.status = "expired"
            payment.save(update_fields=["status", "modified"])
            count += 1
            logger.warning(
                f"Cleaned up stale pending payment {payment.id} "
                f"(initiated {(now - payment.initiated_at).days} days ago)"
            )

        logger.info(f"Cleaned up {count} stale pending payments")
        return {"cleaned_up": count}

    except Exception as e:
        logger.exception("Error in cleanup_expired_payments task")
        raise
