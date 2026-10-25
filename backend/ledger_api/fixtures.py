"""Throwaway credentials for the ledger test stand. Not real secrets."""
import os

API_KEYS = {
    "nina": os.environ.get("LEDGER_KEY_NINA", "ledger-nina-4c1e88a0"),
    "omar": os.environ.get("LEDGER_KEY_OMAR", "ledger-omar-9b7d2f11"),
    "pia": os.environ.get("LEDGER_KEY_PIA", "ledger-pia-21aa6c5e"),
    "root": os.environ.get("LEDGER_KEY_ROOT", "ledger-root-e03f7b42"),
}

ALL_FLAWS = ("bola", "bfla", "bopla", "tenant")


def active_flaws() -> set[str]:
    """LEDGER_FLAWS: comma list of ALL_FLAWS; empty string = correct behaviour. Unset = all flaws on."""
    raw = os.environ.get("LEDGER_FLAWS")
    if raw is None:
        return set(ALL_FLAWS)
    return {v.strip() for v in raw.split(",") if v.strip()}
