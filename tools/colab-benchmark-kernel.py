"""Execute actual inference in short kernel calls, without remote-file polling.

The model is initialized once in the persistent kernel. Each bounded call does
real translation and streams complete result records back for private checkpoint
storage. Never allocate, restart, or prolong an idle runtime.
"""
import base64
import importlib.util
import json
import pathlib
import re
import subprocess
import time
import uuid
ROOT=pathlib.Path(__file__).resolve().parent
def load(name):
    spec=importlib.util.spec_from_file_location(name,ROOT/(name+".py"))
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    return mod
transport=load("colab-benchmark-transport")
def assignment_count():
    # Query the provider, not the CLI's possibly stale session cache.
    from colab_cli.auth import AuthProvider
    from colab_cli.common import state
    state.auth_provider=AuthProvider.ADC
    return len(state.client.list_assignments())
def invoke(args,limit):
    # Preserve complete result records even when the command times out.
    try:
        p=subprocess.run(args,stdin=subprocess.DEVNULL,capture_output=True,text=True,errors="replace",timeout=limit)
        return p.returncode,p.stdout+"\n"+p.stderr
    except subprocess.TimeoutExpired as exc:
        def decode(value):
            return value.decode("utf-8",errors="replace") if isinstance(value,bytes) else value or ""
        return 124,decode(exc.stdout)+"\n"+decode(exc.stderr)+"\nTimeoutError\n"
def report_failure(phase,raw,probe,emit):
    category=transport.classify(raw)
    emit("COLAB_KERNEL_FAILURE="+phase+":"+category,flush=True)
    count=None
    try:
        count=probe()
        emit("COLAB_FAILURE_ACTIVE_ASSIGNMENTS="+str(count),flush=True)
    except Exception as exc:
        emit("COLAB_FAILURE_ASSIGNMENT_QUERY_FAILED="+type(exc).__name__,flush=True)
    # Respect quota, access restrictions and deterministic local failures.
    if re.search(r"invalid_grant|invalid_scope|quota exceeded|usage limit|compute units|resource exhausted|rate limit|\b429\b|permission denied|access denied|CACHE_(?:NOT_READY|SIZE_MISMATCH)|HASH_MISMATCH|ENGINE_(?:ASSET_UNAVAILABLE|ARGUMENTS_FAILED|DEPENDENCY_FAILED|OPTION_UNAVAILABLE)|FULL_GPU_OFFLOAD_UNCONFIRMED|GPU_MODEL_MEMORY_NOT_VERIFIED",raw,re.I):
        return 1
    if category=="AUTH":
        return 1
    if count==0 or category in ("CONNECTION_LOST","KERNEL_GONE","SESSION_GONE","FILE_UNAVAILABLE","TIMEOUT"):
        return 75
    return 1
def collect(cli,session,worker,log,inputs,saved,store,validate,*,run=invoke,probe=assignment_count,emit=print,batch_size=4):
    log=pathlib.Path(log)
    log.write_text("",encoding="utf-8")
    nonce=uuid.uuid4().hex
    prefix="RO_RESULT_"+nonce+"="
    ready="RO_READY_"+nonce
    done="RO_BATCH_DONE_"+nonce
    ids={r["id"] for r in inputs}
    if len(ids)!=200 or len(inputs)!=200 or not set(saved)<=ids:
        raise RuntimeError("CHECKPOINT_INPUTS")
    if any("reference" in r for r in inputs):
        raise RuntimeError("CHECKPOINT_INPUTS")
    def append(s):
        with log.open("a",encoding="utf-8") as f:
            f.write(s)
            if not s.endswith("\n"): f.write("\n")
    def record(row):
        append("BENCHMARK_RESULT="+json.dumps(row,ensure_ascii=False,separators=(",",":")))
    def execute(source,limit):
        script=log.with_name("kernel-call.py")
        script.write_text(source,encoding="utf-8")
        return run([*cli,"exec","-s",session,"--timeout",str(limit),"-f",str(script)],limit+30)
    for row in saved.values(): record(row)
    pending=[r for r in inputs if r["id"] not in saved]
    if not pending:
        append("BENCHMARK_DONE")
        return 0
    # Compile the existing model/translation implementation in an isolated
    # namespace retained by the kernel; no change to benchmark fingerprint.
    init=("ro_bench_ns={'__name__':'__main__'}\n"
        "exec(compile("+repr(worker)+",'benchmark-model.py','exec'),ro_bench_ns)\n"
        "print("+repr(ready)+",flush=True)\n")
    rc,raw=execute(init,1800)
    append(raw)
    if rc or ready not in raw.splitlines():
        return report_failure("INIT",raw,probe,emit)
    emit("COLAB_KERNEL_MODEL_READY",flush=True)
    start=time.monotonic()
    for i in range(0,len(pending),batch_size):
        batch=pending[i:i+batch_size]
        # Same two-way concurrency and translation contract as the original
        # worker. Print each completed row, including quality failures.
        code=("import base64 as ro_b64,json as ro_json\n"
            "from concurrent.futures import ThreadPoolExecutor as ro_pool\n"
            "ro_batch=ro_json.loads("+repr(json.dumps(batch,ensure_ascii=False))+")\n"
            "with ro_pool(max_workers=2) as ro_executor:\n"
            "    for ro_row in ro_executor.map(lambda r:ro_bench_ns['translate_one'](r,ro_bench_ns['base']),ro_batch):\n"
            "        print("+repr(prefix)+"+ro_b64.b64encode(ro_json.dumps(ro_row,ensure_ascii=False).encode('utf-8')).decode('ascii'),flush=True)\n"
            "print("+repr(done)+",flush=True)\n")
        rc,raw=execute(code,1500)
        # Do not print raw outputs or credentials. Decode only nonce-tagged
        # complete rows. A failed call may still have delivered some results.
        rows=[]
        for line in raw.splitlines():
            m=re.fullmatch(re.escape(prefix)+r"([A-Za-z0-9+/=]+)",line)
            if m:
                rows.append(json.loads(base64.b64decode(m[1],validate=True)))
        new=validate(rows,{r["id"] for r in batch})
        if set(new)&set(saved):
            raise RuntimeError("CHECKPOINT_RESULT_CONFLICT")
        if new:
            combined={**saved,**new}
            store.save(combined)
            saved=combined
            for row in new.values(): record(row)
            elapsed=round(time.monotonic()-start,1)
            append(f"TRANSLATION_PROGRESS {len(saved)}/200 {elapsed}")
            emit(f"COLAB_KERNEL_PROGRESS={len(saved)}/200",flush=True)
        # Don't re-submit a potentially still-running batch. Stop and preserve
        # all acknowledged results if the backend or transport failed.
        if rc or done not in raw.splitlines() or set(new)!={r["id"] for r in batch}:
            return report_failure("BATCH",raw,probe,emit)
    if set(saved)!=ids:
        raise RuntimeError("CHECKPOINT_INCOMPLETE")
    append("BENCHMARK_DONE")
    return 0
