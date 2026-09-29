"""Probe access and evidence semantics without SMTP/network access."""

import json
import smtplib
from pathlib import Path

import pytest
from pydantic import SecretStr

from app import smtp_probe
from app.config import Settings
from app.mail import SMTPMailer


@pytest.mark.parametrize("outcome", ["accepted", "auth_error", "missing_config"])
def test_smtp_probe_distinguishes_acceptance_from_delivery(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, outcome: str
) -> None:
    app = tmp_path / "backend/app"
    app.mkdir(parents=True)
    for name in ("smtp_probe.py", "mail.py", "config.py"):
        (app / name).write_text("synthetic source")
    monkeypatch.setattr(smtp_probe, "__file__", str(app / "smtp_probe.py"))
    monkeypatch.setattr("sys.argv", ["smtp_probe", "--send"])
    for name in ("CI", "PSYEVO_CHECK_NETWORK"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("PSYEVO_SMTP_TEST_SEND_ALLOWED", "true")
    monkeypatch.setenv("PSYEVO_SMTP_TEST_TO", "synthetic@example.com")
    settings = Settings(
        smtp_host="smtp.example.com",
        smtp_port=465,
        smtp_from="sender@example.com",
        smtp_username="synthetic",
        smtp_password=SecretStr("SECRET-SENTINEL"),
        smtp_tls_mode="ssl",
        email_code_key=SecretStr("x" * 32),
    )
    monkeypatch.setattr(
        smtp_probe, "load_settings", lambda: Settings() if outcome == "missing_config" else settings
    )
    sent: list[str] = []

    def send(self: object, recipient: str, subject: str, body: str) -> None:
        sent.append(body)
        if outcome == "auth_error":
            raise smtplib.SMTPAuthenticationError(535, b"SECRET-SENTINEL")

    monkeypatch.setattr(SMTPMailer, "send", send)
    assert smtp_probe.main() == {"accepted": 0, "auth_error": 1, "missing_config": 2}[outcome]
    path = next((tmp_path / ".artifacts").glob("*/receipt.json"))
    data = json.loads(path.read_text())
    assert "SECRET-SENTINEL" not in path.read_text()
    assert data["smtp_accepted"] == (outcome == "accepted")
    assert not data["delivery_confirmed"]
    assert len(sent) == (outcome != "missing_config")
    if outcome == "accepted":
        token = sent[0].split("token: ")[1].splitlines()[0]
        monkeypatch.setattr("sys.argv", ["smtp_probe", "--confirm", str(path)])
        monkeypatch.setattr("builtins.input", lambda _: "WRONG")
        assert smtp_probe.main() == 1
        assert not json.loads(path.read_text())["delivery_confirmed"]
        monkeypatch.setattr("builtins.input", lambda _: token)
        assert smtp_probe.main() == 0
        assert json.loads(path.read_text())["delivery_confirmed"]
        assert len(sent) == 1


def test_smtp_probe_requires_explicit_recipient_authorization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("sys.argv", ["smtp_probe", "--send"])
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.delenv("PSYEVO_CHECK_NETWORK", raising=False)
    monkeypatch.setenv("PSYEVO_SMTP_TEST_SEND_ALLOWED", "false")
    with pytest.raises(SystemExit) as exc:
        smtp_probe.main()
    assert exc.value.code == 2
