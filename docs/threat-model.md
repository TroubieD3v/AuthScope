# Threat model

AuthScope sends authenticated requests on behalf of test identities. The main risks are therefore *using it
against the wrong system*, *leaking the credentials it holds*, and *someone else driving it*.

| Threat | Mitigation |
|---|---|
| Requests reach a host outside the agreed scope (typo, malicious spec, redirect, DNS tricks) | Explicit `allowed_hosts` (required for non-loopback targets, no wildcards); host, port, scheme and path validated per request; resolved IP checked; link-local / metadata / multicast addresses always blocked; redirects not followed by default and re-validated when enabled; spec URLs fetched through the same guard |
| Accidental damage to real data | Read-only by default, enforced inside the HTTP engine; state-changing tests need an explicit switch plus a reset endpoint (or an explicit acknowledgement); a failed reset stops further writes |
| Overloading the target | 5 requests/s default, per-run request budget, sequential write tests, cancel button |
| Credentials leak through config, database, reports or screenshots | Secrets are never part of the config model; UI input is write-only and kept in memory; env vars as the alternative; evidence masked (known secret values, JWTs, bearer/basic values, sensitive keys, card numbers, e-mails); reproduction commands use `$ENV` placeholders |
| Another website or local user drives the AuthScope API (CSRF, DNS rebinding) | Binds to 127.0.0.1; `Host` header allow-list; CORS limited to the dev UI origin; `serve` refuses a public bind without an explicit flag; Docker ports published on 127.0.0.1 only |
| False confidence from a clean report | Every case is recorded with its verdict; inconclusive and skipped cases are listed with reasons; BOPLA uses entitled roles as controls; failed baselines mark comparisons inconclusive |

## Out of scope

- DNS is checked right before each request but not pinned; a hostile resolver for an allow-listed name could still
  rebind between check and connect. Allow-list only hosts you control.
- AuthScope trusts the machine it runs on. Anyone with local access to the process or its memory can read runtime
  secrets.
- The demo API is vulnerable by design and must never be exposed.
