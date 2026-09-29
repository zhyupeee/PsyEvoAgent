"""Explicit development-only PowerShell config loading; private pipe, no secret logs."""

import hashlib
import json
import logging
import os
import shutil
import subprocess
import threading
import time
from pathlib import Path

from pydantic import ValidationError

from app.config import Settings, load_settings

FIELDS = (
    "BASE_URL",
    "MODEL",
    "API_KEY",
    "DEADLINE_SECONDS",
    "MAX_OUTPUT_TOKENS",
)
logger = logging.getLogger("uvicorn.error")


def read_config(path: Path, base: Settings) -> Settings:
    # Never execute a user-supplied API URL as a file. This path is set only by
    # the local launcher, not by an HTTP request or an account preference.
    shell = shutil.which("powershell.exe") if os.name == "nt" else shutil.which("pwsh")
    if shell is None:
        raise ValueError("provider_config_shell_unavailable")
    env = {k: v for k, v in os.environ.items() if not k.startswith("PSYEVO_PROVIDER_")}
    env["PSYEVO_CONFIG_INPUT"] = str(path.resolve())
    code = """$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
try {
    & { . $env:PSYEVO_CONFIG_INPUT } *> $null
    $result = @{}
    foreach ($name in @('BASE_URL','MODEL','API_KEY','DEADLINE_SECONDS','MAX_OUTPUT_TOKENS')) {
        $value = [Environment]::GetEnvironmentVariable('PSYEVO_PROVIDER_' + $name)
        if ($null -ne $value) { $result['PSYEVO_PROVIDER_' + $name] = $value }
    }
    [Console]::Out.Write(($result | ConvertTo-Json -Compress))
} catch { exit 2 }
"""
    result = subprocess.run(
        [shell, "-NoProfile", "-NonInteractive", "-Command", code],
        env=env,
        capture_output=True,
        timeout=8,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    if result.returncode:
        raise ValueError("provider_config_invalid")
    try:
        values = json.loads(result.stdout.decode("utf-8-sig"))
        if not isinstance(values, dict) or any(not isinstance(v, str) for v in values.values()):
            raise ValueError("provider_config_invalid")
        if not all(
            values.get("PSYEVO_PROVIDER_" + name) for name in ("MODEL", "BASE_URL", "API_KEY")
        ):
            raise ValueError("provider_config_incomplete")
        override = os.environ.get("PSYEVO_OUTPUT_TOKEN_OVERRIDE")
        if override:
            values["PSYEVO_PROVIDER_MAX_OUTPUT_TOKENS"] = override
        parsed = load_settings(values)
        update = {
            "provider_" + field.lower(): getattr(parsed, "provider_" + field.lower())
            for field in FIELDS
        }
        return Settings.model_validate({**base.model_dump(), **update})
    except (ValueError, TypeError, ValidationError):
        raise ValueError("provider_config_invalid") from None


class ConfigCache:
    def __init__(self, base: Settings) -> None:
        self.base = base
        self.active: Settings | None = base if base.provider_ready else None
        self.fingerprint: bytes | None = None
        self.changed = 0.0
        self.attempted: bytes | None = None
        self.lock = threading.Lock()

    def get(self) -> Settings:
        assert self.base.provider_config_file is not None
        path = Path(self.base.provider_config_file)
        with self.lock:
            try:
                fingerprint = hashlib.sha256(path.read_bytes()).digest()
            except OSError:
                fingerprint = b"missing"
            if fingerprint != self.fingerprint:
                self.fingerprint, self.changed = fingerprint, time.monotonic()
            if fingerprint != self.attempted and (
                self.active is None or time.monotonic() - self.changed >= 0.5
            ):
                self.attempted = fingerprint
                try:
                    self.active = read_config(path, self.base)
                    logger.info("provider.config_loaded model=%s", self.active.provider_model)
                except (ValueError, subprocess.TimeoutExpired, OSError):
                    logger.warning(
                        "provider.config_rejected keeping_last_valid=%s", self.active is not None
                    )
            if self.active is None:
                raise ValueError("provider_config_unavailable")
            return self.active


_caches: dict[str, ConfigCache] = {}
_lock = threading.Lock()


def official_settings(settings: Settings) -> Settings:
    if (
        settings.environment != "development"
        or settings.support_mode != "live"
        or not settings.provider_config_file
    ):
        return settings
    with _lock:
        cache = _caches.get(settings.provider_config_file)
        if cache is None or cache.base != settings:
            cache = _caches[settings.provider_config_file] = ConfigCache(settings)
    return cache.get()
