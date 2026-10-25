# Benchmarks

How well does AuthScope find authorization flaws, and how often does it cry wolf? Each benchmark stand runs in two
modes: **correct** (no flaws) and **flawed** (every planted flaw switched on). A good result is *zero* findings in the
correct mode and *exactly* the planted flaws in the flawed mode. CI checks both on every push
(`scripts/ci_gate.py`, job `authz-gate`).

## Stands

| Stand | What it exercises |
|---|---|
| `demo_api` (port 8000) | Bearer tokens, numeric ids, login flow, nested paths (`/users/{id}/orders/{id}`), filtered lists that return `200 []` |
| `ledger_api` (port 8100) | A separately written API with other conventions: API keys in a header, UUIDs under `uuid`, `{"data": ...}` envelopes, refusals sent as **HTTP 200 with an `errors` array**, paginated lists, and invoices identified by **(workspace, number)** where numbers repeat across workspaces |

The ledger stand was added so the engine is not tuned to the conventions of a single API. Its invoices can only be
identified correctly with composite identifiers (`params` + JSONPath `match` rules): invoice `1001` exists in both
workspaces.

## Results (v1.5.0)

### Correct mode: false positives

| Stand | Checks | Passed | Violations | Needs review | Errors |
|---|---|---|---|---|---|
| demo_api | 97 executed (+38 state-changing, skipped in read-only mode) | 97 | **0** | **0** | 0 |
| ledger_api | 50 | 50 | **0** | **0** | 0 |

In the ledger stand, 9 of those passes are refusals that arrive as `200 {"data": null, "errors": [...]}`. A
status-code-only scanner would report them as access; AuthScope classifies them as soft denials.

### Flawed mode: detection

| Stand | Module | Planted flaw | Findings | Missed | Extra |
|---|---|---|---|---|---|
| demo_api | BOLA / IDOR | users and orders readable within a tenant; list leak; nested route | 11 | 0 | 0 |
| demo_api | BFLA | admin statistics open to every user | 3 | 0 | 0 |
| demo_api | BOPLA | `internalNotes`, `creditLimit` shown to users | 3 | 0 | 0 |
| demo_api | Unauthenticated | sales summary without a token | 2 | 0 | 0 |
| demo_api | Cross-tenant | users, orders, invoices and lists across tenants | 18 | 0 | 0 |
| demo_api | Custom tests | the YAML example case | 1 | 0 | 0 |
| ledger_api | BOLA / IDOR | documents readable within a workspace; list leak | 4 | 0 | 0 |
| ledger_api | BFLA | audit log open to members | 3 | 0 | 0 |
| ledger_api | BOPLA | `costCenter` shown to members | 3 | 0 | 0 |
| ledger_api | Cross-tenant | invoices of the other workspace (composite ids) | 4 | 0 | 0 |
| **Total** | | | **52** | **0** | **0** |

The exact expected lists are in [`examples/expected-findings.json`](../examples/expected-findings.json) and
[`examples/expected-findings-ledger.json`](../examples/expected-findings-ledger.json). For every object-level finding
the gate also verifies that the evidence targets the reported object, that the response contains its identifier (or
satisfies its match rules), and that the baseline was made by the owner. No credential of either stand appears in any
report format.

### Hard cases outside the stands

The comparison logic is additionally pinned by [`tests/corpus/cases.yaml`](../tests/corpus/cases.yaml) (40+ annotated
responses such as look-alike objects, ids in wrappers, empty pagination, GraphQL errors, login pages served with 200,
truncated JSON) and by property-based tests: a 200 response without the requested object's identifier is never
reported as a confirmed violation.

## Limits of these numbers

- Both stands were written together with AuthScope. They show that the engine behaves correctly on known flaws and
  different API conventions; they are not an independent measurement of real-world recall.
- State-changing flaws are only covered when mutating mode is on (it is off in this benchmark).
- Third-party benchmark APIs are tracked in [issue #4](https://github.com/TroubieD3v/AuthScope/issues/4).

## Reproduce

```bash
pip install -e .
DEMO_VULNS= DEMO_PORT=8000 python -m demo_api &
DEMO_PORT=8001 python -m demo_api &
LEDGER_FLAWS= LEDGER_PORT=8100 python -m ledger_api &
LEDGER_PORT=8101 python -m ledger_api &

python scripts/ci_gate.py --stand demo   --secure http://127.0.0.1:8000 --vulnerable http://127.0.0.1:8001 --out reports
python scripts/ci_gate.py --stand ledger --secure http://127.0.0.1:8100 --vulnerable http://127.0.0.1:8101 --out reports
```

Each run prints the verdict counts and writes JSON, Markdown, HTML and pytest reports for both modes to `reports/`.
