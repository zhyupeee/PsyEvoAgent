"""Explicit TLS SMTP transport. No environment discovery or background consumers."""

import smtplib
import ssl
from email.message import EmailMessage
from typing import Protocol

from app.config import Settings


class Mailer(Protocol):
    def send(self, recipient: str, subject: str, body: str) -> None: ...


class SMTPMailer:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def send(self, recipient: str, subject: str, body: str) -> None:
        config = self.settings
        if not config.email_ready:
            raise RuntimeError("Mail is not configured")
        assert config.smtp_host and config.smtp_port and config.smtp_password
        message = EmailMessage()
        message["From"] = config.smtp_from
        message["To"] = recipient
        message["Subject"] = subject
        message.set_content(body)
        context = ssl.create_default_context()
        connection: smtplib.SMTP
        if config.smtp_tls_mode == "ssl":
            connection = smtplib.SMTP_SSL(
                config.smtp_host, config.smtp_port, timeout=10, context=context
            )
        else:
            connection = smtplib.SMTP(config.smtp_host, config.smtp_port, timeout=10)
        with connection as smtp:
            if config.smtp_tls_mode == "starttls":
                smtp.starttls(context=context)
            assert config.smtp_username
            smtp.login(config.smtp_username, config.smtp_password.get_secret_value())
            smtp.send_message(message)
