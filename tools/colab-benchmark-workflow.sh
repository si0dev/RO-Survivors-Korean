#!/usr/bin/env bash
set -euo pipefail
umask 077
tmp="$RUNNER_TEMP/ro-colab-state"
export XDG_CONFIG_HOME="$tmp/config"
export RO_CACHE_TMP="$tmp"
export GOOGLE_APPLICATION_CREDENTIALS="$tmp/adc.json"
cli=(colab --auth=adc --config "$tmp/sessions.json")
gpu="ro-translate-$GITHUB_RUN_ID"
allocation_started=0
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
restore_checkpoint() {
  rm -f "$tmp/checkpoint-complete"
  python benchmark/tools/colab-benchmark-checkpoint.py prepare "$tmp/drive.conf" "$RUNNER_TEMP/ro-benchmark" "$tmp"
}
checkpoint_count() {
  python -c 'import json,sys; print(len(json.load(open(sys.argv[1]))))' "$tmp/resume.json"
}
release_session() {
  timeout 60 "${cli[@]}" stop -s "$gpu" >"$tmp/stop.log" 2>&1 </dev/null || true
  timeout 180 python benchmark/tools/colab-session-cleanup.py POST
  allocation_started=0
  rm -f "$tmp/sessions.json"
}
run_session() {
allocation_started=1
gpu="ro-translate-$GITHUB_RUN_ID-$1"
export REMOTE_CONFIG="/tmp/ro-model-$GITHUB_RUN_ID-$GITHUB_RUN_ATTEMPT-$1.conf"
# Keep T4 only; do not switch to potentially billable accelerators or bypass quota.
# The CLI handles its own bounded retries of transient server failures.
export COLAB_CLI_ASSIGN_RETRIES=3
echo "COLAB_PHASE=GPU_ALLOCATION"
check gpu-session 600 "${cli[@]}" new -s "$gpu" --gpu T4 || { session_rc=$?; return 0; }
# Refresh on the runner immediately before passing a short-lived credential.
python - <<'PY'
import configparser,json,os,pathlib
p=pathlib.Path(os.environ["RO_CACHE_TMP"])
c=configparser.ConfigParser(interpolation=None);c.read(p/"drive.conf")
t=json.loads(c["rocache"]["token"]);t["expiry"]="2000-01-01T00:00:00Z"
c["rocache"]["token"]=json.dumps(t)
with (p/"drive.conf").open("w") as f: c.write(f)
PY
check drive-refresh 120 rclone --config "$tmp/drive.conf" lsjson rocache:RO-Survivors-Korean-cache-v2/index-translate-9b-q6k-b12343-v1 --files-only
python - <<'PY'
import configparser,json,os,pathlib,datetime
p=pathlib.Path(os.environ["RO_CACHE_TMP"])
c=configparser.ConfigParser(interpolation=None);c.read(p/"drive.conf")
t=json.loads(c["rocache"]["token"])
expiry=datetime.datetime.fromisoformat(t["expiry"].replace("Z","+00:00"))
assert (expiry-datetime.datetime.now(datetime.timezone.utc)).total_seconds()>1800
short=configparser.ConfigParser(interpolation=None)
short["rocache"]={"type":"drive","scope":"drive.file","client_id":c["rocache"]["client_id"],"token":json.dumps({k:t[k] for k in ("access_token","token_type","expiry")})}
with (p/"short.conf").open("w") as f: short.write(f)
PY
check token-upload 60 "${cli[@]}" upload -s "$gpu" "$tmp/short.conf" "$REMOTE_CONFIG" || { session_rc=$?; if grep -Eqi "connection was lost|connection reset|timed out|timeout|file or directory not found|502|503|504" "$tmp/token-upload.log" && ! grep -Eqi "401|403|429|quota|permission denied|invalid_grant" "$tmp/token-upload.log"; then session_rc=75; fi; return 0; }
# Keep the refresh-capable Drive config only on the runner until cleanup.
rm -f "$tmp/short.conf"
python - "$RUNNER_TEMP/ro-benchmark/inputs.json" "$tmp/benchmark.py" <<'PY'
import json,sys,os,pathlib
inputs=json.load(open(sys.argv[1]))
assert len(inputs)==200 and all("reference" not in row for row in inputs)
root=pathlib.Path("benchmark/tools")
body="import json\nINPUTS=json.loads("+repr(json.dumps(inputs,ensure_ascii=False))+")\nCONFIG="+repr(os.environ["REMOTE_CONFIG"])+"\n"
bootstrap=json.loads((pathlib.Path(os.environ["RO_CACHE_TMP"])/"bootstrap.json").read_text())
for key in ("RCLONE_DRIVE_ID","RCLONE_ZIP_SHA","MANIFEST_SHA"): body+=key+"="+repr(bootstrap[key])+"\n"
for name in ("colab-cache-mount.py","colab-benchmark-cache.py","colab-benchmark-model.py","colab-benchmark-translate.py"):
    body+=(root/name).read_text()+"\n"
# The kernel transport calls translate_one on pending batches after initialization.
compile(body,"benchmark.py","exec")
pathlib.Path(sys.argv[2]).write_text(body)
PY
echo "COLAB_PHASE=MODEL_AND_TRANSLATION"
session_rc=0
touch "$tmp/translation.log"
local remaining=$(($2-SECONDS))
if [ "$remaining" -le 0 ]; then session_rc=124; return 0; fi
if [ "$remaining" -gt 5700 ]; then remaining=5700; fi
timeout "$remaining" python benchmark/tools/colab-benchmark-checkpoint.py collect "$tmp/drive.conf" "$RUNNER_TEMP/ro-benchmark" "$tmp" "$gpu" "$GITHUB_RUN_ID" "$GITHUB_RUN_ATTEMPT" </dev/null || session_rc=$?
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

  python benchmark/tools/colab-drive-auth.py
  unset RCLONE_CONFIG_SECRET
  check auth 90 "${cli[@]}" sessions
  timeout 180 python benchmark/tools/colab-session-cleanup.py PRE
}
prepare_cache() {
  check cache-preflight 2400 python benchmark/tools/colab-cache-populate.py
  python benchmark/tools/colab-benchmark-bootstrap.py "$tmp" "$HOME/.cache/ro-llm/rclone"
}
run_benchmark() {
  cleanup_on_exit() {
    local rc=$?
    trap - EXIT
    if [ "$allocation_started" = 1 ]; then
      if ! release_session; then rc=1; fi
    fi
    exit "$rc"
  }
  trap cleanup_on_exit EXIT
  trap 'exit 130' INT
  trap 'exit 143' TERM
  source benchmark/tools/colab-benchmark-recover.sh
  recover_benchmark
}
final_cleanup() {
  local rc=0
  if [ -f "$GOOGLE_APPLICATION_CREDENTIALS" ]; then
    timeout 180 python benchmark/tools/colab-session-cleanup.py POST || rc=$?
  fi
  rm -rf "$tmp" "$RUNNER_TEMP/ro-benchmark"
  return "$rc"
}
