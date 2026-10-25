"""Public entry point for the shared daily error reporter."""
from core.error_digest import EmailReporter, SENDER_EMAIL, RECEIVER_EMAIL

email_reporter = EmailReporter()
