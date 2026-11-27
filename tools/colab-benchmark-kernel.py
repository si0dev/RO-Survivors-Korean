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
import queue
import threading
from concurrent.futures import ThreadPoolExecutor
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
def invoke(args,limit,on_line=None):
    lines=[]
    q=queue.Queue()
    with subprocess.Popen(args,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT,text=True,errors="replace",bufsize=1) as p:
        def reader():
            try:
                for line in p.stdout: q.put(line)
            finally: q.put(None)
        t=threading.Thread(target=reader,daemon=True);t.start()
        deadline=time.monotonic()+limit
        try:
            while True:
                remaining=deadline-time.monotonic()
                if remaining<=0: raise subprocess.TimeoutExpired(args,limit)
                try: line=q.get(timeout=min(remaining,10))
                except queue.Empty: continue
                if line is None: break
                lines.append(line)
                if on_line and line.endswith("\n"): on_line(line.rstrip("\r\n"))
            return p.wait(timeout=max(0.1,deadline-time.monotonic())),"".join(lines)
        except subprocess.TimeoutExpired:
            p.kill();p.wait();t.join(timeout=5)
            while True:
                try: line=q.get_nowait()
                except queue.Empty: break
                if line is None: break
                lines.append(line)
                if on_line and line.endswith("\n"): on_line(line.rstrip("\r\n"))
            return 124,"".join(lines)+"\nTimeoutError\n"
        finally:
            if p.poll() is None: p.kill();p.wait()
            t.join(timeout=5)
