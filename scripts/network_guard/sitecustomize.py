"""Gate-only CPython audit guard. Never loaded by normal development commands."""

import os
import sys

if os.environ.get("PSYEVO_CHECK_NETWORK") == "loopback-only":

    def guard(event: str, args: tuple[object, ...]) -> None:
        host = None
        if event in {"socket.connect", "socket.sendto", "socket.bind"}:
            address = args[-1]
            if isinstance(address, tuple):
                host = address[0]
        elif event in {
            "socket.getaddrinfo",
            "socket.gethostbyaddr",
            "socket.gethostbyname",
        }:
            host = args[0]
        elif event == "socket.getnameinfo":
            address = args[0]
            if isinstance(address, tuple):
                host = address[0]
        if host is not None and host not in {
            "127.0.0.1",
            "::1",
            "localhost",
            b"127.0.0.1",
            b"::1",
            b"localhost",
        }:
            raise PermissionError("Gate blocks non-loopback network access")

    sys.addaudithook(guard)
