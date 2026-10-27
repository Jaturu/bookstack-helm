import socket

import pytest


class NetworkAccessDenied(RuntimeError):
    pass


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """The report scripts only read local JSON. Enforce that the suite runs
    offline rather than trusting every test to avoid the network."""

    def deny(*args, **kwargs):
        raise NetworkAccessDenied("a test tried to open a real connection")

    monkeypatch.setattr(socket.socket, "connect", deny)
    monkeypatch.setattr(socket.socket, "connect_ex", deny)
    monkeypatch.setattr(socket, "create_connection", deny)
