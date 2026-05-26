"""Mock email tool — replace with real SMTP or SendGrid when ready."""
import logging

logger = logging.getLogger(__name__)


def send_email_notification(
    to: list[str],
    subject: str,
    body: str,
    severity: str,
) -> dict:
    logger.info("[EMAIL MOCK] To: %s", ", ".join(to))
    logger.info("[EMAIL MOCK] Subject: %s", subject)
    logger.info("[EMAIL MOCK] Severity: %s", severity)
    logger.info("[EMAIL MOCK] Body:\n%s", body)
    return {"sent": True, "recipients": to, "subject": subject}
