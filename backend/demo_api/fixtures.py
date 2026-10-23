"""Demo fixtures. These are throwaway values for the bundled demo API only - not real secrets."""
import os

TOKENS = {
    "alice": os.environ.get("DEMO_TOKEN_ALICE", "demo-alice-0f3a9c71"),
    "bob": os.environ.get("DEMO_TOKEN_BOB", "demo-bob-5be2d814"),
    "carol": os.environ.get("DEMO_TOKEN_CAROL", "demo-carol-77c1e0a9"),
    "admin": os.environ.get("DEMO_TOKEN_ADMIN", "demo-admin-b94f1d2e"),
}

# Passwords for POST /api/auth/login (the demo project logs carol in this way).
PASSWORDS = {
    "alice": "alice-demo-pass", "bob": "bob-demo-pass", "carol": "carol-demo-pass", "admin": "admin-demo-pass",
}

ALL_VULNS = ("bola", "bfla", "bopla", "unauth", "tenant")


def active_vulns() -> set[str]:
    """DEMO_VULNS: comma list of ALL_VULNS; empty string = secure. Unset = everything vulnerable."""
    raw = os.environ.get("DEMO_VULNS")
    if raw is None:
        return set(ALL_VULNS)
    return {v.strip() for v in raw.split(",") if v.strip()}
