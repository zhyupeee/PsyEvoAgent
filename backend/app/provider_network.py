"""Pin custom HTTPS calls to validated public IPs; preserve TLS SNI and Host."""

import asyncio
import ipaddress
import socket
from urllib.parse import urlsplit

import httpx2 as httpx


def is_public(value: str) -> bool:
    address = ipaddress.ip_address(value)
    if not address.is_global or address.is_multicast or address.is_reserved:
        return False
    if isinstance(address, ipaddress.IPv6Address):
        # Exclude address-translation/tunnel ranges that can embed private IPv4.
        return (
            address in ipaddress.ip_network("2000::/3")
            and address.sixtofour is None
            and address.teredo is None
        )
    return True


def validate_base_url(value: str) -> str:
    value = value.strip().rstrip("/")
    url = urlsplit(value)
    if (
        url.scheme != "https"
        or not url.hostname
        or url.username is not None
        or url.password is not None
        or url.query
        or url.fragment
        or "\\" in value
        or any(c.isspace() or ord(c) < 32 for c in value)
    ):
        raise ValueError("provider_base_url_invalid")
    if url.port == 0:
        raise ValueError("provider_base_url_invalid")
    host = url.hostname.lower().rstrip(".")
    if host == "localhost" or host.endswith((".localhost", ".local", ".internal")):
        raise ValueError("provider_address_blocked")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        if not host or "%" in host:
            raise ValueError("provider_base_url_invalid") from None
    else:
        if not is_public(str(address)):
            raise ValueError("provider_address_blocked")
    return value


def public_addresses(host: str, port: int) -> list[str]:
    records = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    addresses = list(dict.fromkeys(str(record[4][0]) for record in records))
    if not addresses or any(not is_public(ip) for ip in addresses):
        raise ValueError("provider_address_blocked")
    return addresses


class PublicTransport(httpx.AsyncBaseTransport):
    def __init__(self, base_url: str) -> None:
        self.origin = httpx.URL(validate_base_url(base_url))
        self.inner: httpx.AsyncBaseTransport = httpx.AsyncHTTPTransport(trust_env=False, retries=0)

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        if (request.url.scheme, request.url.host, request.url.port) != (
            self.origin.scheme,
            self.origin.host,
            self.origin.port,
        ):
            raise ValueError("provider_address_blocked")
        try:
            addresses = await asyncio.wait_for(
                asyncio.to_thread(public_addresses, request.url.host, request.url.port or 443), 10
            )
        except (OSError, ValueError) as exc:
            raise ValueError("provider_address_blocked") from exc
        # Numeric destination prevents a second DNS lookup / rebinding. TLS verifies
        # the original hostname; no credential is sent before certificate validation.
        pinned = httpx.Request(
            request.method,
            request.url.copy_with(host=addresses[0]),
            headers=request.headers,
            stream=request.stream,
            extensions={**request.extensions, "sni_hostname": request.url.host},
        )
        return await self.inner.handle_async_request(pinned)

    async def aclose(self) -> None:
        await self.inner.aclose()
