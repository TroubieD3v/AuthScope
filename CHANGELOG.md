# Changelog

## 1.4.0

- CI authorization gate (`scripts/ci_gate.py`) now checks both sides: zero findings on the secure demo, exactly the
  expected findings (`examples/expected-findings.json`) on the vulnerable one, evidence that targets the reported
  object with the owner's baseline, and no demo credential in JSON, Markdown, HTML or pytest reports.
- False-positive corpus (`tests/corpus/cases.yaml`, 40+ annotated responses) and Hypothesis property tests for
  comparison and masking (#5). Fixes found on the way: empty pagination wrappers count as empty, an HTML login form
  served with 200 is a soft denial, the same object in a different wrapper still corroborates the owner's response,
  any other 4xx is "rejected" instead of being read as data, and secrets are masked in JSON keys and header names.
- Resilience (#6): `429` is retried after `Retry-After` (capped, within the request budget), transport errors are
  retried with back-off for read-only requests only, and a run stops after 8 consecutive unreachable responses
  (CLI exit code 3). Retries and back-off time are shown in run statistics and reports. `DEMO_RATE_LIMIT` in the demo
  API exercises it.
- Composite identifiers: resources can carry JSONPath match rules (`.key`, `['key']`, `[n]`, `[*]`, `..key`); all rules
  must match for a confirmed finding, look-alikes stay in "needs review". Editable in the Identity Manager.

## 1.3.0

- Redesigned web interface in an editorial, bento-grid style: large headlines with status pills, a two-ring dial on
  the dashboard, stat tiles, module toggle cards in the Test Runner, identity cards, square controls and pill
  switches.
- Dark theme by default, with a light theme switch in the top bar (remembered per browser, no flash on load).
- New palette: primary `#121212`, secondary `#008542`, tertiary `#D97706`, neutral `#64748B`; Manrope for headlines,
  Inter for body text, JetBrains Mono for code. Fonts are bundled with the UI, no CDN requests.
- Responsive layout: side rail on desktop, bottom navigation on mobile.
- HTML report restyled with the same palette, dark by default with a light/dark switch.
- Screenshots and demo GIF regenerated, including light-theme views.

## 1.2.0

- Comparison: an object-level violation now requires the requested object's id in the response, corroborated by
  at least a quarter of the owner's other fields. Look-alike data without the id, or an id surrounded by unrelated
  data, is reported as "needs review" instead of a violation. New false-positive tests.
- DNS pinning: each request resolves the host once, validates the address and connects to exactly that IP, keeping
  the Host header and TLS server name. Redirect hops and OpenAPI URL fetches are pinned the same way. Cookies are sent
  as an explicit header.
- Repository renamed to `TroubieD3v/AuthScope`; links, clone command and package metadata updated.
- Docker Compose project name fixed to `authscope`.

## 1.1.0

- Authentication: API key in a query parameter (`auth.type: query`) and HTTP Basic (`auth.type: basic`,
  with `username` + password secret, or a `user:password` secret). Reproduction commands and pytest exports use
  environment-variable placeholders for both.
- Nested object paths such as `/users/{user_id}/orders/{order_id}`: the object id goes into the last typed parameter,
  parents are filled from the resource's `parent` chain or from an object of the same owner. Importers infer
  `param_types`.
- Demo API: nested order route, Basic and `?api_key=` authentication.
- README with screenshots and demo GIF (regenerate with `scripts/screenshots.py`), Russian README,
  architecture and threat-model docs, issue and pull request templates, `authscope --version`.

## 1.0.0

First public release.

- Test modules: BOLA / IDOR (direct objects and list leaks), BFLA, BOPLA (with entitled-role controls),
  Unauthenticated Access, Cross-Tenant Access, custom YAML tests.
- Response comparison against an owner baseline: object id match, field overlap, empty and error-envelope
  responses, inconclusive classification for 4xx/5xx/redirects and failed baselines.
- Evidence with masked secrets, response differences, expected policy and `curl` reproduction.
- Reports: HTML, Markdown, JSON, pytest regression tests; run-to-run comparison (new / fixed / unchanged).
- Import: OpenAPI 3 / Swagger 2 (JSON, YAML) and Postman collections v2.0 / v2.1, with inferred access rules.
- Credentials: write-only UI input, environment variables, login flow.
- Safety: host allow-list, address and redirect checks, rate limit, request budget, read-only by default,
  reset hook for state-changing tests, localhost-only service with Host header validation.
- Web UI: Dashboard, API Explorer, Identity Manager, Permission Matrix, Test Runner, Findings & Reports.
- CLI with CI-friendly exit codes; Docker Compose setup; intentionally vulnerable demo API with a secure mode.
