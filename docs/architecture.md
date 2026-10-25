# Architecture

```
Browser ──► AuthScope (FastAPI, 127.0.0.1:8080) ──► Requester ──► target API (allowed hosts only)
             │  serves the built React UI            │ guard: allow-list, DNS pinning, redirect checks,
             │  /api/* control plane                 │ rate limit, request budget, read-only mode
             └─► SQLite (projects, runs, results)    └─► masked evidence only
```

## Request flow of a run

1. `TestRunner` loads the project config (no secrets inside) and resolves credentials: runtime secret store
   (UI, memory only) → `AUTHSCOPE_TOKEN_<NAME>` → login flow.
2. Each selected module's `plan(cfg)` turns endpoints × identities × resources into `Case`s. Every case carries the
   **expected** decision from `policy.decide` and a reason; cases that cannot run get a `skip_reason`.
3. Baselines (the owner's own request) are sent once per endpoint/object and cached.
4. Read-only cases run concurrently under the rate limiter; state-changing cases run one by one, each followed by
   the target's reset hook.
5. `compare.classify` decides what a response *means* (denied, empty, error envelope, same object, ambiguous...);
   the module's `evaluate` turns that and the expectation into a verdict.
6. Evidence is masked (`masking.Masker`) before it is stored or shown; raw responses never leave memory.

## Backend modules (`backend/authscope/`)

| File | Responsibility |
|---|---|
| `config.py` | Pydantic models: target, identities, resources, endpoints, overrides, custom tests |
| `policy.py` | Expected allow/deny for (endpoint, identity, resource) |
| `safety.py` | `TargetGuard`, rate limiter, request budget |
| `http_engine.py` | `Requester` (httpx, async), secret store, credential placement |
| `compare.py` | Response classification and differences |
| `modules/` | BOLA, BFLA, BOPLA, Unauthenticated, Cross-Tenant, custom |
| `runner.py` | Orchestration, login flows, baselines, reset, evidence |
| `openapi_import.py`, `postman_import.py` | Endpoint import with inferred rules |
| `reports.py`, `templates/` | JSON, Markdown, HTML, pytest |
| `storage.py` | SQLite persistence |
| `api.py`, `cli.py` | Web API and command line |

## Frontend (`frontend/`)

React + TypeScript + Vite + Tailwind CSS. `src/components/ui` holds shadcn-style primitives; `src/screens` holds the
six screens. In production the built files are served by the backend; in development Vite proxies `/api`.

## Demo API (`backend/demo_api/`)

A separate FastAPI app with one planted flaw per module, switchable through `DEMO_VULNS`. It exists so that every
detection is backed by a test that proves both the finding and the absence of false positives on the secure variant.
