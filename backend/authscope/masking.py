"""Redaction of tokens and sensitive data before anything is stored or shown."""
from __future__ import annotations

import json
import re
from typing import Any

SENSITIVE_HEADERS = {
    "authorization", "proxy-authorization", "cookie", "set-cookie", "x-api-key",
    "x-auth-token", "x-csrf-token", "x-xsrf-token",
}
SENSITIVE_KEY_RE = re.compile(
    r"(pass(word|wd)?|secret|token|api[-_]?key|authorization|credential|private[-_]?key|"
    r"ssn|social[-_]?security|card[-_]?(number|no)|cvv|cvc|iban|session)", re.I)
_JWT_RE = re.compile(r"eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{4,}")
_BEARER_RE = re.compile(r"(?i)\b(bearer|basic)\s+[A-Za-z0-9._~+/=-]{8,}")
_CARD_RE = re.compile(r"\b(?:\d[ -]?){13,19}\b")
_EMAIL_RE = re.compile(r"\b([A-Za-z0-9._%+-])[A-Za-z0-9._%+-]*@([A-Za-z0-9])[A-Za-z0-9.-]*(\.[A-Za-z]{2,})\b")
REDACTED = "***REDACTED***"
MAX_BODY_CHARS = 2000


class Masker:
    """Masks known secret values plus generic token / PII patterns."""

    def __init__(self, secrets: dict[str, str] | None = None) -> None:
        # secret value -> placeholder; longest first so overlapping values are handled
        self._secrets = sorted(
            ((v, f"{{{{token:{k}}}}}") for k, v in (secrets or {}).items() if v and len(v) >= 4),
            key=lambda kv: -len(kv[0]),
        )

    def text(self, value: str) -> str:
        for secret, placeholder in self._secrets:
            value = value.replace(secret, placeholder)
        value = _JWT_RE.sub(REDACTED, value)
        value = _BEARER_RE.sub(lambda m: f"{m.group(1)} {REDACTED}", value)
        value = _CARD_RE.sub(lambda m: "****" if _luhn(m.group(0)) else m.group(0), value)
        return _EMAIL_RE.sub(lambda m: f"{m.group(1)}***@{m.group(2)}***{m.group(3)}", value)

    def headers(self, headers: dict[str, str]) -> dict[str, str]:
        out = {}
        for k, v in headers.items():
            out[self.text(k)] = REDACTED if k.lower() in SENSITIVE_HEADERS else self.text(v)
        return out

    def json_value(self, value: Any, key: str | None = None) -> Any:
        if key is not None and SENSITIVE_KEY_RE.search(key) and value not in (None, "", [], {}):
            return REDACTED
        if isinstance(value, dict):
            return {self.text(k): self.json_value(v, k) for k, v in value.items()}  # secrets can hide in keys too
        if isinstance(value, list):
            return [self.json_value(v, key) for v in value]
        if isinstance(value, str):
            return self.text(value)
        return value

    def body(self, raw: str | None, limit: int = MAX_BODY_CHARS) -> str | None:
        if raw is None or raw == "":
            return raw
        try:
            text = json.dumps(self.json_value(json.loads(raw)), indent=2, ensure_ascii=False)
        except (ValueError, TypeError):
            text = self.text(raw)
        if len(text) > limit:
            text = text[:limit] + f"\n... [truncated, {len(text) - limit} more chars]"
        return text


def _luhn(candidate: str) -> bool:
    digits = [int(c) for c in candidate if c.isdigit()]
    if not 13 <= len(digits) <= 19:
        return False
    total = 0
    for i, d in enumerate(reversed(digits)):
        if i % 2:
            d = d * 2 - 9 if d > 4 else d * 2
        total += d
    return total % 10 == 0
