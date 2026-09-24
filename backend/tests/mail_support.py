"""Synthetic-only mail capture, never imported by the production application."""

import json
import os
import re
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI
from pydantic import SecretStr

from app.config import Settings, load_settings
from app.main import create_app


class MemoryMailer:
    def __init__(self) -> None:
        self.messages: list[tuple[str, str, str]] = []
        self.fail = False

    def send(self, recipient: str, subject: str, body: str) -> None:
        if self.fail:
            raise RuntimeError("synthetic mail failure")
        self.messages.append((recipient, subject, body))

    def code(self, email: str) -> str:
        for recipient, _, body in reversed(self.messages):
            match = re.search(r"\b[0-9]{6}\b", body)
            if recipient == email and match:
                return match.group()
        raise AssertionError("No synthetic code")


def mail_settings(**kwargs: object) -> Settings:
    return Settings.model_validate(
        {
            "environment": "test",
            "smtp_host": "127.0.0.1",
            "smtp_port": 465,
            "smtp_from": "test@example.com",
            "smtp_username": "synthetic",
            "smtp_password": SecretStr("synthetic-mail-only"),
            "smtp_tls_mode": "ssl",
            "email_code_key": SecretStr("synthetic-email-code-key-32-characters"),
            **kwargs,
        }
    )


class FileMailer:
    def __init__(self, directory: Path) -> None:
        self.directory = directory

    def send(self, recipient: str, subject: str, body: str) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        target = self.directory / (uuid4().hex + ".json")
        target.write_text(
            json.dumps({"email": recipient, "subject": subject, "body": body}), encoding="utf-8"
        )


def create_test_app() -> FastAPI:
    settings = load_settings()
    if settings.environment != "test" or settings.database_url is None:
        raise RuntimeError("Synthetic test environment and isolated database required")
    directory = Path(os.environ["PSYEVO_TEST_MAIL_DIR"]).resolve()
    artifacts = Path(__file__).resolve().parents[2] / ".artifacts"
    if not directory.is_relative_to(artifacts.resolve()):
        raise RuntimeError("Synthetic outbox must stay inside artifacts")
    return create_app(
        mail_settings(
            database_url=settings.database_url,
            browser_origin=settings.browser_origin,
        ),
        FileMailer(directory),
    )
