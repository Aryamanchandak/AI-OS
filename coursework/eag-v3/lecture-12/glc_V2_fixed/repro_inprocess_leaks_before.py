"""Phase 2 in-process leak repros — run against the MONOLITH (before).

Everything shares one process, so ordinary Python reaches every internal.
Run with GLC_CONFIG_DIR pointed at a throwaway dir.
"""
import os, sys

results = {}

# Leak 5 — policy engine monkey-patch
try:
    import glc.policy.engine as eng
    from glc.policy.schemas import PolicyVerdict
    orig = eng.evaluate
    eng.evaluate = lambda *a, **k: PolicyVerdict(action="allow", reason="pirate")
    v = eng.evaluate({"tool": "x"}, {})
    results["leak5_policy_monkeypatch"] = f"OK patched -> verdict.action={v.action!r} reason={v.reason!r}"
    eng.evaluate = orig
except Exception as e:
    results["leak5_policy_monkeypatch"] = f"FAILED: {type(e).__name__}: {e}"

# Leak 3 — pairing escalation via force_pair_owner
try:
    from glc.security.pairing import get_pairing_store
    store = get_pairing_store()
    has = hasattr(store, "force_pair_owner")
    results["leak3_force_pair_owner"] = f"OK importable, force_pair_owner present={has}"
except Exception as e:
    results["leak3_force_pair_owner"] = f"FAILED: {type(e).__name__}: {e}"

# Leak 10 — cost ledger poisoning via db.log_call
try:
    import glc.db as db
    db.init()
    db.log_call(provider="gemini", model="x", input_tokens=999_999_999, agent="victim", status="ok")
    rows = db.recent(limit=1)
    it = rows[0]["input_tokens"] if rows else None
    results["leak10_log_call_poison"] = f"OK inserted unvalidated row input_tokens={it}"
except Exception as e:
    results["leak10_log_call_poison"] = f"FAILED: {type(e).__name__}: {e}"

# Leak 1 — provider key readable in-process (only meaningful when a key is set)
key = os.environ.get("GEMINI_API_KEY")
results["leak1_env_key_read"] = f"os.environ.get('GEMINI_API_KEY') -> {'<present>' if key else None}"

for k, v in results.items():
    print(f"{k}: {v}")
