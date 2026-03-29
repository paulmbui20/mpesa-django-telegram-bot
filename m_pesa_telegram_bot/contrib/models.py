"""
Core data models for M-Pesa Telegram Bot SaaS platform.
Implements row-level multi-tenancy using Foreign Keys.
"""

from datetime import timedelta
from typing import ClassVar

from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django_extensions.db.models import TimeStampedModel

from m_pesa_telegram_bot.users.models import User


class Business(TimeStampedModel):
    """
    Represents a business tenant in the SaaS platform.
    Each business can configure multiple Telegram channels and M-Pesa payment credentials.
    """

    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name="businesses")
    name = models.CharField(_("Business Name"), max_length=255)
    slug = models.SlugField(unique=True, max_length=255)

    # M-Pesa Credentials (Daraja)
    mpesa_consumer_key = models.CharField(_("M-Pesa API Key"), max_length=255)
    mpesa_consumer_secret = models.CharField(_("M-Pesa API Secret"), max_length=255)
    mpesa_till_number = models.CharField(
        _("M-Pesa Till/Paybill Number"),
        max_length=20,
        help_text="The Till or Paybill number to receive payments",
    )
    mpesa_shortcode_type = models.CharField(
        _("Shortcode Type"),
        max_length=20,
        choices=[("till", "Till"), ("paybill", "Paybill")],
        default="till",
    )
    mpesa_passkey = models.CharField(
        _("M-Pesa Online LNM Passkey"),
        max_length=255,
        help_text="Used for M-Pesa Online STK Push",
    )

    # Telegram Bot Credentials
    telegram_bot_token = models.CharField(
        _("Telegram Bot Token"),
        max_length=255,
        unique=True,
        help_text="Unique per business for security",
    )

    # Webhook Configuration
    webhook_secret = models.CharField(
        _("Webhook Secret"),
        max_length=255,
        unique=True,
        help_text="Used to verify webhook authenticity",
    )

    # Status
    is_active = models.BooleanField(default=True)
    is_verified = models.BooleanField(
        default=False,
        help_text="Set to True after Daraja and Telegram webhooks are verified",
    )

    class Meta:
        verbose_name = "Business"
        verbose_name_plural = "Businesses"
        indexes = [
            models.Index(fields=["owner", "is_active"]),
            models.Index(fields=["slug"]),
        ]

    def __str__(self) -> str:
        return self.name

    def get_absolute_url(self) -> str:
        return f"/dashboard/{self.slug}/"


class TelegramChannel(TimeStampedModel):
    """
    Represents a private Telegram channel owned by a business.
    Multiple channels can be created per business for different subscription tiers.
    """

    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="telegram_channels")
    name = models.CharField(_("Channel Name"), max_length=255)
    telegram_channel_id = models.CharField(
        _("Telegram Channel ID"),
        max_length=50,
        help_text="The numeric ID of the Telegram channel",
    )
    description = models.TextField(_("Channel Description"), blank=True)

    # Subscription Configuration
    price_ksh = models.DecimalField(_("Subscription Price (KSH)"), max_digits=10, decimal_places=2)
    duration_days = models.PositiveIntegerField(
        _("Subscription Duration (Days)"),
        default=30,
        help_text="How many days until subscription expires",
    )

    # Status
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Telegram Channel"
        verbose_name_plural = "Telegram Channels"
        unique_together = [["business", "telegram_channel_id"]]
        indexes = [
            models.Index(fields=["business", "is_active"]),
        ]

    def __str__(self) -> str:
        return f"{self.business.name} - {self.name}"


class TelegramUser(TimeStampedModel):
    """
    Represents end-users interacting with Telegram bots.
    Tracks Telegram user info for subscription management.
    """

    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="telegram_users")
    telegram_user_id = models.CharField(
        _("Telegram User ID"),
        max_length=50,
        help_text="The numeric ID of the Telegram user",
    )
    telegram_username = models.CharField(
        _("Telegram Username"),
        max_length=255,
        blank=True,
        help_text="@username if available",
    )
    phone_number = models.CharField(
        _("Phone Number"),
        max_length=20,
        blank=True,
        help_text="Phone number used for M-Pesa payments (e.g., 2547XXXXXXX)",
    )

    class Meta:
        verbose_name = "Telegram User"
        verbose_name_plural = "Telegram Users"
        unique_together = [["business", "telegram_user_id"]]
        indexes = [
            models.Index(fields=["business", "telegram_user_id"]),
        ]

    def __str__(self) -> str:
        return f"{self.telegram_username or self.telegram_user_id} ({self.business.name})"


