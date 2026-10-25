"""Postman Collection (v2.0 / v2.1) import -> Endpoint list.

Path variables (``:orderId``) and collection variables used as path segments (``{{orderId}}``)
become ``{orderId}`` templates. A leading ``{{baseUrl}}``-style host variable is dropped, since the
target base URL comes from the project. Like the OpenAPI importer, access rules are only inferred.
"""
from __future__ import annotations

import json
import re
from typing import Any

from .config import Endpoint
from .openapi_import import ImportErrorInfo, infer_rules

METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE"}


def is_postman(doc: Any) -> bool:
    info = doc.get("info") if isinstance(doc, dict) else None
    return isinstance(info, dict) and ("_postman_id" in info or "postman" in str(info.get("schema", "")))


def parse_collection(content: str) -> dict[str, Any]:
    try:
        doc = json.loads(content)
    except ValueError as exc:
        raise ImportErrorInfo(f"Postman collections are JSON: {exc}") from exc
    if not is_postman(doc) or not isinstance(doc.get("item"), list):
        raise ImportErrorInfo("not a Postman collection (missing info.schema / item)")
    return doc


def _path_of(url: Any) -> str | None:
    if isinstance(url, str):
        raw = url
    elif isinstance(url, dict):
        if isinstance(url.get("path"), list):
            segs = [s if isinstance(s, str) else str(s.get("value", "")) for s in url["path"]]
            return "/" + "/".join(s for s in segs if s)
        raw = url.get("raw", "")
    else:
        return None
    raw = raw.split("?", 1)[0].split("#", 1)[0]
    raw = re.sub(r"^\{\{[^}]+\}\}", "", raw)  # {{baseUrl}}
    raw = re.sub(r"^[a-z]+://[^/]+", "", raw)  # absolute URL -> path
    return raw or "/"


def _template(path: str) -> str:
    segs = []
    for seg in path.split("/"):
        if seg.startswith(":") and len(seg) > 1:
            seg = "{" + seg[1:] + "}"
        seg = re.sub(r"\{\{([^}]+)\}\}", r"{\1}", seg)
        segs.append(seg)
    out = "/".join(segs)
    return out if out.startswith("/") else "/" + out


def _body(req: dict[str, Any]) -> Any:
    body = req.get("body")
    if not isinstance(body, dict) or body.get("mode") != "raw":
        return None
    raw = re.sub(r"\{\{[^}]+\}\}", "1", body.get("raw") or "")  # placeholders -> harmless value
    try:
        return json.loads(raw) if raw.strip() else None
    except ValueError:
        return None


def _walk(items: list[Any], inherited_auth: Any, folder: list[str], out: list[Endpoint]) -> None:
    for item in items:
        if not isinstance(item, dict):
            continue
        auth = item.get("auth", inherited_auth)
        if isinstance(item.get("item"), list):
            _walk(item["item"], auth, folder + [str(item.get("name", ""))], out)
            continue
        req = item.get("request")
        if isinstance(req, str):
            req = {"method": "GET", "url": req}
        if not isinstance(req, dict):
            continue
        method = str(req.get("method", "GET")).upper()
        path = _path_of(req.get("url"))
        if method not in METHODS or not path:
            continue
        path = _template(path)
        req_auth = req.get("auth", auth)
        public = isinstance(req_auth, dict) and req_auth.get("type") == "noauth"
        query: dict[str, str] = {}
        url = req.get("url")
        pairs: list[tuple[str, str]] = []
        if isinstance(url, dict) and isinstance(url.get("query"), list):
            pairs = [(str(q["key"]), str(q.get("value") or "")) for q in url["query"]
                     if isinstance(q, dict) and q.get("key") and not q.get("disabled")]
        else:
            raw = url if isinstance(url, str) else (url or {}).get("raw", "") if isinstance(url, dict) else ""
            if "?" in raw:
                pairs = [tuple((kv.split("=", 1) + [""])[:2]) for kv in raw.split("?", 1)[1].split("#")[0].split("&") if kv]  # type: ignore[misc]
        for key, val in pairs:
            query[key] = "1" if not val or val.startswith("{{") else val
        try:
            out.append(Endpoint(method=method, path=path, summary=item.get("name"),
                                tags=[f for f in folder if f], query=query, body=_body(req),
                                source="postman", inferred=True, **infer_rules(method, path, public)))
        except ValueError:
            continue


def endpoints_from_postman(doc: dict[str, Any]) -> list[Endpoint]:
    out: list[Endpoint] = []
    _walk(doc.get("item", []), doc.get("auth"), [], out)
    unique: dict[str, Endpoint] = {}
    for ep in out:
        unique.setdefault(ep.key, ep)
    return list(unique.values())
