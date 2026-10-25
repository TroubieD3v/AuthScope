"""Project configuration model: target, identities, resources, endpoints, policy overrides.

Secrets (tokens) are never part of this model. An identity only names the environment
variable (``token_env``) or runtime secret slot that holds its credential.
"""
from __future__ import annotations

import ipaddress
import re
from typing import Any, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, Field, field_validator, model_validator

Access = Literal["public", "authenticated", "owner", "tenant", "roles"]
Expected = Literal["allow", "deny"]
MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}

MODULE_NAMES = ("unauth", "bola", "bfla", "bopla", "tenant", "custom")


class ResetConfig(BaseModel):
    """Endpoint on the target that restores the test data set after mutating tests."""

    method: str = "POST"
    path: str
    identity: str | None = None


class TargetConfig(BaseModel):
    base_url: str
    allowed_hosts: list[str] = Field(default_factory=list)
    rate_limit_rps: float = Field(default=5.0, gt=0, le=100)
    max_requests: int = Field(default=500, gt=0, le=100_000)
    timeout_s: float = Field(default=10.0, gt=0, le=120)
    concurrency: int = Field(default=1, ge=1, le=8)
    max_redirects: int = Field(default=0, ge=0, le=5)
    max_retries: int = Field(default=3, ge=0, le=10)  # 429s for any request; transport errors only for reads
    retry_after_cap_s: float = Field(default=30.0, gt=0, le=300)  # longer Retry-After values are not waited for
    allow_mutating: bool = False
    acknowledge_no_reset: bool = False
    reset: ResetConfig | None = None
    verify_tls: bool = True

    @field_validator("base_url")
    @classmethod
    def _check_url(cls, v: str) -> str:
        parts = urlsplit(v)
        if parts.scheme not in ("http", "https") or not parts.hostname:
            raise ValueError("base_url must be an http(s) URL with a host")
        if parts.username or parts.password:
            raise ValueError("credentials in base_url are not allowed")
        return v.rstrip("/")

    @model_validator(mode="after")
    def _check_hosts(self) -> "TargetConfig":
        host = urlsplit(self.base_url).hostname or ""
        hosts = [h.strip().lower() for h in self.allowed_hosts if h.strip()]
        if not hosts:
            # Only loopback targets get an implicit allow-list; everything else must be explicit.
            if _is_loopback(host):
                hosts = [host.lower()]
            else:
                raise ValueError(
                    "allowed_hosts is required for non-loopback targets: list every host the "
                    "engine may contact"
                )
        if "*" in hosts or any("*" in h for h in hosts):
            raise ValueError("wildcards are not allowed in allowed_hosts")
        if host.lower() not in hosts:
            raise ValueError(f"base_url host '{host}' must be listed in allowed_hosts")
        self.allowed_hosts = hosts
        if self.allow_mutating and not (self.reset or self.acknowledge_no_reset):
            raise ValueError(
                "allow_mutating requires a 'reset' endpoint, or acknowledge_no_reset: true"
            )
        return self


def _is_loopback(host: str) -> bool:
    if host == "localhost" or host.endswith(".localhost"):
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


class AuthConfig(BaseModel):
    """How the identity's secret is attached to requests.

    bearer: ``Authorization: Bearer <secret>``; header: ``<header_name>: <secret>``;
    cookie: ``<cookie_name>=<secret>``; query: ``?<query_name>=<secret>``;
    basic: HTTP Basic with ``username`` + secret as password (or a ``user:password`` secret).
    """

    type: Literal["bearer", "header", "cookie", "query", "basic", "none"] = "bearer"
    header_name: str = "X-API-Key"  # type == header
    cookie_name: str = "session"  # type == cookie
    query_name: str = "api_key"  # type == query
    username: str | None = None  # type == basic


class LoginConfig(BaseModel):
    """Obtain the identity's token by calling a login endpoint at the start of a run.

    ``body`` may contain ``${password}`` (the identity's password: runtime secret or
    AUTHSCOPE_PASSWORD_<NAME>) and ``${ENV_VAR}`` placeholders. Nothing secret is stored here.
    """

    method: str = "POST"
    path: str
    body: dict[str, Any] = Field(default_factory=dict)
    token_path: str = "access_token"  # dotted path in the JSON response

    @field_validator("path")
    @classmethod
    def _p(cls, v: str) -> str:
        if not v.startswith("/") or v.startswith("//") or "://" in v or "\\" in v:
            raise ValueError("login path must start with a single '/'")
        return v


