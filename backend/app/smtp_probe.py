"""Explicit one-message SMTP acceptance, separate from fake/PR tests."""

import argparse
import hashlib
import json
import os
import smtplib
import ssl
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from app.config import load_settings
from app.mail import SMTPMailer


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--send", action="store_true")
    parser.add_argument("--confirm", type=Path)
    args = parser.parse_args()
    if args.confirm:
        path = args.confirm.resolve()
        artifacts = Path(__file__).resolve().parents[2] / ".artifacts"
        if not path.is_relative_to(artifacts) or path.name != "receipt.json":
            parser.error("Confirmation requires a local artifact receipt")
        saved = json.loads(path.read_text(encoding="utf-8"))
        if saved.get("protocol") != "smtp-delivery-check/1" or not saved.get("smtp_accepted"):
            parser.error("No accepted SMTP test to confirm")
        token = input("Delivery verification token: ").strip().upper()
        if hashlib.sha256(token.encode()).hexdigest() != saved["delivery_token_hash"]:
            print("Delivery token did not match")
            return 1
        saved.update(
            delivery_confirmed=True, status="passed", confirmed_at=datetime.now(UTC).isoformat()
        )
        path.write_text(json.dumps(saved, indent=2), encoding="utf-8")
        print("Delivery confirmed; no message resent")
        return 0
    if not args.send or os.environ.get("CI") or os.environ.get("PSYEVO_CHECK_NETWORK"):
        parser.error("Explicit --send outside PR/network isolation required")
    if os.environ.get("PSYEVO_SMTP_TEST_SEND_ALLOWED", "").lower() != "true":
        parser.error("Explicit test-recipient send authorization required")
    recipient = os.environ.get("PSYEVO_SMTP_TEST_TO", "")
    if not recipient or "@" not in recipient or any(c.isspace() for c in recipient):
        parser.error("A test inbox is required")
    run_id = uuid4().hex
    token = uuid4().hex[:12].upper()
    folder = Path(__file__).resolve().parents[2] / ".artifacts" / ("step08-smtp-" + run_id[:12])
    folder.mkdir(parents=True)
    receipt: dict[str, object] = {
        "protocol": "smtp-delivery-check/1",
        "step_id": "S1-STEP08",
        "execution_kind": "real-smtp-one-synthetic-message",
        "started": datetime.now(UTC).isoformat(),
        "status": "blocked",
        "smtp_accepted": False,
        "delivery_confirmed": False,
        "delivery_token_hash": hashlib.sha256(token.encode()).hexdigest(),
        "run_id": run_id,
        "limitations": "SMTP acceptance is not inbox delivery; no business account is created",
    }
    try:
        settings = load_settings()
        if not settings.email_ready:
            receipt["reason"] = "smtp_not_configured"
            return 2
        SMTPMailer(settings).send(
            recipient,
            "PsyEvoAgent STEP08 SMTP test " + run_id[:8],
            "This is your authorized synthetic SMTP delivery test. No account was created.\n"
            "Reply to the local Codex task with this delivery verification token: " + token + "\n"
            "This token is only for test-delivery confirmation, not login or password recovery.\n",
        )
        receipt.update(
            smtp_accepted=True,
            status="awaiting_delivery_confirmation",
            tls_mode=settings.smtp_tls_mode,
        )
        return 0
    except smtplib.SMTPAuthenticationError:
        receipt.update(status="failed", reason="smtp_authentication")
        return 1
    except (ssl.SSLError, smtplib.SMTPException, OSError):
        receipt.update(status="failed", reason="smtp_transport")
        return 1
    except Exception:
        receipt.update(status="failed", reason="invalid_configuration_or_message")
        return 1
    finally:
        receipt["ended"] = datetime.now(UTC).isoformat()
        receipt["source_sha256"] = {
            name: hashlib.sha256((Path(__file__).parent / name).read_bytes()).hexdigest()
            for name in ("smtp_probe.py", "mail.py", "config.py")
        }
        (folder / "receipt.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
        print("Receipt: " + str(folder / "receipt.json"))


if __name__ == "__main__":
    raise SystemExit(main())
