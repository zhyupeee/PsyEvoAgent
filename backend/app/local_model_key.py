"""Initialize independent local encryption once; never print configuration or keys."""

import json
import os
import tempfile
from pathlib import Path

from cryptography.fernet import Fernet
from sqlalchemy import inspect, text
from sqlalchemy.engine import make_url

from app.config import load_settings
from app.database import make_engine


def initialize(path: Path) -> None:
    config = json.loads(path.read_text(encoding="utf-8-sig"))
    if config.get("provider_encryption_key"):
        Fernet(config["provider_encryption_key"].encode())
        return
    settings = load_settings()
    if settings.environment != "development" or settings.database_url is None:
        raise ValueError("Local encryption requires the development database")
    url = make_url(settings.database_url.get_secret_value())
    if url.host not in {"127.0.0.1", "localhost"} or url.database != "psyevo_synthetic_dev":
        raise ValueError("Local encryption requires the local development database")
    engine = make_engine(settings.database_url.get_secret_value())
    try:
        with engine.connect() as connection:
            for table, column in (
                ("provider_settings", "encrypted_api_key"),
                ("provider_bindings", "encrypted_config"),
            ):
                if inspect(connection).has_table(table) and connection.scalar(
                    text(f"SELECT EXISTS (SELECT 1 FROM {table} WHERE {column} IS NOT NULL)")
                ):
                    raise ValueError("Restore the original encryption key; ciphertext exists")
    finally:
        engine.dispose()
    config["provider_encryption_key"] = Fernet.generate_key().decode()
    temp: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, prefix=".env.key-", delete=False
        ) as output:
            temp = output.name
            json.dump(config, output, indent=2)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temp, path)
    finally:
        if temp and Path(temp).exists():
            Path(temp).unlink()


if __name__ == "__main__":
    try:
        initialize(Path(__file__).resolve().parents[2] / ".env.local.json")
    except Exception:
        print("Local encryption initialization failed; restore configuration. No key was printed.")
        raise SystemExit(1) from None
