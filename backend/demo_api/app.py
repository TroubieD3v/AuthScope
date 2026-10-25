"""Intentionally vulnerable demo API for AuthScope.

DO NOT deploy this anywhere. Every flaw can be switched off with DEMO_VULNS (comma list of
bola, bfla, bopla, unauth, tenant; empty string = fully secure) so AuthScope's findings can be
verified and its regression behaviour demonstrated.
"""
from __future__ import annotations

import base64
import copy
import os

from typing import Any

from fastapi import Body, Depends, FastAPI, Header, HTTPException, Query
from pydantic import BaseModel

from .fixtures import PASSWORDS, TOKENS, active_vulns

SEED_USERS = {
    1: {"id": 1, "username": "alice", "email": "alice@acme.test", "role": "user", "tenant": "acme",
        "internalNotes": "VIP, handle with care", "creditLimit": 5000},
    2: {"id": 2, "username": "bob", "email": "bob@acme.test", "role": "user", "tenant": "acme",
        "internalNotes": "Chargeback history", "creditLimit": 800},
    3: {"id": 3, "username": "carol", "email": "carol@globex.test", "role": "user", "tenant": "globex",
        "internalNotes": "Competitor employee", "creditLimit": 1200},
    4: {"id": 4, "username": "admin", "email": "admin@platform.test", "role": "admin", "tenant": None,
        "internalNotes": "Platform operator", "creditLimit": 0},
}
SEED_ORDERS = {
    101: {"id": 101, "ownerId": 1, "tenant": "acme", "item": "Mechanical keyboard", "total": 129.9,
          "status": "paid", "shippingAddress": "12 Birch Lane, Springfield"},
    102: {"id": 102, "ownerId": 2, "tenant": "acme", "item": "27in monitor", "total": 349.0,
          "status": "shipped", "shippingAddress": "88 Oak Street, Shelbyville"},
    103: {"id": 103, "ownerId": 3, "tenant": "globex", "item": "Standing desk", "total": 599.0,
          "status": "paid", "shippingAddress": "1 Globex Plaza, Cypress Creek"},
}
SEED_ITEMS = {
    101: [{"sku": "KB-77", "qty": 1}], 102: [{"sku": "MON-27", "qty": 1}], 103: [{"sku": "DESK-9", "qty": 1}],
}
SEED_INVOICES = {
    201: {"id": 201, "tenant": "acme", "orderId": 101, "amount": 129.9, "iban": "DE89370400440532013000"},
    202: {"id": 202, "tenant": "globex", "orderId": 103, "amount": 599.0, "iban": "GB29NWBK60161331926819"},
}

BEARER = {"security": [{"bearerAuth": []}]}
NAME_TO_ID = {"alice": 1, "bob": 2, "carol": 3, "admin": 4}
USERS: dict = {}
ORDERS: dict = {}
INVOICES: dict = {}


def reset_state() -> None:
    for target, seed in ((USERS, SEED_USERS), (ORDERS, SEED_ORDERS), (INVOICES, SEED_INVOICES)):
        target.clear()
        target.update(copy.deepcopy(seed))


reset_state()
_hits: list[float] = []


def _rate_limited() -> bool:
    """DEMO_RATE_LIMIT=N: at most N requests per second (to exercise 429 handling)."""
    limit = int(os.environ.get("DEMO_RATE_LIMIT", "0") or 0)
    if limit <= 0:
        return False
    import time as _t

    now = _t.monotonic()
    while _hits and now - _hits[0] > 1:
        _hits.pop(0)
    if len(_hits) >= limit:
        return True
    _hits.append(now)
    return False


app = FastAPI(title="AuthScope Demo API", version="1.0.0",
              description="Intentionally vulnerable API used to demo AuthScope. Never deploy.")


@app.middleware("http")
async def rate_limit(request, call_next):
    from fastapi.responses import JSONResponse

    if request.url.path not in ("/health", "/__demo/reset") and _rate_limited():
        return JSONResponse({"detail": "Too many requests"}, status_code=429, headers={"Retry-After": "1"})
    return await call_next(request)


def vulns() -> set[str]:
    return active_vulns()


def _user_by_credentials(authorization: str | None, api_key: str | None):
    """Bearer token, HTTP Basic (username + demo password) or ?api_key=<token>."""
    token = api_key
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
    elif authorization and authorization.lower().startswith("basic "):
        try:
            user, _, password = base64.b64decode(authorization[6:].strip()).decode().partition(":")
        except ValueError:
            return None
        return USERS.get(NAME_TO_ID[user]) if PASSWORDS.get(user) == password else None
    if not token:
        return None
    for name, value in TOKENS.items():
        if token == value:
            return USERS.get(NAME_TO_ID[name])
    return None


