import sys,subprocess,json,re
from collections import Counter
import torch
assert torch.cuda.is_available() and "T4" in torch.cuda.get_device_name(0)
print("GPU_READY",flush=True)
import os,time,tempfile,tarfile,pathlib,atexit
from concurrent.futures import ThreadPoolExecutor
import urllib.request
import requests

load_start=time.monotonic()
d=verified_manifest()
assert d is not None,"CACHE_NOT_READY"
root=pathlib.Path(tempfile.mkdtemp(prefix="index-llama-"))
if shutil.disk_usage(root).free<sum(e["size"] for e in d["files"])+2*1024**3:
    raise RuntimeError("LOCAL_DISK_SPACE_INSUFFICIENT")
for entry in d["files"]:
    if entry["kind"]=="model": continue
    archive=cache/entry["name"]
    copy_asset(CONFIG,entry["name"],archive,entry)
    with tarfile.open(archive,"r:*") as tf: tf.extractall(root,filter="data")
    archive.unlink()
server=next(root.rglob("llama-server"))
entry=next(e for e in d["files"] if e["kind"]=="model")
model_path=root/MODEL
print("LOCAL_MODEL_COPY_START",flush=True)
copy_seconds,verify_seconds=copy_asset(CONFIG,MODEL,model_path,entry)
with model_path.open("rb") as f: assert f.read(4)==b"GGUF","LOCAL_MODEL_HASH_MISMATCH"
pathlib.Path(CONFIG).unlink(missing_ok=True)
print("LOCAL_MODEL_COPY="+json.dumps({"bytes":entry["size"],"copy_seconds":round(copy_seconds,1),"verify_seconds":round(verify_seconds,1)}),flush=True)
libs=sorted({str(p.parent) for p in root.rglob("*.so*")})
env=dict(os.environ,LD_LIBRARY_PATH=":".join(libs+[os.environ.get("LD_LIBRARY_PATH","")]))
# Validate the executable and retain only non-sensitive failure classifications.
def engine_diagnostic(stage,output,rc):
    patterns={
        "missing_library":r"error while loading shared libraries|not found",
        "glibc_mismatch":r"GLIBC(?:XX)?_[\d.]+.*not found",
        "cuda_driver_mismatch":r"CUDA driver version is insufficient|driver/library version mismatch|unsupported.*driver",
        "cuda_kernel_mismatch":r"no kernel image|invalid device function|unsupported gpu architecture",
        "out_of_memory":r"out of memory|failed to allocate|allocation failed|cudaMalloc.*fail",
        "invalid_argument":r"invalid argument|unknown argument|unrecognized option|invalid option|unknown option",
        "model_read":r"failed to read|failed to open|Input/output error|GGUF.*(?:invalid|error)|failed to load model",
        "permission":r"permission denied",
        "illegal_instruction":r"illegal instruction",
        "bind":r"failed to bind|address already in use",
        "missing_symbol":r"undefined symbol|symbol lookup error",
        "cuda_error":r"CUDA error|CUDA failure|ggml_cuda.*(?:error|failed)",
        "context_error":r"failed to create context|context.*(?:too large|failed)",
    }
    missing=sorted(set(re.findall(r"\b(?:lib[A-Za-z0-9_+.-]+\.so(?:\.[0-9]+)*)\s*=>\s*not found",output)))
    symbols=sorted(set(re.findall(r"\bGLIBC(?:XX)?_[0-9.]+",output)))[:12]
    flags=sorted(set(re.findall(r"--(?:fit|no-mmap|load-mode|reasoning|log-verbosity|log-file|jinja|chat-template-kwargs|n-gpu-layers|ctx-size|parallel|host|port)\b",output))) if re.search(patterns["invalid_argument"],output,re.I) else []
    categories=[k for k,v in patterns.items() if re.search(v,output,re.I)]
    d={"stage":stage,"returncode":rc,"categories":categories,"missing_libraries":missing,"glibc_versions":symbols,"flags":flags}
    print("ENGINE_DIAGNOSTIC="+json.dumps(d,separators=(",",":")),flush=True)
    # Static allowlist of relevant terms, never full raw logs.
    return categories

def run_check(args,stage,timeout=30):
    r=subprocess.run(args,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,errors="replace",timeout=timeout)
    engine_diagnostic(stage,r.stdout,r.returncode)
    return r

ldd=run_check(["ldd",str(server)],"ldd")
if ldd.returncode or re.search(r"=>\s*not found|version .* not found",ldd.stdout):
    raise RuntimeError("ENGINE_DEPENDENCY_FAILED")
help_result=run_check([str(server),"--help"],"help")
if help_result.returncode:
    raise RuntimeError("ENGINE_HELP_FAILED")
