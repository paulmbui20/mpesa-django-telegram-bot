"""Contrib app configuration."""

from django.apps import AppConfig


class ContribConfig(AppConfig):
    """Configuration for the contrib app."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "m_pesa_telegram_bot.contrib"
    verbose_name = "M-Pesa Telegram Bot Contrib"

    def ready(self):
        """Import signals when app is ready."""
        import m_pesa_telegram_bot.contrib.signals  # noqa: F401
