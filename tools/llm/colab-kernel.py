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
transport=load("colab-transport")
def assignment_count():
    # Query the provider, not the CLI's possibly stale session cache.
    from colab_cli.auth import AuthProvider
    from colab_cli.common import state
    state.auth_provider=AuthProvider.ADC
    return len(state.client.list_assignments())
class HeartbeatTimeout(Exception):
    pass

def invoke(args,limit,on_line=None,on_wait=None,heartbeat=30):
    lines=[]
    q=queue.Queue()
    with subprocess.Popen(args,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT,text=True,errors="replace",bufsize=1) as p:
        def reader():
            try:
                for line in p.stdout: q.put(line)
            finally: q.put(None)
        t=threading.Thread(target=reader,daemon=True);t.start()
        started=time.monotonic()
        deadline=started+limit
        next_heartbeat=started+heartbeat
        try:
            while True:
                now=time.monotonic()
                if on_wait and now>=next_heartbeat:
                    if on_wait(int(now-started)) is False: raise HeartbeatTimeout()
                    next_heartbeat=now+heartbeat
                remaining=deadline-now
                if remaining<=0: raise subprocess.TimeoutExpired(args,limit)
                try: line=q.get(timeout=min(remaining,10,max(0.01,next_heartbeat-now) if on_wait else 10))
                except queue.Empty: continue
                if line is None: break
                lines.append(line)
                if on_line and line.endswith("\n"): on_line(line.rstrip("\r\n"))
            return p.wait(timeout=max(0.1,deadline-time.monotonic())),"".join(lines)
        except (subprocess.TimeoutExpired,HeartbeatTimeout) as exc:
            p.kill();p.wait();t.join(timeout=5)
            while True:
                try: line=q.get_nowait()
                except queue.Empty: break
                if line is None: break
                lines.append(line)
                if on_line and line.endswith("\n"): on_line(line.rstrip("\r\n"))
            marker="COLAB_HEARTBEAT_TIMEOUT" if isinstance(exc,HeartbeatTimeout) else "TimeoutError"
            return 124,"".join(lines)+"\n"+marker+"\n"
        finally:
            if p.poll() is None: p.kill();p.wait()
            t.join(timeout=5)
def safe_progress(line,emit):
    if re.fullmatch(r"(?:GPU_READY|RCLONE_BOOTSTRAP_START|RCLONE_BOOTSTRAP_READY|RCLONE_BOOTSTRAP_REUSED|SHARED_ENGINE_REUSED|LOCAL_MODEL_COPY_START|LOCAL_MODEL_READY|MODEL_SERVER_START|MODEL_READY|INDEX_FULL_GPU_OFFLOAD \d+/\d+|MODEL_(?:SERVER|LOAD)_SECONDS \d+(?:\.\d+)?|CACHE_COPY_(?:START|DONE)=(?:manifest|model|llama|cudart)|CACHE_COPY_PERCENT=(?:manifest|model|llama|cudart):(?:100|[0-9]{1,2}))",line):
        emit(line,flush=True)
    for marker in ("TRANSLATION_RETRY=","TRANSLATION_ERROR="):
        if not line.startswith(marker): continue
        try:
            data=json.loads(line[len(marker):])
            if not re.fullmatch(r"[0-9]{1,6}",data["id"]) or type(data["attempt"]) is not int or not 1<=data["attempt"]<=3:
                return
            if marker=="TRANSLATION_RETRY=":
                failures=data["failures"]
                if not isinstance(failures,list) or not all(v in ("hangul","placeholders","numbers","abbreviations","terms","format") for v in failures):
                    return
                safe={"id":data["id"],"attempt":data["attempt"],"failures":failures}
            else:
                if data["kind"] not in ("HTTP_TIMEOUT","HTTP_CONNECTION","HTTP_TRANSPORT","HTTP_STATUS","RESPONSE_SCHEMA") or type(data["status"]) is not int or not 0<=data["status"]<=599:
                    return
                safe={"id":data["id"],"attempt":data["attempt"],"kind":data["kind"],"status":data["status"]}
            emit(marker+json.dumps(safe),flush=True)
        except (ValueError,KeyError,TypeError): pass
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
    if category=="UNCLASSIFIED" and "COLAB_HEARTBEAT_TIMEOUT" in raw.splitlines():
        category="HEARTBEAT_TIMEOUT"
    emit("COLAB_KERNEL_FAILURE="+phase+":"+category,flush=True)
    if category in ("CONNECTION_LOST","KERNEL_GONE","SESSION_GONE"):
        emit("COLAB_CONNECTION_LOST phase="+phase+" evidence="+category,flush=True)
    elif category in ("HEARTBEAT_TIMEOUT","TIMEOUT"):
        emit("COLAB_CONNECTION_UNVERIFIED phase="+phase+" reason="+category,flush=True)
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
    if count==0 or category in ("CONNECTION_LOST","KERNEL_GONE","SESSION_GONE","FILE_UNAVAILABLE","TIMEOUT","HEARTBEAT_TIMEOUT") or re.search(r"RCLONE_BOOTSTRAP_CONNECTION|RCLONE_BOOTSTRAP_HTTP_50[234]|LOCAL_MODEL_COPY_TIMEOUT",raw):
        return 75
    return 1