# Only pass optional flags advertised by this exact cached binary.
help_text=help_result.stdout
# Small review prompts do not require a large KV cache; keep identical
# settings across all reviewer models and leave translation mode unchanged.
context_size="4096" if globals().get("REVIEW_ONLY",False) else "16384"
cmd=[str(server),"-m",str(model_path),"-ngl","all","--load-mode","none","-c",context_size,"-np","4","--host","127.0.0.1","--port","18080"]
for flag,values in (("--fit",["off"]),("--log-verbosity",["4"]),("--log-file",[str(root/"llama.log")]),("--jinja",[]),("--reasoning",["off"])):
    if re.search(r"(?<![\w-])"+re.escape(flag)+r"(?![\w-])",help_text): cmd.extend([flag,*values])
    else: print("ENGINE_OPTION_UNAVAILABLE "+flag,flush=True)
# Validate the entire actual option list before starting model loading.
option_check=run_check(cmd+["--help"],"arguments")
if option_check.returncode:
    raise RuntimeError("ENGINE_ARGUMENTS_FAILED")
server_start=time.monotonic()
server_log=open(root/"server.log","w+")
print("MODEL_SERVER_START",flush=True)
proc=subprocess.Popen(["stdbuf","-oL","-eL",*cmd],stdout=server_log,stderr=subprocess.STDOUT,env=env)
atexit.register(lambda: proc.terminate() if proc.poll() is None else None)
base="http://127.0.0.1:18080"
def read_engine_log():
    server_log.flush()
    log=(root/"server.log").read_text(errors="replace")
    if (root/"llama.log").exists(): log+="\n"+(root/"llama.log").read_text(errors="replace")
    return log
deadline=time.monotonic()+900
while time.monotonic()<deadline:
    if proc.poll() is not None:
        engine_diagnostic("server",read_engine_log(),proc.returncode)
        raise RuntimeError("ENGINE_START_FAILED")
    try:
        if requests.get(base+"/health",timeout=3).status_code==200: break
    except requests.RequestException: pass
    time.sleep(2)
else:
    engine_diagnostic("ready_timeout",read_engine_log(),proc.poll())
    raise RuntimeError("ENGINE_READY_TIMEOUT")
# Read the final load, not the initial fit probe, and report only safe numeric diagnostics.
offloads=[]
for _ in range(10):
    server_log.flush()
    log=(root/"server.log").read_text(errors="replace")
    if (root/"llama.log").exists(): log+="\n"+(root/"llama.log").read_text(errors="replace")
    offloads=re.findall(r"offloaded\s+(\d+)\s*/\s*(\d+)\s+layers\s+to\s+GPU",log,re.I)
    if offloads and offloads[-1][0]==offloads[-1][1] and int(offloads[-1][0])>0: break
    time.sleep(1)
def gpu_process_mib():
    output=subprocess.check_output(["nvidia-smi","--query-compute-apps=pid,used_gpu_memory","--format=csv,noheader,nounits"],text=True)
    return sum(int(m.group(2)) for line in output.splitlines() if (m:=re.fullmatch(r"\s*(\d+)\s*,\s*(\d+)\s*",line)) and int(m.group(1))==proc.pid)
gpu_mib=gpu_process_mib()
free,total=torch.cuda.mem_get_info()
diagnostic={"offloads":[list(map(int,x)) for x in offloads],"server_gpu_mib":gpu_mib,"gpu_free_mib":free//1048576,"gpu_total_mib":total//1048576,"cuda_model_buffers_mib":[float(v) for v in re.findall(r"CUDA\d+\s+model buffer size\s*=\s*([\d.]+)\s*MiB",log,re.I)],"cuda_log_seen":bool(re.search(r"ggml_cuda|CUDA0",log,re.I))}
print("INDEX_GPU_DIAGNOSTIC="+json.dumps(diagnostic,separators=(",",":")),flush=True)
if gpu_mib<5500: raise RuntimeError("GPU_MODEL_MEMORY_NOT_VERIFIED")
if offloads and offloads[-1][0]==offloads[-1][1] and int(offloads[-1][0])>0:
    print("INDEX_FULL_GPU_OFFLOAD "+"/".join(offloads[-1]),flush=True)
else:
    print("INDEX_FULL_GPU_OFFLOAD_UNCONFIRMED",flush=True)
print("MODEL_SERVER_SECONDS "+str(round(time.monotonic()-server_start,1)),flush=True)
print("MODEL_LOAD_SECONDS "+str(round(time.monotonic()-load_start,1)),flush=True)
if globals().get("MODEL_SOURCE_MODE","local")=="local":
    assert offloads and offloads[-1][0]==offloads[-1][1] and int(offloads[-1][0])>0,"LOCAL_FULL_GPU_OFFLOAD_UNCONFIRMED"
    print("LOCAL_MODEL_READY",flush=True)
print("MODEL_READY",flush=True)

