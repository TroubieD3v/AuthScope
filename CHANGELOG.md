# Changelog

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
