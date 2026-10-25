"""OpenAPI 3.x / Swagger 2.0 import -> Endpoint list.

OpenAPI says *how* to authenticate, not *who owns what*, so the importer only proposes access
rules (marked ``inferred``); the user confirms them in the Permission Matrix.
"""
from __future__ import annotations

import json
import re
from typing import Any

import yaml

from .config import Endpoint, ProjectConfig

HTTP_METHODS = ("get", "put", "post", "delete", "patch")


class ImportErrorInfo(ValueError):
    pass


def parse_document(content: str) -> dict[str, Any]:
    try:
        doc = json.loads(content)
    except ValueError:
        try:
            doc = yaml.safe_load(content)
        except yaml.YAMLError as exc:
            raise ImportErrorInfo(f"not valid JSON or YAML: {exc}") from exc
    if not isinstance(doc, dict) or "paths" not in doc:
        raise ImportErrorInfo("document has no 'paths' - is this an OpenAPI/Swagger file?")
    if not (str(doc.get("openapi", "")).startswith("3") or str(doc.get("swagger", "")).startswith("2")):
        raise ImportErrorInfo("missing 'openapi: 3.x' or 'swagger: 2.0' marker")
    return doc


def _resolve(doc: dict, node: Any, depth: int = 0) -> Any:
    if isinstance(node, dict) and "$ref" in node and depth < 8:
        ref = node["$ref"]
        if isinstance(ref, str) and ref.startswith("#/"):
            cur: Any = doc
            for part in ref[2:].split("/"):
                cur = cur.get(part.replace("~1", "/").replace("~0", "~"), {}) if isinstance(cur, dict) else {}
            return _resolve(doc, cur, depth + 1)
    return node


def example_from_schema(doc: dict, schema: Any, depth: int = 0) -> Any:
    schema = _resolve(doc, schema)
    if not isinstance(schema, dict) or depth > 4:
        return None
    if "example" in schema:
        return schema["example"]
    if "default" in schema:
        return schema["default"]
    if schema.get("enum"):
        return schema["enum"][0]
    for key in ("allOf", "oneOf", "anyOf"):
        if schema.get(key):
            parts = [example_from_schema(doc, s, depth + 1) for s in schema[key]]
            if key == "allOf":
                merged: dict = {}
                for p in parts:
                    if isinstance(p, dict):
                        merged.update(p)
                return merged
            return parts[0]
    t = schema.get("type")
    if t == "object" or "properties" in schema:
        props = schema.get("properties", {})
        required = set(schema.get("required", []))
        return {k: example_from_schema(doc, v, depth + 1) for k, v in props.items()
                if k in required or len(props) <= 6}
    if t == "array":
        item = example_from_schema(doc, schema.get("items", {}), depth + 1)
        return [item] if item is not None else []
    return {"string": "string", "integer": 1, "number": 1, "boolean": True}.get(t)


def _singular(word: str) -> str:
    word = re.sub(r"[^a-zA-Z0-9]", "", word)
    if word.endswith("ies"):
        return word[:-3] + "y"
    if word.endswith("ses"):
        return word[:-2]
    if word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def _resource_type_for(path: str, param: str) -> str:
    base = re.sub(r"(_id|Id|_uuid|Uuid|_ID)$", "", param)
    if base and base != param:
        return _singular(base).lower()
    segments = [s for s in path.split("/") if s]  # generic {id}: use the preceding path segment
    idx = segments.index("{" + param + "}")
    return _singular(segments[idx - 1]).lower() if idx > 0 else "object"


def _security(doc: dict, op: dict) -> str:
    """public | authenticated | unknown - from OpenAPI semantics."""
    schemes = (doc.get("components", {}) or {}).get("securitySchemes") or doc.get("securityDefinitions")
    sec = op.get("security", doc.get("security"))
    if sec is None:
        return "authenticated" if not schemes else "public"
    if sec == [] or all(s == {} for s in sec):
        return "public"
    return "authenticated"


def infer_rules(method: str, path: str, public: bool) -> dict[str, Any]:
    """Proposed access rule for an endpoint (shared by OpenAPI and Postman import)."""
    method = method.lower()
    path_params = re.findall(r"{([^}/]+)}", path)
    access, allow_roles = ("public" if public else "authenticated"), []
    rtype = _resource_type_for(path, path_params[-1]) if path_params else None
    param_types = {p: _resource_type_for(path, p) for p in path_params} if len(path_params) > 1 else {}
    list_of = None
    segments = [s for s in path.split("/") if s]
    if re.search(r"(^|/)(admin|internal|management|backoffice)(/|$)", path, re.I):
        access, allow_roles = "roles", ["admin"]
    elif access != "public" and rtype and method in ("get", "put", "patch", "delete"):
        access, allow_roles = "owner", ["admin"]
    if method == "get" and not path_params and segments and segments[-1].endswith("s"):
        list_of = _singular(segments[-1]).lower()
    return {"access": access, "allow_roles": allow_roles, "resource_type": rtype, "list_of": list_of,
            "param_types": param_types}


def endpoints_from_openapi(doc: dict[str, Any]) -> list[Endpoint]:
    out: list[Endpoint] = []
    for path, item in (doc.get("paths") or {}).items():
        if not isinstance(item, dict) or not path.startswith("/"):
            continue
        shared_params = [_resolve(doc, p) for p in item.get("parameters", [])]
        for method in HTTP_METHODS:
            op = item.get(method)
            if not isinstance(op, dict):
                continue
            params = shared_params + [_resolve(doc, p) for p in op.get("parameters", [])]
            path_params = re.findall(r"{([^}/]+)}", path)  # the template is authoritative
            query = {}
            for p in params:
                if p.get("in") == "query" and p.get("required"):
                    ex = example_from_schema(doc, p.get("schema", {}))
                    query[p["name"]] = str(ex if ex is not None else "1")

            rules = infer_rules(method, path, _security(doc, op) == "public")

            body = None
            rb = _resolve(doc, op.get("requestBody", {}))
            if isinstance(rb, dict):
                media = (rb.get("content") or {}).get("application/json")
                if media:
                    body = media.get("example") or example_from_schema(doc, media.get("schema", {}))
            elif method in ("post", "put", "patch"):
                for p in params:
                    if p.get("in") == "body":
                        body = example_from_schema(doc, p.get("schema", {}))
            try:
                out.append(Endpoint(
                    method=method.upper(), path=path, summary=op.get("summary") or op.get("operationId"),
                    tags=list(op.get("tags", [])), **rules, query=query, body=body,
                    source="openapi", inferred=True,
                ))
            except ValueError:
                continue
    return out


def merge_endpoints(cfg: ProjectConfig, imported: list[Endpoint], replace: bool = False) -> dict[str, int]:
    """Merge into cfg. Existing endpoints keep their (hand-tuned) rules; new ones are appended."""
    existing = {e.key: e for e in cfg.endpoints}
    added = updated = 0
    for ep in imported:
        cur = existing.get(ep.key)
        if cur is None:
            cfg.endpoints.append(ep)
            added += 1
        elif replace or (cur.inferred and cur.source in ("openapi", "postman")):
            idx = cfg.endpoints.index(cur)
            ep.enabled = cur.enabled
            cfg.endpoints[idx] = ep
            updated += 1
    return {"added": added, "updated": updated, "total": len(cfg.endpoints)}