def current_user(authorization: str | None = Header(default=None), api_key: str | None = Query(default=None)):
    user = _user_by_credentials(authorization, api_key)
    if not user:
        raise HTTPException(401, "Authentication required")
    return user


def maybe_user(authorization: str | None = Header(default=None), api_key: str | None = Query(default=None)):
    return _user_by_credentials(authorization, api_key)


def public_user(user: dict, viewer: dict) -> dict:
    out = dict(user)
    sees_private = viewer["role"] == "admin" or "bopla" in vulns()
    if not sees_private:
        out.pop("internalNotes", None)
        out.pop("creditLimit", None)
    return out


def order_view(order: dict) -> dict:
    return {k: v for k, v in order.items()}


def can_read_order(order: dict, user: dict) -> bool:
    if user["role"] == "admin" or order["ownerId"] == user["id"]:
        return True
    if order["tenant"] == user["tenant"]:
        return "bola" in vulns()
    return "tenant" in vulns()


class LoginRequest(BaseModel):
    username: str
    password: str


@app.post("/api/auth/login", tags=["auth"], summary="Log in, returns a bearer token", openapi_extra={"security": []})
def login(body: LoginRequest):
    if PASSWORDS.get(body.username) != body.password:
        raise HTTPException(401, "Invalid credentials")
    return {"access_token": TOKENS[body.username], "token_type": "bearer"}


# -- public ----------------------------------------------------------------------------
@app.get("/health", tags=["system"], summary="Liveness probe", openapi_extra={"security": []})
def health():
    return {"status": "ok", "mode": "vulnerable" if vulns() else "secure", "vulns": sorted(vulns())}


# -- users -----------------------------------------------------------------------------
@app.get("/api/users/me", tags=["users"], summary="Current user", openapi_extra=BEARER)
def me(user=Depends(current_user)):
    return public_user(user, user)


@app.get("/api/users/{user_id}", tags=["users"], summary="Get a user", openapi_extra=BEARER)
def get_user(user_id: int, user=Depends(current_user)):
    target = USERS.get(user_id)
    if not target:
        raise HTTPException(404, "User not found")
    if user["role"] != "admin" and target["id"] != user["id"]:
        if not ("bola" in vulns() and target["tenant"] == user["tenant"]) and not (
                "tenant" in vulns() and target["tenant"] != user["tenant"]):
            raise HTTPException(404, "User not found")
    return public_user(target, user)


USER_WRITABLE = {"username"}
ADMIN_WRITABLE = USER_WRITABLE | {"role", "creditLimit", "internalNotes", "tenant"}


def _apply(target: dict, body: dict[str, Any], allowed: set[str]) -> None:
    for k, v in body.items():
        if k in allowed and k in target:
            target[k] = v


@app.put("/api/users/{user_id}", tags=["users"], summary="Update a user", openapi_extra=BEARER)
def update_user(user_id: int, body: dict[str, Any] = Body(..., examples=[{"username": "new-name"}]),
                user=Depends(current_user)):
    target = USERS.get(user_id)
    if not target:
        raise HTTPException(404, "User not found")
    if user["role"] != "admin" and target["id"] != user["id"] and "bola" not in vulns():
        raise HTTPException(403, "Forbidden")
    _apply(target, body, ADMIN_WRITABLE if user["role"] == "admin" else USER_WRITABLE)
    return public_user(target, user)


# -- orders ----------------------------------------------------------------------------
@app.get("/api/orders", tags=["orders"], summary="List orders", openapi_extra=BEARER)
def list_orders(user=Depends(current_user)):
    return [order_view(o) for o in ORDERS.values() if can_read_order(o, user) or _list_leak(o, user)]


def _list_leak(order: dict, user: dict) -> bool:
    # the list endpoint has its own, laxer filter - a classic copy/paste BOLA
    if "bola" in vulns() and order["tenant"] == user["tenant"]:
        return True
    return "tenant" in vulns() and order["tenant"] != user["tenant"]


@app.get("/api/orders/{order_id}", tags=["orders"], summary="Get an order", openapi_extra=BEARER)
def get_order(order_id: int, user=Depends(current_user)):
    order = ORDERS.get(order_id)
    if not order or not can_read_order(order, user):
        raise HTTPException(404, "Order not found")
    return order_view(order)


