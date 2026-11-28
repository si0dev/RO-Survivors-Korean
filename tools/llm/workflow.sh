#!/usr/bin/env bash
set -euo pipefail
umask 077
tmp="$RUNNER_TEMP/ro-update-llm"
export XDG_CONFIG_HOME="$tmp/config"
export RO_CACHE_TMP="$tmp"
export GOOGLE_APPLICATION_CREDENTIALS="$tmp/adc.json"
cli=(colab --auth=adc --config "$tmp/sessions.json")
gpu="ro-translate-$GITHUB_RUN_ID"
allocation_started=0
allocation_ready=0
# Never emit raw authentication or session logs into this public repository.
check() {
  local phase="$1" limit="$2"
  shift 2
  if timeout "$limit" "$@" </dev/null >"$tmp/$phase.log" 2>&1; then
    echo "$phase: PASS"
  else
    local rc=$?
    echo "$phase: FAIL (exit $rc)"
    python - "$tmp/$phase.log" <<'PY'
import re,sys
s=open(sys.argv[1],errors="replace").read()
for pattern in (r"\b401\b",r"\b403\b",r"\b429\b",r"\b503\b",r"invalid_grant",r"invalid_scope",r"accessNotConfigured",r"SERVICE_DISABLED",r"insufficientPermissions",r"rateLimitExceeded",r"userRateLimitExceeded",r"storageQuotaExceeded",r"appNotAuthorizedToFile",r"domainPolicy",r"insufficient.{0,20}scope",r"quota",r"resource exhausted",r"not available",r"authentication",r"timeout",r"no available",r"permission denied",r"allocation",r"ENGINE_ASSET_UNAVAILABLE",r"ENGINE_START_FAILED",r"ENGINE_READY_TIMEOUT",r"FULL_GPU_OFFLOAD_NOT_VERIFIED",r"TRANSLATION_TRUNCATED",r"GPU_MODEL_MEMORY_NOT_VERIFIED",r"CACHE_MANIFEST_MISMATCH",r"CACHE_DUPLICATE_NAME",r"DOWNLOAD_SIZE_MISMATCH",r"DOWNLOAD_HASH_MISMATCH",r"UPLOAD_HASH_MISMATCH",r"REMOTE_DIGEST_READ_FAILED",r"RCLONE_FAILED:[a-z0-9_ ]+"):
    if re.search(pattern,s,re.I):
        print("Diagnostic category:",pattern.replace("\\b",""))
if sys.argv[1].endswith("/gpu-session.log"):
    # Distinguish provider refusal from transient capacity without exposing account data.
    categories={
        "PRECONDITION_REFUSED":r"precondition failed|allocation refused|TooManyAssignmentsError|\b412\b",
        "SERVICE_UNAVAILABLE":r"service unavailable|\b503\b|\b502\b|\b504\b",
        "USAGE_LIMIT":r"usage limit|compute units|resource exhausted|quota exceeded|rate limit|\b429\b",
        "NO_GPU_AVAILABLE":r"no (?:available|backend|GPU)|GPU.*not available|cannot allocate",
        "ACCESS_DENIED":r"\b401\b|\b403\b|permission denied|scope_not_permitted",
        "TIMEOUT":r"timed out|timeout|ReadTimeout"
    }
    matches=[k for k,v in categories.items() if re.search(v,s,re.I)]
    print("COLAB_ALLOCATION_CAUSE="+(",".join(matches) if matches else "UNCLASSIFIED"),flush=True)
if sys.argv[1].endswith("/translation.log"):
    import json
    for line in s.splitlines():
        if "INDEX_GPU_DIAGNOSTIC=" not in line: continue
        try:
            d,_=json.JSONDecoder().raw_decode(line.split("INDEX_GPU_DIAGNOSTIC=",1)[1])
            keys=("offloads","server_gpu_mib","gpu_free_mib","gpu_total_mib","cuda_model_buffers_mib","cuda_log_seen")
            print("GPU_DIAGNOSTIC "+json.dumps({k:d[k] for k in keys}))
        except (ValueError,KeyError,TypeError): pass
PY
    return "$rc"
  fi
}
allocate_gpu() {
allocation_started=1
# Keep T4 only; do not switch to potentially billable accelerators or bypass quota.
# The CLI handles its own bounded retries of transient server failures.
export COLAB_CLI_ASSIGN_RETRIES=3
echo "COLAB_PHASE=GPU_ALLOCATION"
check gpu-session 600 "${cli[@]}" new -s "$gpu" --gpu T4 || { session_rc=$?; if grep -Eqi "connection was lost|connection reset|timed out|timeout|service unavailable|502|503|504" "$tmp/gpu-session.log" && ! grep -Eqi "401|403|412|429|quota|usage limit|permission denied|invalid_grant|TooManyAssignmentsError|resource exhausted" "$tmp/gpu-session.log"; then session_rc=75; fi; return "$session_rc"; }
allocation_ready=1
}
prepare_auth() {
  mkdir -m 700 -p "$tmp"
python - <<'PY'
import os,json
p=os.environ["GOOGLE_APPLICATION_CREDENTIALS"]
try:
    data=json.loads(os.environ["COLAB_ADC_JSON"])
    assert data["type"] == "authorized_user"
    assert all(data.get(k) for k in ("client_id","client_secret","refresh_token"))
except Exception:
    raise SystemExit("ADC secret missing or invalid authorized_user JSON")
with open(p,"w") as f:
    json.dump(data,f)
print("ADC secret format OK")
PY
unset COLAB_ADC_JSON

  python tools/llm/colab-drive-auth.py
  unset RCLONE_CONFIG_SECRET
  check auth 90 "${cli[@]}" sessions
  python tools/llm/session-check.py PRE
}
prepare_cache() {
  # Emit only fixed, sanitized progress lines; never stream raw credential logs.
  local rc=0
  timeout 2400 python tools/llm/colab-cache-populate.py </dev/null 2>&1 | python -u -c '
import sys,re
safe=re.compile(r"(?:CACHE_STAGE: (?:listing|verify_manifest|repair_invalid_manifest|source_metadata|(?:model|llama|cudart)_(?:recover|download|upload)|publish_manifest)|CACHE_(?:FILE_(?:REUSED|SAVED) (?:model|llama|cudart) [0-9]+|ENGINE_REUSED (?:llama|cudart)|UPLOAD_(?:ATTEMPT|RETRY) (?:model|llama|cudart) [1-3](?: [A-Za-z0-9_: -]+)?|ERROR:[A-Za-z]+:[A-Za-z0-9_:= -]+:line=[0-9]+)|CACHE_PREPARED=\{.*\})")
for line in sys.stdin:
    line=line.rstrip("\r\n")
    if safe.fullmatch(line) and not line.startswith("CACHE_PREPARED="): print(line,flush=True)
    elif line.startswith("CACHE_PREPARED="):
        import json
        obj=json.loads(line.split("=",1)[1])
        assert obj["mode"] in ("hit","created","repaired")
        print("CACHE_PREPARED="+json.dumps({"mode":obj["mode"],"bytes":int(obj["bytes"]),"seconds":float(obj["seconds"])}),flush=True)
' | tee "$tmp/cache-preflight.log" || rc=$?
  if [ "$rc" != 0 ]; then echo "cache-preflight: FAIL (exit $rc)"; return "$rc"; fi
  echo "cache-preflight: PASS"
  python tools/llm/colab-bootstrap.py "$tmp" "$HOME/.cache/ro-llm/rclone"
}
comparison_profiles() {
  python -c 'import json; rows=json.load(open("tools/llm/colab-profiles.json")); assert len(rows)==3; [print(x["name"]+"\t"+json.dumps(x["profile"],separators=(",",":"))) for x in rows]'
}
select_comparison_model() {
  local name="$1" profile
  profile=$(python - "$tmp/profiles.tsv" "$name" <<'PY'
import sys
rows=[line.rstrip("\n").split("\t",1) for line in open(sys.argv[1])]
matches=[profile for name,profile in rows if name==sys.argv[2]]
assert len(matches)==1
print(matches[0])
PY
)
  export RO_CACHE_PROFILE_JSON="$profile" RO_REVIEW_MODEL="$name"
}
prepare_comparison_model_cache() {
  select_comparison_model "$1"
  echo "CACHE_MODEL=$RO_REVIEW_MODEL"
  prepare_cache
  cp "$tmp/bootstrap.json" "$tmp/bootstrap-$RO_REVIEW_MODEL.json"
}
allocate_comparison_session() {
  gpu="ro-translate-$GITHUB_RUN_ID-${RO_SESSION_SUFFIX:-1}"
  test ! -e "$tmp/comparison-session"
  printf '%s\n' "$gpu" > "$tmp/comparison-session"
  allocate_gpu
  echo "COMPARISON_SESSION_READY"
}

