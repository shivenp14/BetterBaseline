"""Small dependency-free check for the E2E backend socket guard."""

import os
import socket
import subprocess
import sys
from pathlib import Path

import python_guard.sitecustomize  # noqa: F401


def main():
    for lookup in (
        lambda: socket.getaddrinfo("example.invalid", 80),
        lambda: socket.gethostbyname("example.invalid"),
        lambda: socket.gethostbyname_ex("example.invalid"),
    ):
        try:
            lookup()
        except OSError as error:
            assert "E2E backend egress blocked before DNS lookup" in str(error), str(error)
        else:
            raise AssertionError("non-loopback DNS lookup was not blocked")

    for connect in (socket.socket.connect, socket.socket.connect_ex):
        sock = socket.socket()
        try:
            connect(sock, ("203.0.113.1", 80))
        except OSError as error:
            assert "E2E backend egress blocked" in str(error), str(error)
        else:
            raise AssertionError("non-loopback socket connection was not blocked")
        finally:
            sock.close()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        try:
            sock.sendto(b"blocked", ("203.0.113.1", 80))
        except OSError as error:
            assert "E2E backend egress blocked" in str(error), str(error)
        else:
            raise AssertionError("non-loopback datagram was not blocked")
    finally:
        sock.close()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        try:
            sock.sendmsg([b"blocked"], [], 0, ("203.0.113.1", 80))
        except OSError as error:
            assert "E2E backend egress blocked" in str(error), str(error)
        else:
            raise AssertionError("non-loopback sendmsg datagram was not blocked")
    finally:
        sock.close()

    sock = socket.socket()
    try:
        try:
            sock.connect_ex(("127.0.0.1", 1))
        except ConnectionRefusedError:
            pass  # loopback was allowed and reached the OS
        except OSError as error:
            assert "E2E backend egress blocked" not in str(error), str(error)
    finally:
        sock.close()

    # Mirror Playwright's webServer PYTHONPATH injection in a fresh interpreter;
    # sitecustomize must load before application startup code runs.
    guard_dir = str(Path(__file__).resolve().parent / "python_guard")
    startup_env = os.environ.copy()
    startup_env["PYTHONPATH"] = guard_dir + os.pathsep + startup_env.get("PYTHONPATH", "")
    startup_probe = subprocess.run(
        [
            sys.executable,
            "-c",
            "import socket, sys; assert 'sitecustomize' in sys.modules; "
            "socket.gethostbyname('example.invalid')",
        ],
        env=startup_env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert startup_probe.returncode != 0, "startup-injected guard did not block DNS"
    assert "E2E backend egress blocked before DNS lookup" in startup_probe.stderr, startup_probe.stderr

    print("PASS: non-loopback DNS and socket egress are blocked; startup injection loads the guard")


if __name__ == "__main__":
    main()
