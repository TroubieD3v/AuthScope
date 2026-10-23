"""Guard rails for the test engine: host allow-list, address checks, redirects, rate/budget limits.

Nothing in the engine talks to the network except through ``TargetGuard``-checked requests.
"""
from __future__ import annotations

import asyncio
import ipaddress
import socket
import time
from urllib.parse import urljoin, urlsplit

from .config import MUTATING_METHODS, TargetConfig


class SafetyError(Exception):
    """A request was refused by a safety rule (never sent)."""


class BudgetExceeded(SafetyError):
    pass


_ALWAYS_BLOCKED_NETS = [
    ipaddress.ip_network("169.254.0.0/16"),  # link-local, cloud metadata (169.254.169.254)
    ipaddress.ip_network("fe80::/10"),
    ipaddress.ip_network("fd00:ec2::/32"),  # AWS IPv6 metadata
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("224.0.0.0/4"),
    ipaddress.ip_network("ff00::/8"),
]


def _default_port(scheme: str) -> int:
    return 443 if scheme == "https" else 80


def ip_is_forbidden(ip: ipaddress._BaseAddress) -> bool:
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    if ip.is_unspecified or ip.is_multicast or ip.is_link_local:
        return True
    return any(ip in net for net in _ALWAYS_BLOCKED_NETS if net.version == ip.version)


class RateLimiter:
    def __init__(self, rps: float) -> None:
        self._interval = 1.0 / rps
        self._next = 0.0
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            now = time.monotonic()
            wait = self._next - now
            if wait > 0:
                await asyncio.sleep(wait)
                now = time.monotonic()
            self._next = max(now, self._next) + self._interval


class RequestBudget:
    def __init__(self, maximum: int) -> None:
        self.maximum = maximum
        self.used = 0

    def consume(self) -> None:
        if self.used >= self.maximum:
            raise BudgetExceeded(f"request budget of {self.maximum} exhausted")
        self.used += 1


class TargetGuard:
    def __init__(self, target: TargetConfig) -> None:
        self.target = target
        base = urlsplit(target.base_url)
        self._base_port = base.port or _default_port(base.scheme)
        self._allowed: dict[str, set[int | None]] = {}
        for entry in target.allowed_hosts:
            host, _, port = entry.partition(":") if entry.count(":") == 1 else (entry, "", "")
            self._allowed.setdefault(host.lower().strip("[]"), set()).add(int(port) if port else None)

    # -- URL / method checks -----------------------------------------------------------
    def check_url(self, url: str) -> None:
        parts = urlsplit(url)
        if parts.scheme not in ("http", "https"):
            raise SafetyError(f"scheme '{parts.scheme}' is not allowed")
        if parts.username or parts.password:
            raise SafetyError("credentials in URL are not allowed")
        host = (parts.hostname or "").lower()
        if host not in self._allowed:
            raise SafetyError(f"host '{host}' is not in allowed_hosts")
        port = parts.port or _default_port(parts.scheme)
        ports = self._allowed[host]
        if None in ports:
            if port != self._base_port:
                raise SafetyError(f"port {port} differs from the target port {self._base_port}")
        elif port not in ports:
            raise SafetyError(f"port {port} is not allowed for host '{host}'")

    def check_method(self, method: str) -> None:
        if method.upper() in MUTATING_METHODS and not self.target.allow_mutating:
            raise SafetyError(f"{method} refused: mutating mode is disabled")

    def build_url(self, path: str) -> str:
        if not path.startswith("/") or path.startswith("//") or "://" in path or "\\" in path:
            raise SafetyError(f"unsafe path '{path}'")
        url = self.target.base_url + path
        self.check_url(url)
        if urlsplit(url).hostname != urlsplit(self.target.base_url).hostname:
            raise SafetyError("path changes the request host")
        return url

    def resolve_redirect(self, current_url: str, location: str) -> str:
        url = urljoin(current_url, location)
        self.check_url(url)
        return url

    # -- DNS / address check -----------------------------------------------------------
    async def check_resolved(self, url: str) -> None:
        parts = urlsplit(url)
        host = parts.hostname or ""
        port = parts.port or _default_port(parts.scheme)
        try:
            literal = ipaddress.ip_address(host)
            addrs = [literal]
        except ValueError:
            loop = asyncio.get_running_loop()
            try:
                infos = await loop.getaddrinfo(host, port, type=socket.SOCK_STREAM)
            except socket.gaierror as exc:
                raise SafetyError(f"cannot resolve '{host}': {exc}") from exc
            addrs = [ipaddress.ip_address(i[4][0].split("%")[0]) for i in infos]
        for ip in addrs:
            if ip_is_forbidden(ip):
                raise SafetyError(f"'{host}' resolves to forbidden address {ip}")
