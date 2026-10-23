"""Reproduction helpers: curl commands that use token placeholders, never real secrets."""
from __future__ import annotations

import shlex
from urllib.parse import urlsplit

from .config import Identity
from .http_engine import INVALID_TOKEN, RawResponse


def curl_command(raw: RawResponse, identity: Identity | None, mode: str) -> str:
    parts = ["curl", "-i", "-X", raw.method, shlex.quote(raw.url)]
    if mode == "invalid":
        parts += ["-H", shlex.quote(f"Authorization: Bearer {INVALID_TOKEN}")]
    elif mode == "identity" and identity is not None and not identity.anonymous:
        var = f"${identity.token_env}"
        if identity.auth.type == "bearer":
            parts += ["-H", f'"Authorization: Bearer {var}"']
        elif identity.auth.type == "header":
            parts += ["-H", f'"{identity.auth.header_name}: {var}"']
        elif identity.auth.type == "cookie":
            parts += ["-H", f'"Cookie: {identity.auth.cookie_name}={var}"']
    if raw.request_body:
        parts += ["-H", shlex.quote("Content-Type: application/json"), "-d", shlex.quote(raw.request_body)]
    return " ".join(parts)


def pytest_snippet(index: int, module: str, name: str, method: str, url: str, identity: Identity | None,
                   mode: str, expected: str, body: str | None) -> str:
    parts = urlsplit(url)
    path = parts.path + (f"?{parts.query}" if parts.query else "")
    headers = "{}"
    if mode == "invalid":
        headers = f'{{"Authorization": "Bearer {INVALID_TOKEN}"}}'
    elif mode == "identity" and identity is not None and not identity.anonymous:
        env = identity.token_env
        if identity.auth.type == "bearer":
            headers = f'{{"Authorization": "Bearer " + os.environ["{env}"]}}'
        elif identity.auth.type == "header":
            headers = f'{{"{identity.auth.header_name}": os.environ["{env}"]}}'
        elif identity.auth.type == "cookie":
            headers = f'{{"Cookie": "{identity.auth.cookie_name}=" + os.environ["{env}"]}}'
    check = "assert resp.status_code in DENIED" if expected == "deny" else "assert resp.status_code < 300"
    json_arg = f", json={body}" if body else ""
    func = "".join(c if c.isalnum() else "_" for c in f"{module}_{index}_{name}".lower())[:80]
    return (
        f"def test_{func}():\n"
        f'    """{name} - expected: {expected}"""\n'
        f"    resp = httpx.request({method!r}, BASE_URL + {path!r}, headers={headers}{json_arg}, timeout=10)\n"
        f"    {check}\n"
    )
