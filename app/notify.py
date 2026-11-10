"""Email sending over SMTP. Without SMTP settings it runs in dry-run mode: alerts are only stored in the outbox (GET /api/alerts)."""
import asyncio, smtplib, ssl
from email.message import EmailMessage
from . import config

class Mailer:
    def __init__(self, host=None, port=None, user=None, password=None, sender=None, to=None):
        self.host = config.SMTP_HOST if host is None else host
        self.port = int(config.SMTP_PORT if port is None else port)
        self.user = config.SMTP_USER if user is None else user
        self.password = config.SMTP_PASSWORD if password is None else password
        self.sender = (config.ALERT_EMAIL_FROM if sender is None else sender) or self.user
        raw = config.ALERT_EMAIL_TO if to is None else to
        self.to = [a.strip() for a in (raw.split(",") if isinstance(raw, str) else raw or []) if a.strip()]

    @property
    def configured(self):
        return bool(self.host and self.to and self.sender)

    async def send(self, subject, body):
        """Returns (status, error): status is 'sent', 'dry_run' or 'failed'. Never raises."""
        if not self.configured: return "dry_run", None
        try:
            await asyncio.to_thread(self._send, subject, body)
            return "sent", None
        except Exception as e:
            return "failed", f"{type(e).__name__}: {e}"[:300]

    def _send(self, subject, body):
        msg = EmailMessage()
        msg["Subject"], msg["From"], msg["To"] = subject, self.sender, ", ".join(self.to)
        msg.set_content(body)
        ctx = ssl.create_default_context()
        if self.port == 465:
            with smtplib.SMTP_SSL(self.host, self.port, context=ctx, timeout=15) as s:
                if self.user: s.login(self.user, self.password or "")
                s.send_message(msg)
        else:
            with smtplib.SMTP(self.host, self.port, timeout=15) as s:
                s.starttls(context=ctx)
                if self.user: s.login(self.user, self.password or "")
                s.send_message(msg)
