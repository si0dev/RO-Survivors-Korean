"""Do not terminate unrelated Colab sessions."""
import sys,time
from colab_cli.auth import AuthProvider
from colab_cli.common import state
state.auth_provider=AuthProvider.ADC
phase=sys.argv[1]
if phase not in ("PRE","POST"): raise SystemExit(2)
try:
    for attempt in range(1 if phase=="PRE" else 13):
        count=len(state.client.list_assignments())
        if count==0:
            print(f"COLAB_{phase}_ACTIVE_AFTER=0",flush=True)
            break
        if phase=="PRE": raise RuntimeError("ACTIVE_SESSION_PRESENT")
        time.sleep(5)
    else: raise RuntimeError("SESSION_CLEANUP_UNCONFIRMED")
except Exception as exc:
    print(f"COLAB_{phase}_CHECK_FAILED={type(exc).__name__}",flush=True)
    raise SystemExit(1) from None
