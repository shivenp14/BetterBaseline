"""Block non-loopback socket connections in the E2E backend process."""

import ipaddress
import socket


_original_connect = socket.socket.connect
_original_connect_ex = socket.socket.connect_ex
_original_sendto = socket.socket.sendto
_original_sendmsg = socket.socket.sendmsg
_original_getaddrinfo = socket.getaddrinfo
_original_gethostbyname = socket.gethostbyname
_original_gethostbyname_ex = socket.gethostbyname_ex


def _is_loopback(address):
    if not isinstance(address, tuple) or not address:
        return False
    host = address[0]
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _is_loopback_host(host):
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _guarded_getaddrinfo(host, *args, **kwargs):
    if not _is_loopback_host(host):
        raise OSError(f"E2E backend egress blocked before DNS lookup for: {host!r}")
    return _original_getaddrinfo(host, *args, **kwargs)


def _guarded_gethostbyname(host):
    if not _is_loopback_host(host):
        raise OSError(f"E2E backend egress blocked before DNS lookup for: {host!r}")
    return _original_gethostbyname(host)


def _guarded_gethostbyname_ex(host):
    if not _is_loopback_host(host):
        raise OSError(f"E2E backend egress blocked before DNS lookup for: {host!r}")
    return _original_gethostbyname_ex(host)


def _guarded_connect(self, address):
    if not _is_loopback(address):
        raise OSError(f"E2E backend egress blocked for non-loopback address: {address!r}")
    return _original_connect(self, address)


def _guarded_connect_ex(self, address):
    if not _is_loopback(address):
        raise OSError(f"E2E backend egress blocked for non-loopback address: {address!r}")
    return _original_connect_ex(self, address)


def _guarded_sendto(self, data, *args):
    address = args[-1] if len(args) == 2 else args[0]
    if not _is_loopback(address):
        raise OSError(f"E2E backend egress blocked for non-loopback datagram address: {address!r}")
    return _original_sendto(self, data, *args)


def _guarded_sendmsg(self, buffers, ancdata=(), flags=0, address=None):
    if address is not None and not _is_loopback(address):
        raise OSError(f"E2E backend egress blocked for non-loopback datagram address: {address!r}")
    return _original_sendmsg(self, buffers, ancdata, flags, address)


socket.socket.connect = _guarded_connect
socket.socket.connect_ex = _guarded_connect_ex
socket.socket.sendto = _guarded_sendto
socket.socket.sendmsg = _guarded_sendmsg
socket.getaddrinfo = _guarded_getaddrinfo
socket.gethostbyname = _guarded_gethostbyname
socket.gethostbyname_ex = _guarded_gethostbyname_ex
