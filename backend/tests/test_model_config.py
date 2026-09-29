"""No paid requests: encryption, config reload, and pinned transport checks."""

import asyncio
import os
import socket
from pathlib import Path

import httpx2 as httpx
import pytest
from cryptography.fernet import Fernet
from pydantic import SecretStr

from app.config import Settings
from app.provider_config import ConfigCache, read_config
from app.provider_network import PublicTransport, public_addresses, validate_base_url
from app.provider_settings import decrypt, encrypt


def config() -> Settings:
    return Settings(provider_encryption_key=SecretStr(Fernet.generate_key().decode()))


def test_encryption_is_independent_owner_bound_and_key_never_falls_back() -> None:
    settings = config()
    token = encrypt(settings, "owner-a", "account-key", {"key": "synthetic-sensitive"})
    assert "synthetic-sensitive" not in token
    assert decrypt(settings, "owner-a", "account-key", token)["key"] == "synthetic-sensitive"
    for owner, context in [("owner-b", "account-key"), ("owner-a", "other-run")]:
        with pytest.raises(ValueError):
            decrypt(settings, owner, context, token)
    with pytest.raises(ValueError):
        decrypt(config(), "owner-a", "account-key", token)
    with pytest.raises(ValueError, match="encryption_unavailable"):
        encrypt(Settings(), "a", "key", {"key": "synthetic"})


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com/v1",
        "https://localhost/v1",
        "https://127.0.0.1/v1",
        "https://[::1]/v1",
        "https://169.254.169.254/v1",
        "https://10.2.3.4",
        "https://user:pass@example.com",
        "https://example.com/v1?key=secret",
        "https://example.com/#x",
        "https://224.0.0.1",
    ],
)
def test_custom_address_rejection(url: str) -> None:
    with pytest.raises(ValueError):
        validate_base_url(url)


def test_base_path_and_public_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    assert validate_base_url("https://example.com/v1/") == "https://example.com/v1"
    records = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443))]
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: records)
    assert public_addresses("example.com", 443) == ["8.8.8.8"]
    records.append((socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443)))
    with pytest.raises(ValueError, match="address_blocked"):
        public_addresses("example.com", 443)


def test_transport_pins_ip_preserves_host_and_tls_name(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.provider_network.public_addresses", lambda *a: ["8.8.8.8"])

    async def check() -> None:
        transport = PublicTransport("https://example.com/v1")
        await transport.inner.aclose()

        async def handle(req: httpx.Request) -> httpx.Response:
            assert req.url.host == "8.8.8.8"
            assert req.headers["host"] == "example.com"
            assert req.extensions["sni_hostname"] == "example.com"
            assert req.url.path == "/v1/chat/completions"
            return httpx.Response(200, json={})

        transport.inner = httpx.MockTransport(handle)
        async with httpx.AsyncClient(transport=transport) as client:
            assert (
                await client.post("https://example.com/v1/chat/completions", json={})
            ).status_code == 200
            with pytest.raises(ValueError, match="address_blocked"):
                await client.post("https://other.example/v1/chat/completions", json={})

    asyncio.run(check())


def test_reload_debounces_keeps_last_good_and_coalesces(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "config.ps1"
    path.write_text("first")
    base = Settings(provider_config_file=str(path))
    loads: list[str] = []

    def loader(path: Path, original: Settings) -> Settings:
        value = path.read_text()
        loads.append(value)
        if value == "broken":
            raise ValueError("invalid")
        return original.model_copy(update={"provider_model": value})

    monkeypatch.setattr("app.provider_config.read_config", loader)
    cache = ConfigCache(base)
    assert cache.get().provider_model == "first"
    path.write_text("second")
    assert cache.get().provider_model == "first"
    path.write_text("third")
    cache.get()
    cache.changed -= 1
    assert cache.get().provider_model == "third"
    path.write_text("broken")
    cache.get()
    cache.changed -= 1
    assert cache.get().provider_model == "third"
    assert cache.get().provider_model == "third"
    assert loads == ["first", "third", "broken"]


@pytest.mark.skipif(os.name != "nt", reason="Windows PowerShell loader")
def test_real_powershell_loader_is_private_and_file_values_win(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "model config.ps1"
    path.write_text(
        "$env:PSYEVO_PROVIDER_BASE_URL='https://example.com/v1'\n"
        "$env:PSYEVO_PROVIDER_MODEL='synthetic-model'\n"
        "$env:PSYEVO_PROVIDER_API_KEY='synthetic-private-key'\n"
        "$env:PSYEVO_PROVIDER_MAX_OUTPUT_TOKENS='2345'\n"
        "Write-Output $env:PSYEVO_PROVIDER_API_KEY\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("PSYEVO_PROVIDER_MODEL", "ambient-must-not-win")
    monkeypatch.delenv("PSYEVO_OUTPUT_TOKEN_OVERRIDE", raising=False)
    result = read_config(path, Settings())
    assert result.provider_model == "synthetic-model"
    assert result.provider_max_output_tokens == 2345
    assert result.provider_api_key is not None
    assert result.provider_api_key.get_secret_value() == "synthetic-private-key"
    assert "synthetic-private-key" not in capsys.readouterr().out
    monkeypatch.setenv("PSYEVO_OUTPUT_TOKEN_OVERRIDE", "1200")
    assert read_config(path, Settings()).provider_max_output_tokens == 1200
    path.write_text("$env:PSYEVO_PROVIDER_MODEL='missing-other-required-fields'")
    with pytest.raises(ValueError):
        read_config(path, Settings())