@app.put("/api/orders/{order_id}", tags=["orders"], summary="Update an order", openapi_extra=BEARER)
def update_order(order_id: int, body: dict[str, Any] = Body(..., examples=[{"status": "cancelled"}]),
                 user=Depends(current_user)):
    order = ORDERS.get(order_id)
    if not order or not can_read_order(order, user):
        raise HTTPException(404, "Order not found")
    _apply(order, body, {"status", "total"} if user["role"] == "admin" else {"status"})
    return order_view(order)


@app.get("/api/users/{user_id}/orders/{order_id}", tags=["orders"], summary="Get one of a user's orders",
         openapi_extra=BEARER)
def user_order(user_id: int, order_id: int, user=Depends(current_user)):
    """Nested route. Vulnerable: only checks that the order belongs to {user_id}, not that the caller is that user."""
    order = ORDERS.get(order_id)
    if not order or order["ownerId"] != user_id:
        raise HTTPException(404, "Order not found")
    if user["role"] != "admin" and user["id"] != user_id:
        same_tenant = order["tenant"] == user["tenant"]
        if not ("bola" in vulns() and same_tenant or "tenant" in vulns() and not same_tenant):
            raise HTTPException(404, "Order not found")
    return order_view(order)


@app.get("/api/orders/{order_id}/items", tags=["orders"], summary="Order items (filtered)",
         openapi_extra=BEARER)
def order_items(order_id: int, user=Depends(current_user)):
    """Secure-by-filtering: other users get 200 + []. AuthScope must NOT report this as BOLA."""
    order = ORDERS.get(order_id)
    if not order or (order["ownerId"] != user["id"] and user["role"] != "admin"):
        return []
    return SEED_ITEMS.get(order_id, [])


# -- invoices (tenant-scoped) ----------------------------------------------------------
@app.get("/api/invoices/{invoice_id}", tags=["invoices"], summary="Get an invoice",
         openapi_extra=BEARER)
def get_invoice(invoice_id: int, user=Depends(current_user)):
    inv = INVOICES.get(invoice_id)
    if not inv:
        raise HTTPException(404, "Invoice not found")
    if user["role"] != "admin" and inv["tenant"] != user["tenant"] and "tenant" not in vulns():
        raise HTTPException(404, "Invoice not found")
    return inv


# -- admin -----------------------------------------------------------------------------
def require_admin(user=Depends(current_user)):
    if user["role"] != "admin" and "bfla" not in vulns():
        raise HTTPException(403, "Admin role required")
    return user


@app.get("/api/admin/stats", tags=["admin"], summary="Platform statistics", openapi_extra=BEARER)
def admin_stats(user=Depends(require_admin)):
    return {"users": len(USERS), "orders": len(ORDERS), "revenue": round(sum(o["total"] for o in ORDERS.values()), 2)}


@app.delete("/api/admin/users/{user_id}", tags=["admin"], summary="Delete a user", openapi_extra=BEARER)
def delete_user(user_id: int, user=Depends(require_admin)):
    if user_id not in USERS:
        raise HTTPException(404, "User not found")
    del USERS[user_id]
    return {"deleted": user_id}


# -- reports (should require auth) ------------------------------------------------------
@app.get("/api/reports/summary", tags=["reports"], summary="Sales summary", openapi_extra=BEARER)
def reports_summary(user=Depends(maybe_user)):
    if user is None and "unauth" not in vulns():
        raise HTTPException(401, "Authentication required")
    return {"orders": len(ORDERS), "totalRevenue": round(sum(o["total"] for o in ORDERS.values()), 2)}


# -- demo plumbing -----------------------------------------------------------------------
@app.post("/__demo/reset", tags=["system"], summary="Reset demo data (admin only)", openapi_extra=BEARER)
def demo_reset(authorization: str | None = Header(default=None)):
    # checks the admin token directly so the reset still works after the admin user was deleted
    if authorization != f"Bearer {TOKENS['admin']}":
        raise HTTPException(403, "Admin token required")
    reset_state()
    return {"reset": True}


app.openapi_schema = None


def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    from fastapi.openapi.utils import get_openapi
    schema = get_openapi(title=app.title, version=app.version, description=app.description, routes=app.routes)
    schema.setdefault("components", {})["securitySchemes"] = {
        "bearerAuth": {"type": "http", "scheme": "bearer"}}
    app.openapi_schema = schema
    return schema


app.openapi = custom_openapi  # type: ignore[method-assign]

if os.environ.get("DEMO_DEBUG"):
    print("demo vulns:", sorted(vulns()))
