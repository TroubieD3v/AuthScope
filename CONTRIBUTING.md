# Contributing

```bash
pip install -e ".[dev]"
cd frontend && npm install && npm run build && cd ..
pytest && pytest -m e2e
```

## Adding a test module

A module lives in `backend/authscope/modules/` and implements two methods:

- `plan(cfg) -> list[Case]` - one `Case` per (endpoint, identity, resource, variant) with the **expected** decision
  (use `policy.decide`). Set `skip_reason` instead of silently dropping cases, so reports show what was not tested.
- `evaluate(case, test, baseline) -> Judgement` - turn the response into a verdict. `modules.base.judge_access`
  covers the common allow/deny table; build on `compare.classify` rather than reading status codes directly.

Register it in `modules/__init__.py`. Every module needs:

1. a planted flaw in `backend/demo_api` that can be switched off through `DEMO_VULNS`;
2. an integration test proving the flaw is found **and** that the secure demo produces no findings.

All requests must go through `Requester.send`, which enforces the allow-list, address checks, rate limit, budget
and read-only mode. Do not add HTTP clients elsewhere.
