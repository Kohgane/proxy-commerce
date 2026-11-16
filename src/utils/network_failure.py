"""Bounded, credential-free classification of wrapped network exceptions."""
import socket
import ssl

from requests import exceptions as req
from urllib3 import exceptions as urllib


def failure_kind(error: BaseException) -> str:
    """Inspect exception objects only; never stringify URLs, headers or messages."""
    pending = [error]
    seen = set()
    found = set()
    while pending and len(seen) < 16:
        item = pending.pop()
        if not isinstance(item, BaseException) or id(item) in seen:
            continue
        seen.add(id(item))
        for types, kind in (
            ((req.ProxyError, urllib.ProxyError), "proxy"),
            ((req.SSLError, urllib.SSLError, ssl.SSLError), "tls"),
            ((socket.gaierror,), "dns"),
            ((ConnectionRefusedError,), "connection_refused"),
            ((ConnectionResetError,), "connection_reset"),
            ((req.Timeout, urllib.TimeoutError, TimeoutError), "timeout"),
        ):
            if isinstance(item, types):
                found.add(kind)
        pending.extend(x for x in (
            item.__cause__, item.__context__, getattr(item, "reason", None),
            getattr(item, "original_error", None), *item.args[:8],
        ) if isinstance(x, BaseException))
    # Proxy context takes precedence: an inner DNS error may be the proxy host.
    return next((kind for kind in (
        "proxy", "tls", "dns", "connection_refused", "connection_reset", "timeout"
    ) if kind in found), "unknown")
