"""Test-only backend egress guard; calculation sockets stay loopback-only."""
import ipaddress
import socket

_connect = socket.socket.connect
_connect_ex = socket.socket.connect_ex


def allowed(address):
    if not isinstance(address, tuple):
        return True  # Unix sockets do not reach the network.
    host = address[0]
    if host == 'localhost':
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def connect(self, address):
    if not allowed(address):
        raise OSError('Integration offline guard blocked external socket')
    return _connect(self, address)


def connect_ex(self, address):
    if not allowed(address):
        raise OSError('Integration offline guard blocked external socket')
    return _connect_ex(self, address)


socket.socket.connect = connect
socket.socket.connect_ex = connect_ex