def safe_progress(line,emit):
    if re.fullmatch(r"(?:GPU_READY|RCLONE_BOOTSTRAP_START|RCLONE_BOOTSTRAP_READY|LOCAL_MODEL_COPY_START|LOCAL_MODEL_READY|MODEL_SERVER_START|MODEL_READY|INDEX_FULL_GPU_OFFLOAD \d+/\d+|MODEL_(?:SERVER|LOAD)_SECONDS \d+(?:\.\d+)?|CACHE_COPY_(?:START|DONE)=(?:manifest|model|llama|cudart)|CACHE_COPY_PERCENT=(?:manifest|model|llama|cudart):(?:100|[0-9]{1,2}))",line):
        emit(line,flush=True)
    # Only numeric, fixed-schema fields; never echo raw CLI logs.
    for marker,keys in (("LOCAL_MODEL_COPY=",("bytes","copy_seconds","verify_seconds")),("INDEX_GPU_DIAGNOSTIC=",("server_gpu_mib","gpu_free_mib","gpu_total_mib"))):
        if not line.startswith(marker): continue
        try:
            data=json.loads(line[len(marker):])
            values={key:data[key] for key in keys}
            if all(type(v) in (int,float) and 0<=v<10**12 for v in values.values()):
                emit(marker+json.dumps(values),flush=True)
        except (ValueError,KeyError,TypeError): pass
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
    if re.search(r"invalid_grant|invalid_scope|quota exceeded|usage limit|compute units|resource exhausted|rate limit|\b429\b|permission denied|access denied|CACHE_(?:NOT_READY|SIZE_MISMATCH)|HASH_MISMATCH|ENGINE_(?:ASSET_UNAVAILABLE|ARGUMENTS_FAILED|DEPENDENCY_FAILED|OPTION_UNAVAILABLE)|FULL_GPU_OFFLOAD_UNCONFIRMED|GPU_MODEL_MEMORY_NOT_VERIFIED|RCLONE_BOOTSTRAP_AUTH|LOCAL_MODEL_COPY_(?:AUTH_FAILED|ACCESS_DENIED|QUOTA)|RCLONE_VERSION_MISMATCH|RCLONE_BOOTSTRAP_HTTP_429",raw,re.I):
        return 1
    if category=="AUTH":
        return 1
    if count==0 or category in ("CONNECTION_LOST","KERNEL_GONE","SESSION_GONE","FILE_UNAVAILABLE","TIMEOUT") or re.search(r"RCLONE_BOOTSTRAP_CONNECTION|RCLONE_BOOTSTRAP_HTTP_50[234]|LOCAL_MODEL_COPY_TIMEOUT",raw):
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
    def execute(source,limit,on_line):
        script=log.with_name("kernel-call.py")
        script.write_text(source,encoding="utf-8")
        args=[*cli,"exec","-s",session,"--timeout",str(limit),"-f",str(script)]
        if run is invoke: return run(args,limit+30,on_line=on_line)
        rc,raw=run(args,limit+30)
        for line in raw.splitlines(): on_line(line)
        return rc,raw
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
    rc,raw=execute(init,1800,lambda line:safe_progress(line,emit))
    append(raw)
    if rc or ready not in raw.splitlines():
        return report_failure("INIT",raw,probe,emit)
    emit("COLAB_KERNEL_MODEL_READY",flush=True)
    start=time.monotonic()
    # At most one outstanding verified snapshot, overlapping the next batch.
    with ThreadPoolExecutor(max_workers=1) as writer:
        commit=None
        for i in range(0,len(pending),batch_size):
            batch=pending[i:i+batch_size]
            batch_ids={r["id"] for r in batch}
            received={}
            def on_line(line):
                match=re.fullmatch(re.escape(prefix)+r"([A-Za-z0-9+/=]+)",line)
                if not match:
                    safe_progress(line,emit)
                    return
                row=json.loads(base64.b64decode(match[1],validate=True))
                verified=validate([row],batch_ids)
                if set(verified)&(set(saved)|set(received)):
                    raise RuntimeError("CHECKPOINT_RESULT_CONFLICT")
                received.update(verified)
                emit(f"COLAB_TRANSLATED={len(saved)+len(received)}/200",flush=True)
            code=("import base64 as ro_b64,json as ro_json\n"
                "from concurrent.futures import ThreadPoolExecutor as ro_pool,as_completed as ro_completed\n"
                "ro_batch=ro_json.loads("+repr(json.dumps(batch,ensure_ascii=False))+")\n"
                "ro_errors=[]\n"
                "with ro_pool(max_workers=4) as ro_executor:\n"
                "    ro_futures=[ro_executor.submit(ro_bench_ns['translate_one'],r,ro_bench_ns['base']) for r in ro_batch]\n"
                "    for ro_future in ro_completed(ro_futures):\n"
                "        try: ro_row=ro_future.result()\n"
                "        except Exception as ro_exc: ro_errors.append(ro_exc);continue\n"
                "        print("+repr(prefix)+"+ro_b64.b64encode(ro_json.dumps(ro_row,ensure_ascii=False).encode('utf-8')).decode('ascii'),flush=True)\n"
                "if ro_errors: raise ro_errors[0]\n"
                "print("+repr(done)+",flush=True)\n")
            rc,raw=execute(code,1500,on_line)
            if commit is not None:
                commit.result()
                emit(f"COLAB_KERNEL_PROGRESS={len(saved)}/200",flush=True)
                commit=None
            if received:
                saved={**saved,**received}
                for row in received.values(): record(row)
                elapsed=round(time.monotonic()-start,1)
                append(f"TRANSLATION_PROGRESS {len(saved)}/200 {elapsed}")
                commit=writer.submit(store.save,dict(saved))
            if rc or done not in raw.splitlines() or set(received)!=batch_ids:
                if commit is not None:
                    commit.result()
                    emit(f"COLAB_KERNEL_PROGRESS={len(saved)}/200",flush=True)
                return report_failure("BATCH",raw,probe,emit)
        if commit is not None:
            commit.result()
            emit(f"COLAB_KERNEL_PROGRESS={len(saved)}/200",flush=True)
    if set(saved)!=ids:
        raise RuntimeError("CHECKPOINT_INCOMPLETE")
    append("BENCHMARK_DONE")
    return 0
