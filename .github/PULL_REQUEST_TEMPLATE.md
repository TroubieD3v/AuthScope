## What changes

<!-- Short description and the issue it closes, e.g. "Closes #12". -->

## Checklist

- [ ] `pytest` passes (and `pytest -m e2e` if the UI changed)
- [ ] `cd frontend && npm run build` passes if the UI changed
- [ ] A new module ships a planted flaw in `demo_api` (switchable via `DEMO_VULNS`) and tests that it is found
      **and** that the secure demo stays clean
- [ ] All HTTP goes through `Requester.send` (allow-list, rate limit, read-only mode)
- [ ] No tokens, passwords or private hosts in code, tests, screenshots or reports
- [ ] README / CHANGELOG updated if behaviour changed
