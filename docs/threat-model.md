# Threat model

AuthScope sends authenticated requests on behalf of test identities. The main risks are therefore *using it
against the wrong system*, *leaking the credentials it holds*, and *someone else driving it*.

| Threat | Mitigation |
|---|---|
| Requests reach a host outside the agreed scope (typo, malicious spec, redirect, DNS tricks) | Explicit `allowed_hosts` (required for non-loopback targets, no wildcards); host, port, scheme and path validated per request; each request resolves the host once, validates the address and connects to exactly that IP (DNS pinning, Host header and TLS name preserved); link-local / metadata / multicast addresses always blocked; redirects not followed by default and re-validated when enabled; spec URLs fetched through the same guard |
| Accidental damage to real data | Read-only by default, enforced inside the HTTP engine; state-changing tests need an explicit switch plus a reset endpoint (or an explicit acknowledgement); a failed reset stops further writes |
| Overloading the target | 5 requests/s default, per-run request budget, sequential write tests, cancel button; `429` honoured via `Retry-After`, retries only within the budget, no retries of writes, run stops after repeated transport errors |
| Credentials leak through config, database, reports or screenshots | Secrets are never part of the config model; UI input is write-only and kept in memory; env vars as the alternative; evidence masked (known secret values, JWTs, bearer/basic values, sensitive keys, card numbers, e-mails); reproduction commands use `$ENV` placeholders |
| Another website or local user drives the AuthScope API (CSRF, DNS rebinding) | Binds to 127.0.0.1; `Host` header allow-list; CORS limited to the dev UI origin; `serve` refuses a public bind without an explicit flag; Docker ports published on 127.0.0.1 only |
| False positives from look-alike data | A violation needs the requested object's id in the response, corroborated by the owner's other fields; similar data without the id goes to "needs review" |
| A scanner regression that silently stops finding issues | CI gate against a vulnerable demo with an exact expected-findings list, plus a false-positive corpus and property-based tests |
| False confidence from a clean report | Every case is recorded with its verdict; inconclusive and skipped cases are listed with reasons; BOPLA uses entitled roles as controls; failed baselines mark comparisons inconclusive |

## Out of scope

- DNS answers are pinned per request, but an allow-listed name can legitimately resolve to different addresses over
  a run; every answer is validated, yet AuthScope cannot tell a hostile resolver from a load balancer. Allow-list
  only hosts you control.
- HTTP proxies are not supported (`trust_env` is off), so pinning cannot be bypassed through proxy settings.
- AuthScope trusts the machine it runs on. Anyone with local access to the process or its memory can read runtime
  secrets.
- The demo API is vulnerable by design and must never be exposed.
