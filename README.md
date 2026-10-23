# AuthScope

**API authorization testing platform** - finds BOLA/IDOR, BFLA, BOPLA, unauthenticated access and
cross-tenant leaks in REST APIs by comparing what the API *actually does* with the access policy you
describe.

AuthScope does not look for "HTTP 200". It answers: *"Bob got access to Alice's order 101, contrary to the
configured policy - here is reproducible evidence."*

> For **authorized** testing only: your own APIs, staging environments, pentests with a written scope.
> The engine contacts nothing but the hosts you list (see [Safety model](#safety-model)).

## Quick start

```bash
git clone https://github.com/TroubieD3v/APIAuthorizationTester.git && cd APIAuthorizationTester
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
cd frontend && npm install && npm run build && cd ..   # builds the web UI once

python -m demo_api &                  # intentionally vulnerable demo API on :8000
authscope serve                       # UI + API on http://localhost:8080
```

Open <http://localhost:8080>, click **Load demo project**, go to **Test Runner -> Start run**, then open
**Permission Matrix** and **Findings & Reports**.

### Docker

```bash
docker compose up --build             # UI on http://localhost:8080, demo API on :8000
AUTHSCOPE_PORT=8090 DEMO_PORT=8001 docker compose up --build   # if those ports are taken
```

Both ports are published on 127.0.0.1 only. In the UI, the demo address is pre-filled with `http://demo-api:8000`.

### CLI / CI

```bash
set -a; . examples/demo.env; set +a
authscope run -c examples/demo.authscope.yaml -f md -o report.md        # exit code 1 if violations
authscope run -c examples/demo.authscope.yaml -f pytest -o test_authz_regression.py
authscope run -c my.yaml -m bola -m bfla --allow-mutating               # selected modules, writes enabled
```

`.github/workflows/ci.yml` contains an `authz-gate` job showing AuthScope as an authorization regression
gate in CI.

## How it works

1. **Target** - base URL and an explicit list of allowed hosts.
2. **Endpoints** - import **OpenAPI/Swagger** (JSON/YAML) or a **Postman collection** (v2.0/v2.1), or add them by
   hand. Specs say *how* to authenticate, not *who owns what*, so access rules are only **inferred** (and marked so)
   until you confirm them.
3. **Identities** - test accounts with a role and (optionally) a tenant. Credentials come from:
   - a token typed in the UI (write-only, kept in server memory only),
   - `AUTHSCOPE_TOKEN_<NAME>` environment variables,
   - a **login flow**: AuthScope calls your login endpoint at the start of each run with
     `AUTHSCOPE_PASSWORD_<NAME>` (or a password typed in the UI) and takes the token from the JSON response.

   Secrets are never written to YAML, SQLite or reports.
4. **Resources** - which test objects belong to which identity (`order 101 -> alice`).
5. **Policy** - per endpoint: `public`, `authenticated`, `owner`, `tenant` or `roles`, plus `allow_roles`, BOPLA
   `restricted_fields`, and manual cell overrides in the Permission Matrix.
6. **Run** and read the matrix and the evidence.

### Smart comparison

```
Baseline  - alice -> GET /api/orders/101   200 OK, her own order
Test      - bob   -> GET /api/orders/101   ?
```

| Observed for the other identity                         | Verdict |
|---------------------------------------------------------|---------|
| 401 / 403 / 404, redirect to a login page               | pass |
| **200 with an empty body / `[]` / `{}`**                | pass - filtering, *not* BOLA |
| 200 whose body is an error envelope (`{"error": ...}`)  | pass - soft denial |
| 200 with the same object (id match, field overlap >= 50% with the baseline) | **violation** |
| 200 with data that does not match the object            | needs review (endpoint may ignore the id) |
| 400/405/422/5xx, unfollowed redirect                    | inconclusive - authorization was not evaluated |
| baseline itself failed (owner got 404)                  | inconclusive - fix the test data |

Every result is recorded - passes and skips too - so a report shows what was verified, not only what broke.

### Modules

| Module | Checks |
|---|---|
| **BOLA / IDOR** | owner baseline vs. other same-tenant identities; list endpoints must not leak foreign objects |
| **BFLA** | every role calls every role-restricted function |
| **BOPLA** | restricted JSON properties (`internalNotes`) must not appear for roles that may not see them; entitled roles act as controls, so a wrong field name is detected instead of giving a false "pass" |
| **Unauthenticated** | no credentials and an invalid token on every non-public endpoint; public endpoints as controls |
| **Cross-Tenant** | identities of tenant A request objects and lists of tenant B |
| **Custom tests** | explicit `tests:` from the YAML |
| **Authorization regression** | compare any two runs: new / fixed / unchanged findings (UI "Compare", `GET /api/runs/{id}/diff`), pytest export of findings |

Planned: Mass Assignment and Session Authorization modules, Burp Suite extension.

### UI screens

**Dashboard** - **API Explorer** (target, import, endpoint rules) - **Identity Manager** (identities, tokens,
login flows, object ownership) - **Permission Matrix** (expected vs. real, click to override) - **Test Runner**
(modules, limits, progress, cancel) - **Findings & Reports** (evidence, run comparison, HTML / Markdown / JSON /
pytest export).

### Evidence

Each finding contains the baseline and test request/response pair, the response differences, the expected policy,
and a `curl` reproduction that reads the token from an environment variable. Tokens (known values, JWTs, `Bearer ...`),
passwords, sensitive JSON keys (`password`, `secret`, `token`, `ssn`, ...), card numbers (Luhn) and e-mail addresses
are masked; bodies are truncated. The pytest export asserts the *expected* policy, so each test fails until the issue
is fixed and then guards against regressions.

## Config file

```yaml
target:
  base_url: http://127.0.0.1:8000
  allowed_hosts: [127.0.0.1]
identities: [alice, bob, admin]            # or full objects: {name, role, tenant, auth, login}
resources:
  - { type: order, id: 101, owner: alice }
  - { type: order, id: 102, owner: bob }
endpoints:
  - { method: GET, path: "/api/orders/{order_id}", access: owner, allow_roles: [admin], resource_type: order }
tests:
  - { name: Cross-user order access, path: /api/orders/101, identity: bob, expected: deny, baseline_identity: alice }
```

Full annotated example: [`examples/demo.authscope.yaml`](examples/demo.authscope.yaml). With the CLI, add
`openapi: ./spec.yaml` or `postman: ./collection.json` to merge endpoints from a file
(see [`examples/demo.postman_collection.json`](examples/demo.postman_collection.json)).

## Safety model

- **Explicit allow-list**: `allowed_hosts` is required for non-loopback targets, no wildcards. Hosts, ports, schemes
  and `user:pass@` URLs are validated for every request; paths that could change the host are refused.
- **Address checks**: the resolved IP is checked before each request; link-local / cloud-metadata
  (169.254.0.0/16, fe80::/10), multicast and unspecified addresses are always blocked.
- **Redirects** are not followed by default. With `max_redirects > 0` every hop is re-validated.
- **Rate limit and budget**: 5 rps default and a per-run request budget (500); when it runs out the run stops and
  the rest is marked skipped.
- **Read-only by default**: PUT/POST/PATCH/DELETE are blocked in the HTTP engine itself unless `allow_mutating` is
  on, which additionally requires a `reset` endpoint (called after every state-changing request; a failed reset stops
  further writes) or an explicit `acknowledge_no_reset`. Use disposable test data. The only exception is the
  identity's own login request.
- **Secrets** never touch YAML, the database or reports.
- **The web service itself** can send requests to your targets, so it binds to `127.0.0.1`, rejects foreign `Host`
  headers (DNS rebinding) and `authscope serve` refuses a public bind without `--i-know-this-is-exposed`.
  Spec URLs are fetched through the same allow-list.

Known limits: DNS is checked right before a request, not pinned (only allow-list hosts you control);
state-changing tests are judged by status code; the login flow supports JSON login endpoints that return the token
in the response body.

See [SECURITY.md](SECURITY.md) for reporting vulnerabilities in AuthScope itself.

## Demo API

`python -m demo_api` starts an intentionally vulnerable API with one flaw per module. `DEMO_VULNS` selects flaws
(`bola,bfla,bopla,unauth,tenant`; set it empty for a fully secure variant). The test suite runs AuthScope against
both variants: every planted flaw must be found, and the secure variant must produce **zero** findings.
**Never deploy it.**

## Development

```bash
pytest                         # unit + end-to-end tests against the demo API (vulnerable and secure)
playwright install chromium && pytest -m e2e    # browser test of the UI workflow (needs the built UI)
cd frontend && npm run dev     # UI on :5173, proxies /api to :8080
```

Layout:

```
backend/authscope/   config, safety, http_engine, compare, policy, modules/, runner,
                     openapi_import, postman_import, reports, storage, api, cli
backend/demo_api/    intentionally vulnerable demo API
frontend/            React + TypeScript + Tailwind, shadcn-style components in src/components/ui
tests/               unit, integration, CLI, e2e (Playwright)
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for adding a module.

## License

[MIT](LICENSE) - TroubieD3v
