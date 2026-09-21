"""Probe the gate-only CPython audit hook without issuing external traffic."""

import socket
from collections.abc import Callable


def assert_blocked(probe: Callable[[], object]) -> None:
    try:
        probe()
    except PermissionError:
        return
    raise AssertionError("Gate did not block network access")


for operation in (
    lambda: socket.create_connection(("203.0.113.1", 443), 1),
    lambda: socket.getaddrinfo("external.invalid", 443),
    lambda: socket.gethostbyname("external.invalid"),
    lambda: socket.gethostbyaddr("203.0.113.1"),
    lambda: socket.getnameinfo(("203.0.113.1", 443), 0),
):
    assert_blocked(operation)

print("Python TCP and DNS guard probes passed")
