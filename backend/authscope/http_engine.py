"""Async HTTP engine. Every request passes the guard, rate limiter and request budget."""
from __future__ import annotations

import asyncio
import base64
import json
import os
import random
import time
from dataclasses import dataclass, field
from typing import Any, Callable
from urllib.parse import quote

import httpx

from .config import SAFE_METHODS, Identity, TargetConfig
from .models import HttpExchange
from .masking import Masker
from .safety import BudgetExceeded, RateLimiter, RequestBudget, SafetyError, TargetGuard

MAX_RESPONSE_BYTES = 1_000_000
INVALID_TOKEN = "authscope-invalid-token"
_KEPT_RESPONSE_HEADERS = {"content-type", "content-length", "location", "www-authenticate", "cache-control"}


SECRET_KINDS = ("token", "password")


class SecretStore:
    """Runtime secrets (in memory only) with environment-variable fallback.

    Kinds: ``token`` (the credential) and ``password`` (for identities that log in).
    """

    def __init__(self) -> None:
        self._runtime: dict[tuple[str, str, str], str] = {}

    def set(self, project_id: str, identity: str, value: str, kind: str = "token") -> None:
        self._runtime[(project_id, identity, kind)] = value

    def delete(self, project_id: str, identity: str, kind: str | None = None) -> None:
        for k in [k for k in self._runtime if k[:2] == (project_id, identity) and (kind is None or k[2] == kind)]:
            del self._runtime[k]

    @staticmethod
    def _env_name(identity: Identity, kind: str) -> str | None:
        return {"token": identity.token_env, "password": identity.password_env}[kind]

    def get(self, project_id: str, identity: Identity, kind: str = "token") -> str | None:
        if identity.anonymous:
            return None
        val = self._runtime.get((project_id, identity.name, kind))
        if val:
            return val
        env = self._env_name(identity, kind)
        return os.environ.get(env) if env else None

    def source(self, project_id: str, identity: Identity, kind: str = "token") -> str:
        if identity.anonymous:
            return "none"
        if (project_id, identity.name, kind) in self._runtime:
            return "runtime"
        env = self._env_name(identity, kind)
        if env and os.environ.get(env):
            return "env"
        if kind == "token" and identity.login:
            return "login"
        return "missing"

    def resolver(self, project_id: str, kind: str = "token") -> Callable[[Identity], str | None]:
        return lambda identity: self.get(project_id, identity, kind)

    def has(self, project_id: str, identity: Identity) -> bool:
        return identity.anonymous or bool(self.get(project_id, identity))


@dataclass
class RawResponse:
    """Unmasked response used for comparison. Never persisted - convert via ``exchange``."""

    method: str
    url: str
    label: str
    identity: str | None
    request_headers: dict[str, str]
    request_body: str | None
    status: int | None = None
    headers: dict[str, str] = field(default_factory=dict)
    text: str = ""
    elapsed_ms: float = 0.0
    error: str | None = None
    redirect_chain: list[str] = field(default_factory=list)
    attempts: int = 1
    _json: Any = field(default=None, repr=False)
    _json_parsed: bool = field(default=False, repr=False)

    @property
    def json(self) -> Any:
        if not self._json_parsed:
            self._json_parsed = True
            try:
                self._json = json.loads(self.text) if self.text.strip() else None
            except ValueError:
                self._json = None
        return self._json

    @property
    def is_json(self) -> bool:
        return self.json is not None or self.text.strip() in ("null",)

    def exchange(self, masker: Masker) -> HttpExchange:
        return HttpExchange(
            label=self.label, identity=self.identity, method=self.method,
            url=masker.text(self.url),
            request_headers=masker.headers(self.request_headers),
            request_body=masker.body(self.request_body),
            status=self.status,
            response_headers={k: masker.text(v) for k, v in self.headers.items()
                              if k.lower() in _KEPT_RESPONSE_HEADERS},
            response_body=masker.body(self.text),
            elapsed_ms=round(self.elapsed_ms, 1), error=self.error,
        )


_sleep = asyncio.sleep  # indirection so tests can skip real waiting


def retry_after(value: str | None, default: float = 1.0) -> float:
    """Seconds to wait from a Retry-After header (delta-seconds or HTTP date)."""
    if not value:
        return default
    value = value.strip()
    if value.isdigit():
        return float(value)
    try:
        from email.utils import parsedate_to_datetime
        from datetime import datetime, timezone

        when = parsedate_to_datetime(value)
        return max(0.0, (when - datetime.now(timezone.utc)).total_seconds())
    except (TypeError, ValueError):
        return default


def render_path(path: str, params: dict[str, str]) -> str:
    out = path
    for k, v in params.items():
        out = out.replace("{" + k + "}", quote(str(v), safe=""))
    return out