class Identity(BaseModel):
    name: str
    role: str = "user"
    tenant: str | None = None
    description: str | None = None
    auth: AuthConfig = Field(default_factory=AuthConfig)
    token_env: str | None = None
    login: LoginConfig | None = None
    password_env: str | None = None  # for login flows

    @field_validator("name")
    @classmethod
    def _name(cls, v: str) -> str:
        if not re.fullmatch(r"[A-Za-z0-9_.-]{1,40}", v):
            raise ValueError("identity name: 1-40 chars of letters, digits, _ . -")
        return v

    @model_validator(mode="after")
    def _defaults(self) -> "Identity":
        if self.role == "guest" and self.token_env is None and self.auth.type == "bearer":
            self.auth = AuthConfig(type="none")
        slug = re.sub(r"[^A-Z0-9]", "_", self.name.upper())
        if self.auth.type != "none" and not self.token_env:
            self.token_env = "AUTHSCOPE_TOKEN_" + slug
        if self.login and not self.password_env:
            self.password_env = "AUTHSCOPE_PASSWORD_" + slug
        return self

    @property
    def anonymous(self) -> bool:
        return self.auth.type == "none"


class Resource(BaseModel):
    type: str
    id: str
    owner: str | None = None
    tenant: str | None = None
    id_field: str = "id"
    label: str | None = None
    parent: str | None = None  # "user:1" - fills the parent segment of nested paths
    # Composite / custom identification: JSONPath -> expected value. When set, a response "contains this
    # object" only if every rule matches (instead of looking for id_field == id).
    match: dict[str, str] = Field(default_factory=dict)

    @field_validator("id", mode="before")
    @classmethod
    def _id_str(cls, v: Any) -> str:
        return str(v)

    @field_validator("match", mode="before")
    @classmethod
    def _match(cls, v: Any) -> Any:
        from .jsonpath import parse

        if isinstance(v, dict):
            for expr in v:
                parse(expr)  # raises with a readable message on unsupported syntax
            return {k: str(val) for k, val in v.items()}
        return v

    @property
    def ref(self) -> str:
        return f"{self.type}:{self.id}"


class RestrictedField(BaseModel):
    """A response field only listed roles (and optionally the owner) may see."""

    name: str
    roles: list[str] = Field(default_factory=lambda: ["admin"])
    owner_can_see: bool = False


class Endpoint(BaseModel):
    method: str
    path: str
    summary: str | None = None
    tags: list[str] = Field(default_factory=list)
    access: Access = "authenticated"
    allow_roles: list[str] = Field(default_factory=list)
    resource_type: str | None = None
    path_param: str | None = None
    param_types: dict[str, str] = Field(default_factory=dict)  # nested paths: {"user_id": "user"}
    list_of: str | None = None
    restricted_fields: list[RestrictedField] = Field(default_factory=list)
    params: dict[str, str] = Field(default_factory=dict)
    query: dict[str, str] = Field(default_factory=dict)
    body: Any = None
    enabled: bool = True
    source: Literal["openapi", "postman", "manual"] = "manual"
    inferred: bool = False

    @field_validator("method")
    @classmethod
    def _method(cls, v: str) -> str:
        v = v.upper()
        if v not in {"GET", "HEAD", "OPTIONS", "POST", "PUT", "PATCH", "DELETE"}:
            raise ValueError(f"unsupported method {v}")
        return v

    @field_validator("path")
    @classmethod
    def _path(cls, v: str) -> str:
        if not v.startswith("/") or v.startswith("//") or "://" in v or "\\" in v or " " in v:
            raise ValueError("path must start with a single '/' and must not contain a scheme")
        return v

    @property
    def key(self) -> str:
        return f"{self.method} {self.path}"

    @property
    def mutating(self) -> bool:
        return self.method in MUTATING_METHODS

    @property
    def path_params(self) -> list[str]:
        return re.findall(r"{([^}/]+)}", self.path)

    @property
    def bound_param(self) -> str | None:
        """The path parameter that carries the tested object's id."""
        if self.path_param:
            return self.path_param
        params = [p for p in self.path_params if p not in self.params]
        if len(params) == 1:
            return params[0]
        if params and self.resource_type:
            typed = [p for p in params if self.param_type(p) == self.resource_type]
            return typed[-1] if typed else params[-1]
        return None

    def param_type(self, param: str) -> str | None:
        if param in self.param_types:
            return self.param_types[param]
        base = re.sub(r"(_id|Id|_uuid|Uuid|_ID)$", "", param)
        return base.lower() if base and base != param else None


