"""Resend HTTP API email backend — avoids SMTP port blocks on Railway."""

import logging

from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend

logger = logging.getLogger(__name__)


class ResendEmailBackend(BaseEmailBackend):
    """Send email via Resend HTTP API instead of SMTP."""

    def open(self):
        return True

    def close(self):
        pass

    def send_messages(self, email_messages):
        import resend

        resend.api_key = getattr(settings, "RESEND_API_KEY", "")
        if not resend.api_key:
            logger.error("RESEND_API_KEY is not set — cannot send email")
            return 0

        sent = 0
        for message in email_messages:
            try:
                # Get HTML alternative if present
                html_body = None
                for content, mimetype in getattr(message, "alternatives", []):
                    if mimetype == "text/html":
                        html_body = content
                        break

                params = {
                    "from": message.from_email,
                    "to": message.to,
                    "subject": message.subject,
                    "text": message.body,
                }
                if html_body:
                    params["html"] = html_body

                resend.Emails.send(params)
                sent += 1
            except Exception as exc:
                logger.exception("Resend API failed for %s: %s", message.to, exc)
                if not self.fail_silently:
                    raise

        return sent