class Requester:
    def __init__(self, target: TargetConfig, resolve_secret: Callable[[Identity], str | None]) -> None:
        self.target = target
        self.guard = TargetGuard(target)
        self.limiter = RateLimiter(target.rate_limit_rps)
        self.budget = RequestBudget(target.max_requests)
        self.retries = 0
        self.backoff_s = 0.0
        self._resolve = resolve_secret
        self._client = httpx.AsyncClient(
            timeout=target.timeout_s, follow_redirects=False, verify=target.verify_tls,
            trust_env=False, headers={"User-Agent": "AuthScope/1.4 (authorization tester)"},
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    def secret_values(self, identities: list[Identity]) -> dict[str, str]:
        """Every credential value that must be masked in evidence."""
        out: dict[str, str] = {}
        for i in identities:
            if tok := self._resolve(i):
                out[i.name] = tok
                if i.auth.type == "basic":
                    pair = f"{i.auth.username}:{tok}" if i.auth.username else tok
                    out[f"{i.name}:basic"] = base64.b64encode(pair.encode()).decode()
        return out

    def token_for(self, identity: Identity | None, mode: str) -> str | None:
        if mode == "invalid":
            return INVALID_TOKEN
        if identity is None or mode == "none":
            return None
        return self._resolve(identity)

    def _auth(self, identity: Identity | None, mode: str) -> tuple[dict[str, str], dict[str, str], dict[str, str]]:
        """Headers, cookies and query parameters that carry the credential."""
        headers: dict[str, str] = {}
        cookies: dict[str, str] = {}
        params: dict[str, str] = {}
        token = self.token_for(identity, mode)
        if not token:
            return headers, cookies, params
        auth = identity.auth if identity and mode != "invalid" else None
        kind = auth.type if auth else "bearer"
        if kind == "bearer":
            headers["Authorization"] = f"Bearer {token}"
        elif kind == "header":
            headers[auth.header_name] = token  # type: ignore[union-attr]
        elif kind == "cookie":
            cookies[auth.cookie_name] = token  # type: ignore[union-attr]
        elif kind == "query":
            params[auth.query_name] = token  # type: ignore[union-attr]
        elif kind == "basic":
            pair = f"{auth.username}:{token}" if auth.username else token  # type: ignore[union-attr]
            headers["Authorization"] = "Basic " + base64.b64encode(pair.encode()).decode()
        return headers, cookies, params

    async def _exchange(self, raw: RawResponse, method: str, url: str, pinned, query, headers, content) -> None:
        current = url
        for hop in range(self.target.max_redirects + 1):
            async with self._client.stream(
                method, pinned.url, params=query if hop == 0 else None,
                headers={**headers, "Host": pinned.host}, content=content, extensions=pinned.extensions,
            ) as resp:
                chunks, size = [], 0
                async for chunk in resp.aiter_bytes():
                    size += len(chunk)
                    chunks.append(chunk)
                    if size > MAX_RESPONSE_BYTES:
                        break
                raw.status = resp.status_code
                raw.headers = dict(resp.headers)
                raw.text = b"".join(chunks).decode(resp.encoding or "utf-8", errors="replace")
            loc = raw.headers.get("location")
            if raw.status in (301, 302, 303, 307, 308) and loc and hop < self.target.max_redirects:
                nxt = self.guard.resolve_redirect(current, loc)  # raises SafetyError if off-list
                pinned = await self.guard.pin(nxt)
                self.budget.consume()
                await self.limiter.acquire()
                raw.redirect_chain.append(nxt)
                current = nxt
                if raw.status in (301, 302, 303):
                    method, content = "GET", None
                continue
            break

    async def send(
        self, method: str, path: str, *, identity: Identity | None = None, mode: str = "identity",
        query: dict[str, str] | None = None, body: Any = None, label: str = "request",
        login: bool = False,
    ) -> RawResponse:
        """Send one request. Safety violations raise; network errors are returned in ``error``.

        ``login=True`` is only used for the identity's own login call, which is allowed to POST
        even in read-only mode.
        """
        method = method.upper()
        if not login:
            self.guard.check_method(method)
        url = self.guard.build_url(path)
        pinned = await self.guard.pin(url)
        self.budget.consume()
        await self.limiter.acquire()

        headers, cookies, auth_params = self._auth(identity, mode)
        if auth_params:
            query = {**(query or {}), **auth_params}
        content = None
        if body is not None:
            content = json.dumps(body)
            headers["Content-Type"] = "application/json"
        if cookies:  # sent as a header: the request URL carries the pinned IP, not the cookie domain
            headers["Cookie"] = "; ".join(f"{k}={v}" for k, v in cookies.items())
        shown_headers = dict(headers)
        raw = RawResponse(method=method, url=url + (_qs(query) if query else ""), label=label,
                          identity=identity.name if identity else None,
                          request_headers=shown_headers, request_body=content)
        start = time.perf_counter()
        attempt = 0
        while True:
            raw.status, raw.headers, raw.text, raw.error, raw.redirect_chain = None, {}, "", None, []
            delay: float | None = None
            try:
                await self._exchange(raw, method, url, pinned, query, headers, content)
            except SafetyError as exc:
                raw.error = f"blocked by safety rule: {exc}"
            except httpx.TransportError as exc:
                raw.error = f"{type(exc).__name__}: {exc}"
                if method in SAFE_METHODS or login:  # never resend a write that may have been processed
                    delay = min(self.target.retry_after_cap_s, 0.5 * 2 ** attempt) + random.uniform(0, 0.25)
            except httpx.HTTPError as exc:
                raw.error = f"{type(exc).__name__}: {exc}"
            if raw.status == 429:  # the server refused before processing, so any method may be retried
                delay = retry_after(raw.headers.get("retry-after"))
                if delay > self.target.retry_after_cap_s:
                    delay = None
            if delay is None or attempt >= self.target.max_retries or self.budget.used >= self.budget.maximum:
                break
            attempt += 1
            self.retries += 1
            self.backoff_s += delay
            await _sleep(delay)
            pinned = await self.guard.pin(url)
            self.budget.consume()
            await self.limiter.acquire()
        raw.attempts = attempt + 1
        raw.elapsed_ms = (time.perf_counter() - start) * 1000
        return raw


def _qs(query: dict[str, str]) -> str:
    return "?" + "&".join(f"{quote(k)}={quote(str(v))}" for k, v in query.items())


__all__ = ["Requester", "RawResponse", "SecretStore", "render_path", "BudgetExceeded", "SafetyError"]
