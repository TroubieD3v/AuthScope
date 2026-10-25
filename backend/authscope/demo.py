"""Ready-made project for the bundled demo API (backend/demo_api)."""
from __future__ import annotations

from .config import ProjectConfig


def demo_config(base_url: str = "http://127.0.0.1:8000", allowed_hosts: list[str] | None = None) -> ProjectConfig:
    from urllib.parse import urlsplit

    host = urlsplit(base_url).hostname or "127.0.0.1"
    bearer = {"type": "bearer"}
    data = {
        "name": "AuthScope demo API",
        "target": {
            "base_url": base_url,
            "allowed_hosts": allowed_hosts or [host],
            "rate_limit_rps": 50,
            "max_requests": 1000,
            "allow_mutating": False,
            "reset": {"method": "POST", "path": "/__demo/reset", "identity": "admin"},
        },
        "identities": [
            {"name": "guest", "role": "guest", "description": "No credentials"},
            {"name": "alice", "role": "user", "tenant": "acme", "auth": bearer},
            {"name": "bob", "role": "user", "tenant": "acme", "auth": bearer},
            {"name": "carol", "role": "user", "tenant": "globex", "auth": bearer,
             "description": "Token obtained through the login flow",
             "login": {"path": "/api/auth/login", "body": {"username": "carol", "password": "${password}"},
                       "token_path": "access_token"}},
            {"name": "admin", "role": "admin", "auth": bearer},
        ],
        "resources": [
            {"type": "user", "id": "1", "owner": "alice"},
            {"type": "user", "id": "2", "owner": "bob"},
            {"type": "user", "id": "3", "owner": "carol"},
            {"type": "user", "id": "4", "owner": "admin"},
            {"type": "order", "id": "101", "owner": "alice", "parent": "user:1", "label": "Alice's keyboard"},
            {"type": "order", "id": "102", "owner": "bob", "parent": "user:2", "label": "Bob's monitor"},
            {"type": "order", "id": "103", "owner": "carol", "parent": "user:3", "label": "Carol's desk"},
            {"type": "invoice", "id": "201", "owner": "alice", "tenant": "acme"},
            {"type": "invoice", "id": "202", "owner": "carol", "tenant": "globex"},
        ],
        "endpoints": [
            {"method": "GET", "path": "/health", "access": "public", "summary": "Liveness probe"},
            {"method": "GET", "path": "/api/users/me", "access": "authenticated", "summary": "Current user"},
            {"method": "GET", "path": "/api/users/{user_id}", "access": "owner", "allow_roles": ["admin"],
             "resource_type": "user", "summary": "Get a user",
             "restricted_fields": [{"name": "internalNotes", "roles": ["admin"]},
                                   {"name": "creditLimit", "roles": ["admin"]}]},
            {"method": "PUT", "path": "/api/users/{user_id}", "access": "owner", "allow_roles": ["admin"],
             "resource_type": "user", "body": {"username": "renamed-by-authscope"}, "summary": "Update a user"},
            {"method": "GET", "path": "/api/orders", "access": "authenticated", "list_of": "order",
             "summary": "List orders"},
            {"method": "GET", "path": "/api/orders/{order_id}", "access": "owner", "allow_roles": ["admin"],
             "resource_type": "order", "summary": "Get an order"},
            {"method": "PUT", "path": "/api/orders/{order_id}", "access": "owner", "allow_roles": ["admin"],
             "resource_type": "order", "body": {"status": "cancelled"}, "summary": "Update an order"},
            {"method": "GET", "path": "/api/users/{user_id}/orders/{order_id}", "access": "owner",
             "allow_roles": ["admin"], "resource_type": "order", "summary": "Get one of a user's orders (nested)"},
            {"method": "GET", "path": "/api/orders/{order_id}/items", "access": "owner", "allow_roles": ["admin"],
             "resource_type": "order", "summary": "Order items (filtered by design)"},
            {"method": "GET", "path": "/api/invoices/{invoice_id}", "access": "tenant", "allow_roles": ["admin"],
             "resource_type": "invoice", "summary": "Get an invoice"},
            {"method": "GET", "path": "/api/admin/stats", "access": "roles", "allow_roles": ["admin"],
             "summary": "Platform statistics"},
            {"method": "DELETE", "path": "/api/admin/users/{user_id}", "access": "roles", "allow_roles": ["admin"],
             "resource_type": "user", "summary": "Delete a user"},
            {"method": "GET", "path": "/api/reports/summary", "access": "authenticated", "summary": "Sales summary"},
            {"method": "POST", "path": "/__demo/reset", "access": "roles", "allow_roles": ["admin"],
             "enabled": False, "summary": "Demo reset hook (used by the engine, not tested)"},
        ],
        "tests": [
            {"name": "Owner order access", "path": "/api/orders/101", "identity": "alice",
             "expected": "allow", "resource": "order:101"},
            {"name": "Cross-user order access", "path": "/api/orders/101", "identity": "bob",
             "expected": "deny", "resource": "order:101", "baseline_identity": "alice"},
        ],
    }
    return ProjectConfig.model_validate(data)


def demo_secrets() -> dict[tuple[str, str], str]:
    """(identity, kind) -> value for the demo API's throwaway credentials."""
    from demo_api.fixtures import PASSWORDS, TOKENS

    out = {(n, "token"): t for n, t in TOKENS.items() if n != "carol"}  # carol logs in instead
    out[("carol", "password")] = PASSWORDS["carol"]
    return out