class Override(BaseModel):
    """Manual policy decision that wins over the derived rule."""

    endpoint: str  # "GET /api/orders/{order_id}"
    identity: str
    resource: str | None = None  # "order:101"; None = every resource
    expected: Expected


class CustomTest(BaseModel):
    name: str
    method: str = "GET"
    path: str
    identity: str
    expected: Expected
    baseline_identity: str | None = None
    resource: str | None = None  # "order:101" - used for id matching
    body: Any = None

    @field_validator("method")
    @classmethod
    def _m(cls, v: str) -> str:
        return v.upper()

    @field_validator("path")
    @classmethod
    def _p(cls, v: str) -> str:
        if not v.startswith("/") or v.startswith("//") or "://" in v or "\\" in v:
            raise ValueError("path must start with a single '/'")
        return v


class ProjectConfig(BaseModel):
    name: str = "Untitled"
    target: TargetConfig
    identities: list[Identity] = Field(default_factory=list)
    resources: list[Resource] = Field(default_factory=list)
    endpoints: list[Endpoint] = Field(default_factory=list)
    overrides: list[Override] = Field(default_factory=list)
    tests: list[CustomTest] = Field(default_factory=list)

    @field_validator("identities", mode="before")
    @classmethod
    def _compact_identities(cls, v: Any) -> Any:
        # allow `identities: [alice, bob]`
        if isinstance(v, list):
            return [{"name": i} if isinstance(i, str) else i for i in v]
        return v

    @model_validator(mode="after")
    def _unique(self) -> "ProjectConfig":
        names = [i.name for i in self.identities]
        if len(names) != len(set(names)):
            raise ValueError("identity names must be unique")
        keys = [e.key for e in self.endpoints]
        if len(keys) != len(set(keys)):
            raise ValueError("duplicate endpoints (same method + path)")
        return self

    # -- lookups -----------------------------------------------------------------------
    def identity(self, name: str) -> Identity | None:
        return next((i for i in self.identities if i.name == name), None)

    def resources_of(self, rtype: str) -> list[Resource]:
        return [r for r in self.resources if r.type == rtype]

    def resource(self, ref: str) -> Resource | None:
        return next((r for r in self.resources if r.ref == ref), None)

    def tenant_of(self, res: Resource) -> str | None:
        if res.tenant:
            return res.tenant
        owner = self.identity(res.owner) if res.owner else None
        return owner.tenant if owner else None

    def path_values(self, ep: Endpoint, res: Resource | None) -> dict[str, str]:
        """Values for every path parameter: fixed params, the object id, and parent objects.

        Other parameters are filled from the object's ``parent`` chain, then from an object of the
        parameter's type owned by the same identity. Unresolvable parameters are left out.
        """
        values = dict(ep.params)
        bound = ep.bound_param
        if res is not None and bound:
            values[bound] = res.id
        chain: list[Resource] = []
        cur = res
        while cur is not None and cur.parent and len(chain) < 5:
            cur = self.resource(cur.parent)
            if cur is not None:
                chain.append(cur)
        for p in ep.path_params:
            if p in values:
                continue
            ptype = ep.param_type(p)
            match = next((c for c in chain if c.type == ptype), None)
            if match is None and res is not None and ptype:
                match = next((r for r in self.resources_of(ptype) if r.owner and r.owner == res.owner), None)
            if match is not None:
                values[p] = match.id
        return values

    def endpoint(self, key: str) -> Endpoint | None:
        return next((e for e in self.endpoints if e.key == key), None)
