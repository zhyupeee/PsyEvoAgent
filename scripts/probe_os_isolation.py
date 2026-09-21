"""Fail closed unless this Linux gate has kernel-enforced loopback-only egress.

Run with python -I, before installing any language-level network hooks.
"""

import errno
import json
import os
import socket
import subprocess
from pathlib import Path


def main() -> None:
    assert os.name == "posix", "OS-isolated gate requires Linux/WSL"
    interfaces = sorted(name for _, name in socket.if_nameindex())
    assert interfaces == ["lo"], interfaces
    status = dict(line.split(":", 1) for line in Path("/proc/self/status").read_text().splitlines())
    assert int(status["NoNewPrivs"].strip()) == 1
    for field in ("CapInh", "CapPrm", "CapEff", "CapBnd", "CapAmb"):
        assert int(status[field].strip(), 16) == 0, field
    results = []
    for family, address in (
        (socket.AF_INET, "203.0.113.1"),
        (socket.AF_INET6, "2001:db8::1"),
    ):
        for kind in (socket.SOCK_STREAM, socket.SOCK_DGRAM):
            with socket.socket(family, kind) as client:
                client.settimeout(2)
                try:
                    client.connect((address, 443))
                except OSError as error:
                    assert error.errno == errno.ENETUNREACH, repr(error)
                    results.append({"address": address, "type": kind.name, "errno": error.errno})
                else:
                    raise AssertionError("Kernel allowed external route")
    # curl is a native executable, unaffected by Python/Node monkeypatches.
    native = subprocess.run(
        [
            "curl",
            "--noproxy",
            "*",
            "-sS",
            "--connect-timeout",
            "2",
            "http://203.0.113.1",
        ],
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )
    assert native.returncode == 7, (native.returncode, native.stderr)
    interop = "microsoft" in Path("/proc/sys/kernel/osrelease").read_text().lower()
    if interop:
        assert Path("/init").read_bytes() == Path("/usr/bin/false").read_bytes()
        # Exercise Windows binary launch as well as checking the mount.
        windows_probe = subprocess.run(
            ["/mnt/c/Windows/System32/cmd.exe", "/c", "exit", "0"],
            capture_output=True,
            timeout=5,
            check=False,
        )
        assert windows_probe.returncode != 0, "Windows interop escaped Linux egress policy"
    print(
        json.dumps(
            {
                "interfaces": interfaces,
                "network_namespace": os.readlink("/proc/self/ns/net"),
                "no_new_privileges": True,
                "capabilities": "none",
                "kernel_probes": results,
                "native_curl_exit": native.returncode,
                "wsl_interop": "blocked" if interop else "not installed",
                "status": "passed",
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
