"""Run one detached Colab worker; collect its log over bounded, fresh CLI calls.

A failed transport call never starts a second worker or requests a GPU.
The workflow owns allocation and cleanup. Only safe diagnostics are emitted.
"""
import os
import pathlib
import re
import subprocess
import sys
import time

SUPERVISOR = """import pathlib, subprocess, sys
work = pathlib.Path(sys.argv[1])
with (work / "worker.log").open("a", encoding="utf-8") as log:
    try:
        code = subprocess.call([sys.executable, "-u", str(work / "worker.py")],
                               stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT)
    except BaseException:
        code = 1
        log.write("\\nREMOTE_SUPERVISOR_ERROR\\n")
    log.write("\\nREMOTE_WORKER_EXIT " + str(code) + "\\n")
    log.flush()
"""

def launch_source(worker, work):
    return (
        "import os,pathlib,subprocess,sys\n"
        "os.umask(0o077)\n"
        "work=pathlib.Path("+repr(work)+")\n"
        "work.mkdir(mode=0o700,exist_ok=False)\n"
        "(work/'worker.py').write_text("+repr(worker)+",encoding='utf-8')\n"
        "(work/'supervisor.py').write_text("+repr(SUPERVISOR)+",encoding='utf-8')\n"
        "(work/'worker.log').touch()\n"
        "subprocess.Popen([sys.executable,'-u',str(work/'supervisor.py'),str(work)],"
        "stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,"
        "start_new_session=True,close_fds=True)\n"
        "print('REMOTE_WORKER_LAUNCHED',flush=True)\n"
    )

def classify(raw):
    categories={
        "CONNECTION_LOST":r"Connection was lost|WebSocketConnectionClosedException|Connection reset",
        "KERNEL_GONE":r"Kernel (?:dead|restarting)",
        "SESSION_GONE":r"Session .* not found|session .* appears to be lost",
        "AUTH":r"\b401\b|\b403\b|invalid_grant|unauthorized",
        "TIMEOUT":r"timed out|TimeoutError|Timeout waiting",
        "FILE_UNAVAILABLE":r"FileNotFoundError|File or directory not found|\b404\b",
    }
    return next((k for k,p in categories.items() if re.search(p,raw,re.I)),"UNCLASSIFIED")

def invoke(args,limit):
    try:
        r=subprocess.run(args,stdin=subprocess.DEVNULL,capture_output=True,text=True,
                         errors="replace",timeout=limit)
        return r.returncode,r.stdout+"\n"+r.stderr
    except subprocess.TimeoutExpired:
        return 124,"TimeoutError"

def collect(cli,session,worker,log,work,*,run=invoke,now=time.monotonic,pause=time.sleep,emit=print,limit=5400):
    log=pathlib.Path(log)
    log.write_text("",encoding="utf-8")
    launch=log.with_name("launch-worker.py")
    launch.write_text(launch_source(worker,work),encoding="utf-8")
    remote=work+"/worker.log"
    snapshot=log.with_name("worker-snapshot.log")
    start=now()
    code,raw=run([*cli,"exec","-s",session,"--timeout","60","-f",str(launch)],120)
    if code or "REMOTE_WORKER_LAUNCHED" not in raw:
        # Launch may have succeeded before the acknowledgment was lost.
        # Do not repeat it; probe the unique log file instead.
        emit("COLAB_TRANSPORT_LAUNCH="+classify(raw),flush=True)
    else:
        emit("COLAB_TRANSPORT_LAUNCH=OK",flush=True)
    last_progress=-1
    failures=0
    while now()-start<limit:
        snapshot.unlink(missing_ok=True)
        code,raw=run([*cli,"download","-s",session,remote,str(snapshot)],90)
        if code or not snapshot.is_file():
            failures+=1
            emit("COLAB_TRANSPORT_DOWNLOAD="+classify(raw)+" attempt="+str(failures),flush=True)
            if failures>=4:
                return 1
        else:
            failures=0
            data=snapshot.read_bytes()
            previous=log.read_bytes()
            if not data.startswith(previous):
                emit("COLAB_TRANSPORT_LOG_REGRESSION",flush=True)
                return 1
            log.write_bytes(data)
            text=data.decode("utf-8",errors="replace")
            count=len(re.findall(r"(?m)^BENCHMARK_RESULT=",text))
            if count!=last_progress:
                emit("COLAB_WORKER_PROGRESS="+str(count)+"/200",flush=True)
                last_progress=count
            m=re.search(r"(?m)^REMOTE_WORKER_EXIT (-?\d+)\n\Z",text)
            if m:
                rc=int(m.group(1))
                emit("COLAB_REMOTE_WORKER_EXIT="+str(rc),flush=True)
                return 0 if rc==0 else 1
        pause(25)
    emit("COLAB_TRANSPORT_DEADLINE",flush=True)
    return 1

if __name__=="__main__":
    # Paths are unique for each workflow run/attempt, not shared between workers.
    bundle,output,session,config,run_id,attempt=sys.argv[1:]
    assert run_id.isdigit() and attempt.isdigit()
    worker=pathlib.Path(bundle).read_text(encoding="utf-8")
    raise SystemExit(collect(["colab","--auth=adc","--config",config],session,worker,output,
                             "/tmp/ro-worker-"+run_id+"-"+attempt))