class Payment(TimeStampedModel):
    """
    Tracks M-Pesa payment transactions for subscriptions.
    """

    PAYMENT_STATUS_CHOICES = [
        ("pending", _("Pending")),
        ("completed", _("Completed")),
        ("failed", _("Failed")),
        ("expired", _("Expired")),
        ("cancelled", _("Cancelled")),
    ]

    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="payments")
    telegram_user = models.ForeignKey(
        TelegramUser,
        on_delete=models.CASCADE,
        related_name="payments",
    )
    telegram_channel = models.ForeignKey(
        TelegramChannel,
        on_delete=models.CASCADE,
        related_name="payments",
    )

    # M-Pesa Details
    checkout_request_id = models.CharField(
        _("Checkout Request ID"),
        max_length=255,
        unique=True,
        help_text="Unique ID from Daraja STK push initiation",
    )
    request_id = models.CharField(
        _("Request ID"),
        max_length=255,
        blank=True,
        help_text="Unique identifier used in requests to Daraja",
    )

    # Payment Info
    amount = models.DecimalField(
        _("Amount (KSH)"),
        max_digits=10,
        decimal_places=2,
        default=0,
    )
    mpesa_receipt_number = models.CharField(
        _("M-Pesa Receipt Number"),
        max_length=50,
        blank=True,
        help_text="Receipt returned by M-Pesa on successful payment",
    )

    # Status
    status = models.CharField(
        _("Payment Status"),
        max_length=20,
        choices=PAYMENT_STATUS_CHOICES,
        default="pending",
    )

    # Timestamps
    initiated_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(
        help_text="STK push expires after 2 minutes (120 seconds)",
    )

    class Meta:
        verbose_name = "Payment"
        verbose_name_plural = "Payments"
        indexes = [
            models.Index(fields=["business", "status"]),
            models.Index(fields=["telegram_user", "status"]),
            models.Index(fields=["checkout_request_id"]),
            models.Index(fields=["status", "expires_at"]),
        ]

    def __str__(self) -> str:
        return f"Payment {self.checkout_request_id} ({self.status})"

    def is_expired(self) -> bool:
        """Check if STK push has expired."""
        return timezone.now() > self.expires_at


class PaymentCallback(TimeStampedModel):
    """
    Raw Daraja callback data for auditing and debugging.
    Stored to maintain a complete audit trail of payment events.
    """

    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="payment_callbacks")
    payment = models.ForeignKey(
        Payment,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="callbacks",
    )

    # Raw Callback Data (JSONField for flexibility)
    callback_data = models.JSONField(_("Raw Callback Data"))

    # Metadata
    result_code = models.CharField(_("Result Code"), max_length=20, blank=True)
    result_description = models.TextField(_("Result Description"), blank=True)

    class Meta:
        verbose_name = "Payment Callback"
        verbose_name_plural = "Payment Callbacks"
        indexes = [
            models.Index(fields=["business", "created"]),
        ]

    def __str__(self) -> str:
        return f"Callback {self.id} ({self.result_code})"


class Subscription(TimeStampedModel):
    """
    Tracks active subscriptions linking TelegramUsers to TelegramChannels.
    Handles subscription lifecycle and expiry management.
    """

    SUBSCRIPTION_STATUS_CHOICES = [
        ("active", _("Active")),
        ("expired", _("Expired")),
        ("cancelled", _("Cancelled")),
    ]

    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="subscriptions")
    telegram_user = models.ForeignKey(
        TelegramUser,
        on_delete=models.CASCADE,
        related_name="subscriptions",
    )
    telegram_channel = models.ForeignKey(
        TelegramChannel,
        on_delete=models.CASCADE,
        related_name="subscriptions",
    )
    payment = models.OneToOneField(
        Payment,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="subscription",
    )

    # Subscription Lifecycle
    started_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(help_text="When the subscription expires")
    status = models.CharField(
        _("Subscription Status"),
        max_length=20,
        choices=SUBSCRIPTION_STATUS_CHOICES,
        default="active",
    )

    class Meta:
        verbose_name = "Subscription"
        verbose_name_plural = "Subscriptions"
        unique_together = [["telegram_user", "telegram_channel"]]
        indexes = [
            models.Index(fields=["business", "status"]),
            models.Index(fields=["telegram_user", "status"]),
            models.Index(fields=["status", "expires_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.telegram_user} → {self.telegram_channel} ({self.status})"

    def is_active(self) -> bool:
        """Check if subscription is currently active."""
        return self.status == "active" and timezone.now() < self.expires_at

    def is_expired(self) -> bool:
        """Check if subscription has passed expiry date."""
        return timezone.now() > self.expires_at

    def mark_expired(self) -> None:
        """Mark subscription as expired."""
        self.status = "expired"
        self.save(update_fields=["status", "modified"])


class TelegramChannelInvite(TimeStampedModel):
    """
    Tracks invite links sent to users for accessing private channels.
    Helps track conversion and retry logic for failed invites.
    """

    INVITE_STATUS_CHOICES = [
        ("pending", _("Pending")),
        ("sent", _("Sent")),
        ("accepted", _("Accepted")),
        ("failed", _("Failed")),
        ("revoked", _("Revoked")),
    ]

    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="telegram_invites")
    subscription = models.ForeignKey(
        Subscription,
        on_delete=models.CASCADE,
        related_name="invites",
    )
    telegram_channel = models.ForeignKey(
        TelegramChannel,
        on_delete=models.CASCADE,
        related_name="invites",
    )

    # Invite Details
    invite_link = models.URLField(_("Invite Link"), blank=True)
    status = models.CharField(
        _("Invite Status"),
        max_length=20,
        choices=INVITE_STATUS_CHOICES,
        default="pending",
    )

    # Retry Logic
    attempt_count = models.PositiveIntegerField(default=0)
    last_attempted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Telegram Channel Invite"
        verbose_name_plural = "Telegram Channel Invites"
        indexes = [
            models.Index(fields=["subscription", "status"]),
            models.Index(fields=["business", "status"]),
        ]

    def __str__(self) -> str:
        return f"Invite for {self.subscription} ({self.status})"
