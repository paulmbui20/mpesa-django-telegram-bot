"""
Django Admin configuration for M-Pesa Telegram Bot contrib models.
Provides admin interface for managing businesses, channels, payments, and subscriptions.
"""

from django.contrib import admin
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from m_pesa_telegram_bot.contrib.models import (
    Business,
    Payment,
    PaymentCallback,
    Subscription,
    TelegramChannel,
    TelegramChannelInvite,
    TelegramUser,
)


@admin.register(Business)
class BusinessAdmin(admin.ModelAdmin):
    """Admin for Business (tenant) model."""

    list_display = [
        "name",
        "owner",
        "mpesa_till_number",
        "is_active",
        "is_verified",
        "created",
    ]
    list_filter = ["is_active", "is_verified", "created"]
    search_fields = ["name", "slug", "owner__email", "mpesa_till_number"]
    readonly_fields = [
        "webhook_secret",
        "created",
        "modified",
    ]
    fieldsets = (
        (_("Business Info"), {
            "fields": ("owner", "name", "slug")
        }),
        (_("M-Pesa Credentials"), {
            "fields": (
                "mpesa_consumer_key",
                "mpesa_consumer_secret",
                "mpesa_till_number",
                "mpesa_shortcode_type",
                "mpesa_passkey",
            ),
            "classes": ("collapse",),
        }),
        (_("Telegram Bot"), {
            "fields": ("telegram_bot_token",),
            "classes": ("collapse",),
        }),
        (_("Webhook Security"), {
            "fields": ("webhook_secret",),
        }),
        (_("Status"), {
            "fields": ("is_active", "is_verified")
        }),
        (_("Timestamps"), {
            "fields": ("created", "modified"),
            "classes": ("collapse",),
        }),
    )


@admin.register(TelegramChannel)
class TelegramChannelAdmin(admin.ModelAdmin):
    """Admin for TelegramChannel model."""

    list_display = [
        "name",
        "business",
        "telegram_channel_id",
        "price_ksh",
        "duration_days",
        "is_active",
    ]
    list_filter = ["is_active", "business", "created"]
    search_fields = ["name", "telegram_channel_id", "business__name"]
    readonly_fields = ["created", "modified"]
    fieldsets = (
        (_("Channel Info"), {
            "fields": ("business", "name", "telegram_channel_id", "description")
        }),
        (_("Subscription Config"), {
            "fields": ("price_ksh", "duration_days")
        }),
        (_("Status"), {
            "fields": ("is_active",)
        }),
        (_("Timestamps"), {
            "fields": ("created", "modified"),
            "classes": ("collapse",),
        }),
    )


@admin.register(TelegramUser)
class TelegramUserAdmin(admin.ModelAdmin):
    """Admin for TelegramUser model."""

    list_display = [
        "telegram_username",
        "telegram_user_id",
        "business",
        "phone_number",
        "created",
    ]
    list_filter = ["business", "created"]
    search_fields = [
        "telegram_user_id",
        "telegram_username",
        "phone_number",
        "business__name",
    ]
    readonly_fields = ["created", "modified"]


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    """Admin for Payment model."""

    list_display = [
        "checkout_request_id",
        "telegram_user",
        "telegram_channel",
        "amount",
        "status_badge",
        "completed_at",
    ]
    list_filter = ["status", "business", "created"]
    search_fields = [
        "checkout_request_id",
        "mpesa_receipt_number",
        "telegram_user__telegram_username",
    ]
    readonly_fields = [
        "checkout_request_id",
        "initiated_at",
        "created",
        "modified",
    ]
    fieldsets = (
        (_("Payment Info"), {
            "fields": (
                "business",
                "telegram_user",
                "telegram_channel",
                "amount",
            )
        }),
        (_("M-Pesa Details"), {
            "fields": (
                "checkout_request_id",
                "request_id",
                "mpesa_receipt_number",
            ),
            "classes": ("collapse",),
        }),
        (_("Status"), {
            "fields": ("status",)
        }),
        (_("Timestamps"), {
            "fields": (
                "initiated_at",
                "completed_at",
                "expires_at",
                "created",
                "modified",
            ),
            "classes": ("collapse",),
        }),
    )

    def status_badge(self, obj):
        """Display status as a colored badge."""
        status_colors = {
            "pending": "#FFA500",
            "completed": "#28a745",
            "failed": "#dc3545",
            "expired": "#6c757d",
            "cancelled": "#fd7e14",
        }
        color = status_colors.get(obj.status, "#000000")
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 10px; '
            'border-radius: 3px;">{}</span>',
            color,
            obj.get_status_display(),
        )

    status_badge.short_description = "Status"


@admin.register(PaymentCallback)
class PaymentCallbackAdmin(admin.ModelAdmin):
    """Admin for PaymentCallback (audit log) model."""

    list_display = [
        "id",
        "payment",
        "business",
        "result_code",
        "created",
    ]
    list_filter = ["business", "result_code", "created"]
    search_fields = ["payment__checkout_request_id", "result_code"]
    readonly_fields = ["callback_data", "created"]


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    """Admin for Subscription model."""

    list_display = [
        "telegram_user",
        "telegram_channel",
        "status",
        "expires_at",
        "created",
    ]
    list_filter = ["status", "business", "created"]
    search_fields = [
        "telegram_user__telegram_username",
        "telegram_channel__name",
    ]
    readonly_fields = ["created", "modified"]
    fieldsets = (
        (_("Subscription"), {
            "fields": (
                "business",
                "telegram_user",
                "telegram_channel",
                "payment",
            )
        }),
        (_("Lifecycle"), {
            "fields": ("status", "started_at", "expires_at")
        }),
        (_("Timestamps"), {
            "fields": ("created", "modified"),
            "classes": ("collapse",),
        }),
    )

    actions = ["mark_as_expired"]

    def mark_as_expired(self, request, queryset):
        """Admin action to manually mark subscriptions as expired."""
        updated = 0
        for subscription in queryset:
            if subscription.status == "active":
                subscription.mark_expired()
                updated += 1
        self.message_user(request, f"Marked {updated} subscriptions as expired.")

    mark_as_expired.short_description = "Mark selected subscriptions as expired"


@admin.register(TelegramChannelInvite)
class TelegramChannelInviteAdmin(admin.ModelAdmin):
    """Admin for TelegramChannelInvite model."""

    list_display = [
        "id",
        "subscription",
        "status",
        "attempt_count",
        "last_attempted_at",
    ]
    list_filter = ["status", "business", "created"]
    search_fields = ["subscription__telegram_user__telegram_username"]
    readonly_fields = ["created", "modified"]
