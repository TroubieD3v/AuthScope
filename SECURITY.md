# Security policy

## Reporting a vulnerability in AuthScope

Please do not open a public issue for security problems in AuthScope itself (for example a way to make the
engine contact a host outside `allowed_hosts`, a secret leaking into reports or storage, or a way to reach the
local web service from another origin). Use GitHub's private vulnerability reporting on
<https://github.com/TroubieD3v/APIAuthorizationTester/security/advisories/new> instead.

Include the version, a minimal config and steps to reproduce. You will get an answer within a week.

## Using AuthScope responsibly

AuthScope is meant for APIs you own or are explicitly authorized to test. Keep the default safety limits unless you
have a reason to change them, run state-changing tests only against disposable test data, and never expose the
web service to a network without your own access control.

The bundled `demo_api` is intentionally vulnerable. Do not deploy it.