session_context() {
  gpu="ro-translate-$GITHUB_RUN_ID-${RO_SESSION_SUFFIX:-1}"
  test "$(cat "$tmp/comparison-session")" = "$gpu"
  test -s "$tmp/sessions.json"
  export RO_REVIEW_SHARED_ROOT="/tmp/ro-update-$GITHUB_RUN_ID-$GITHUB_RUN_ATTEMPT-${RO_SESSION_SUFFIX:-1}"
}
prefetch_models() {
  session_context
  select_comparison_model 'Index-Translate-9B-Q6_K'
  export REMOTE_CONFIG="/tmp/ro-update-$GITHUB_RUN_ID-$GITHUB_RUN_ATTEMPT-${RO_SESSION_SUFFIX:-1}.conf"
  cp "$tmp/bootstrap-$RO_REVIEW_MODEL.json" "$tmp/bootstrap.json"
# Refresh on the runner immediately before passing a short-lived credential.
python - <<'PY'
import configparser,json,os,pathlib
p=pathlib.Path(os.environ["RO_CACHE_TMP"])
c=configparser.ConfigParser(interpolation=None);c.read(p/"drive.conf")
t=json.loads(c["rocache"]["token"]);t["expiry"]="2000-01-01T00:00:00Z"
c["rocache"]["token"]=json.dumps(t)
with (p/"drive.conf").open("w") as f: c.write(f)
PY
local cache_remote
cache_remote=$(python tools/llm/colab_cache_layout.py)
check drive-refresh 120 rclone --config "$tmp/drive.conf" lsjson "$cache_remote" --files-only
python - <<'PY'
import configparser,json,os,pathlib,datetime
p=pathlib.Path(os.environ["RO_CACHE_TMP"])
c=configparser.ConfigParser(interpolation=None);c.read(p/"drive.conf")
t=json.loads(c["rocache"]["token"])
expiry=datetime.datetime.fromisoformat(t["expiry"].replace("Z","+00:00"))
assert (expiry-datetime.datetime.now(datetime.timezone.utc)).total_seconds()>2700
short=configparser.ConfigParser(interpolation=None)
short["rocache"]={"type":"drive","scope":"drive.file","client_id":c["rocache"]["client_id"],"token":json.dumps({k:t[k] for k in ("access_token","token_type","expiry")})}
with (p/"short.conf").open("w") as f: short.write(f)
PY
check token-upload 60 "${cli[@]}" upload -s "$gpu" "$tmp/short.conf" "$REMOTE_CONFIG"
# Keep the refresh-capable Drive config only on the runner until cleanup.
rm -f "$tmp/short.conf"

  timeout 2500 python tools/llm/pipeline.py prefetch "$tmp" "$gpu" </dev/null
}
run_model() {
  session_context
  select_comparison_model "$1"
  test -f "$tmp/chain-prefetch-ready"
  cp "$tmp/bootstrap-$RO_REVIEW_MODEL.json" "$tmp/bootstrap.json"
  local limit=4350
  if [ "${RO_LIVE_AUDIT:-0}" = 1 ] && [ "$2" = verify ]; then limit=6150; fi
  timeout "$limit" python tools/llm/pipeline.py run "$tmp" "$gpu" "$2" </dev/null
}
cleanup() {
  local rc=0
  if [ -f "$GOOGLE_APPLICATION_CREDENTIALS" ] && [ -f "$tmp/comparison-session" ]; then
    gpu=$(cat "$tmp/comparison-session")
    check stop-session 90 "${cli[@]}" stop -s "$gpu" || rc=$?
    python tools/llm/session-check.py POST || rc=$?
  fi
  rm -rf "$tmp"
  return "$rc"
}
