"""Configuration and identity validation do not send external email."""

import pytest
from pydantic import ValidationError

from app.config import load_settings
from app.contracts import EmailInput, PasswordChange, PasswordReset, Register
from app.mail import SMTPMailer
from tests.mail_support import mail_settings


def test_email_normalization_and_password_boundaries() -> None:
    assert EmailInput(email="  Admin@PSY.com  ").email == "admin@psy.com"
    assert EmailInput(email="name+tag@example.com").email == "name+tag@example.com"
    assert EmailInput(email="first.last@example.com").email == "first.last@example.com"
    for email in (
        "a..b@example.com",
        "a@-example.com",
        "a@localhost",
        "a@b@example.com",
        "a\n@example.com",
        "a" * 65 + "@example.com",
    ):
        with pytest.raises(ValidationError):
            EmailInput(email=email)
    for model, values in (
        (Register, {"email": "a@example.com", "code": "123456", "password": "123456"}),
        (PasswordReset, {"email": "a@example.com", "code": "123456", "new_password": "123456"}),
        (PasswordChange, {"current_password": "previous", "new_password": "123456"}),
    ):
        model(**values)
        field = "password" if model is Register else "new_password"
        for password in ("12345", "a" * 129):
            with pytest.raises(ValidationError):
                model(**{**values, field: password})


def test_mail_configuration_is_explicit_and_secret() -> None:
    assert not load_settings({}).email_ready
    settings = load_settings(
        {
            "PSYEVO_SMTP_HOST": "smtp.example.com",
            "PSYEVO_SMTP_PORT": "465",
            "PSYEVO_SMTP_FROM": "app@example.com",
            "PSYEVO_SMTP_USERNAME": "app",
            "PSYEVO_SMTP_PASSWORD": "private-mail-password",
            "PSYEVO_SMTP_TLS_MODE": "ssl",
            "PSYEVO_EMAIL_CODE_KEY": "private-digest-key-at-least-32-bytes",
        }
    )
    assert settings.email_ready
    assert "private-mail-password" not in repr(settings)
    assert "private-digest-key" not in repr(settings)
    with pytest.raises(RuntimeError, match="not configured"):
        SMTPMailer(load_settings({})).send("a@example.com", "synthetic", "synthetic")
    with pytest.raises(ValidationError):
        load_settings({"PSYEVO_SMTP_TLS_MODE": "none"})


@pytest.mark.parametrize("mode", ["ssl", "starttls"])
def test_smtp_uses_verified_tls_and_authentication(
    monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    import ssl
    from unittest.mock import MagicMock

    connection = MagicMock()
    constructor = MagicMock(return_value=connection)
    monkeypatch.setattr(
        "app.mail.smtplib.SMTP_SSL" if mode == "ssl" else "app.mail.smtplib.SMTP", constructor
    )
    SMTPMailer(mail_settings(smtp_tls_mode=mode)).send(
        "person@example.com", "subject", "synthetic message"
    )
    smtp = connection.__enter__.return_value
    smtp.login.assert_called_once_with("synthetic", "synthetic-mail-only")
    smtp.send_message.assert_called_once()
    message = smtp.send_message.call_args.args[0]
    assert message["To"] == "person@example.com"
    if mode == "ssl":
        context = constructor.call_args.kwargs["context"]
        smtp.starttls.assert_not_called()
    else:
        smtp.starttls.assert_called_once()
        context = smtp.starttls.call_args.kwargs["context"]
    assert context.check_hostname and context.verify_mode == ssl.CERT_REQUIRED
