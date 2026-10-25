"""Second, independent test stand for AuthScope: a small document and invoice ledger.

It deliberately uses other conventions than demo_api, so the engine is not tuned to one API:
API keys in a header, UUIDs, ``{"data": ...}`` envelopes, refusals sent as HTTP 200 with an ``errors``
array, paginated lists, and invoices identified by (workspace, number) where numbers repeat across
workspaces. Flaws are switched with LEDGER_FLAWS (bola, bfla, bopla, tenant; empty = correct). Never deploy.
"""
from __future__ import annotations

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse

from .fixtures import API_KEYS, active_flaws

USERS = {
    "nina": {"uuid": "u-nina", "name": "nina", "role": "member", "workspace": "ws-north"},
    "omar": {"uuid": "u-omar", "name": "omar", "role": "member", "workspace": "ws-north"},
    "pia": {"uuid": "u-pia", "name": "pia", "role": "member", "workspace": "ws-south"},
    "root": {"uuid": "u-root", "name": "root", "role": "admin", "workspace": None},
}
DOCS = {
    "7f0c2a9e-0d6b-4a57-9a1e-1b2c3d4e5f01": {"title": "Q3 forecast", "body": "Revenue plan for Q3",
                                             "owner": "nina", "workspace": "ws-north", "costCenter": "CC-104"},
    "7f0c2a9e-0d6b-4a57-9a1e-1b2c3d4e5f02": {"title": "Vendor list", "body": "Approved suppliers",
                                             "owner": "omar", "workspace": "ws-north", "costCenter": "CC-221"},
    "7f0c2a9e-0d6b-4a57-9a1e-1b2c3d4e5f03": {"title": "Hiring plan", "body": "Two engineers in Q4",
                                             "owner": "pia", "workspace": "ws-south", "costCenter": "CC-310"},
}
# invoice numbers repeat across workspaces on purpose
INVOICES = {
    ("ws-north", 1001): {"amount": 1200.0, "customer": "Contoso", "owner": "nina"},
    ("ws-north", 1002): {"amount": 450.5, "customer": "Fabrikam", "owner": "omar"},
    ("ws-south", 1001): {"amount": 980.0, "customer": "Northwind", "owner": "pia"},
}

app = FastAPI(title="AuthScope Ledger test stand", version="1.0.0",
              description="Independent, intentionally flawed API for testing AuthScope. Never deploy.")
KEY_HEADER = {"security": [{"apiKey": []}]}


def flaws() -> set[str]:
    return active_flaws()


def refused(code: str = "FORBIDDEN") -> JSONResponse:
    """This API reports refusals as HTTP 200 with an errors array (a common GraphQL-style convention)."""
    return JSONResponse({"data": None, "errors": [{"code": code, "message": "not authorized"}]})


def caller(x_api_key: str | None = Header(default=None)):
    for name, key in API_KEYS.items():
        if x_api_key == key:
            return USERS[name]
    raise HTTPException(401, {"errors": [{"code": "UNAUTHENTICATED"}]})


def doc_view(uuid: str, doc: dict, viewer: dict) -> dict:
    out = {"uuid": uuid, "title": doc["title"], "body": doc["body"], "ownerUuid": USERS[doc["owner"]]["uuid"],
           "workspace": doc["workspace"]}
    if viewer["role"] == "admin" or "bopla" in flaws():
        out["costCenter"] = doc["costCenter"]
    return out


def can_read_doc(doc: dict, user: dict) -> bool:
    if user["role"] == "admin" or doc["owner"] == user["name"]:
        return True
    return "bola" in flaws() and doc["workspace"] == user["workspace"]


@app.get("/v2/health", tags=["system"], openapi_extra={"security": []})
def health():
    return {"data": {"status": "ok", "flaws": sorted(flaws())}}


@app.get("/v2/me", tags=["users"], openapi_extra=KEY_HEADER)
def me(user=Depends(caller)):
    return {"data": {"user": user}}


@app.get("/v2/documents", tags=["documents"], openapi_extra=KEY_HEADER)
def list_documents(page: int = 1, user=Depends(caller)):
    items = [doc_view(u, d, user) for u, d in DOCS.items() if can_read_doc(d, user)]
    return {"items": items[(page - 1) * 20: page * 20], "total": len(items), "page": page}


@app.get("/v2/documents/{doc_uuid}", tags=["documents"], openapi_extra=KEY_HEADER)
def get_document(doc_uuid: str, user=Depends(caller)):
    doc = DOCS.get(doc_uuid)
    if doc is None:
        raise HTTPException(404, {"errors": [{"code": "NOT_FOUND"}]})
    if not can_read_doc(doc, user):
        return refused()
    return {"data": {"document": doc_view(doc_uuid, doc, user)}}


@app.get("/v2/workspaces/{workspace}/invoices/{number}", tags=["invoices"], openapi_extra=KEY_HEADER)
def get_invoice(workspace: str, number: int, user=Depends(caller)):
    inv = INVOICES.get((workspace, number))
    if inv is None:
        raise HTTPException(404, {"errors": [{"code": "NOT_FOUND"}]})
    if user["role"] != "admin" and workspace != user["workspace"] and "tenant" not in flaws():
        raise HTTPException(404, {"errors": [{"code": "NOT_FOUND"}]})
    return {"data": {"workspace": workspace, "number": number, "amount": inv["amount"], "customer": inv["customer"]}}


@app.get("/v2/admin/audit-log", tags=["admin"], openapi_extra=KEY_HEADER)
def audit_log(user=Depends(caller)):
    if user["role"] != "admin" and "bfla" not in flaws():
        return refused("ADMIN_ONLY")
    return {"data": {"events": [{"at": "2026-10-01T09:00:00Z", "actor": "root", "action": "rotate-keys"}]}}
