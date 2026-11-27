"""Require zero account-wide Colab assignments before/after an exclusive LLM CI."""
import sys
import time
from colab_cli.auth import AuthProvider
from colab_cli.common import state

def clear_assignments(phase):
    state.auth_provider=AuthProvider.ADC
    client=state.client
    rows=client.list_assignments()
    print(f"COLAB_{phase}_ACTIVE_BEFORE={len(rows)}",flush=True)
    # Only terminate assignments observed at the start of this cleanup.
    for row in rows:
        try:
            client.unassign(row.endpoint)
        except Exception:
            # A concurrent server-side expiry is harmless if the endpoint is gone.
            if any(a.endpoint==row.endpoint for a in client.list_assignments()):
                raise
    for _ in range(13):
        remaining=client.list_assignments()
        if not remaining:
            print(f"COLAB_{phase}_ACTIVE_AFTER=0",flush=True)
            print(f"COLAB_{phase}_CLEANUP: PASS",flush=True)
            return
        time.sleep(5)
    raise RuntimeError("ACTIVE_ASSIGNMENTS_REMAIN")

if __name__=="__main__":
    phase=sys.argv[1]
    if phase not in ("PRE","POST"):
        raise SystemExit(2)
    try:
        clear_assignments(phase)
    except Exception as exc:
        print(f"COLAB_{phase}_CLEANUP: FAIL ({type(exc).__name__})",flush=True)
        raise SystemExit(1) from None
