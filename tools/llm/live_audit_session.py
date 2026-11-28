"""One allocated Colab, one GPU model at a time, many bounded inference calls."""
import json,os,pathlib,sys,time,uuid,shutil
ROOT=pathlib.Path(__file__).resolve().parent
MODELS={"index":"Index-Translate-9B-Q6_K","correct":"Hy-MT3-7B-Q8_0","verify":"Qwen3-14B-Q4_K_M"}

def start_source(bootstrap,shared,stage,marker):
    # The persistent kernel retains the live subprocess and its private handles.
    header="import builtins,shutil,subprocess\nassert not hasattr(builtins,'_ro_audit_model'), 'MODEL_ALREADY_LOADED'\n"
    ns={"PRELOADED_MODEL":True,"REVIEW_ONLY":True,"CHAIN_FULL_SCOPE":True,"REVIEW_SHARED_ROOT":shared}
    ns.update({k:bootstrap[k] for k in ("RCLONE_DRIVE_ID","RCLONE_ZIP_SHA","MANIFEST_SHA","CACHE_SPEC")})
    body=(ROOT/"colab-model.py").read_text()
    return header+"ns="+repr(ns)+"\ntry:\n    exec(compile("+repr(body)+",'audit-model','exec'),ns)\n    builtins._ro_audit_model=( "+repr(stage)+",ns)\nexcept BaseException:\n    child=ns.get('proc')\n    if child is not None and child.poll() is None:\n        child.terminate()\n        try: child.wait(timeout=30)\n        except subprocess.TimeoutExpired: child.kill();child.wait(timeout=30)\n    if ns.get('server_log') is not None: ns['server_log'].close()\n    if ns.get('root') is not None: shutil.rmtree(ns['root'],ignore_errors=True)\n    raise\nprint("+repr(marker)+",flush=True)\n"

def batch_source(stage,payload,marker):
    done=marker+"BATCH_DONE"
    return ("import builtins,requests\n"
      +"stage,ns=builtins._ro_audit_model\nassert stage=="+repr(stage)+" and ns['proc'].poll() is None,'AUDIT_MODEL_NOT_RUNNING'\n"
      +"base=ns['base']\nassert requests.get(base+'/health',timeout=5).status_code==200,'AUDIT_MODEL_NOT_HEALTHY'\n"
      +payload+"\nprint("+repr(done)+",flush=True)\n"),done

def stop_source(stage,marker):
    return ("import builtins,subprocess,shutil\nstage,ns=builtins._ro_audit_model\nassert stage=="+repr(stage)+"\n"
      +"child=ns['proc']\nif child.poll() is None:\n    child.terminate()\n    try: child.wait(timeout=30)\n    except subprocess.TimeoutExpired: child.kill();child.wait(timeout=30)\n"
      +"ns['server_log'].close()\nshutil.rmtree(ns['root'],ignore_errors=True)\ndel builtins._ro_audit_model\nprint("+repr(marker)+",flush=True)\n")

def remote(tmp,session,body,marker,limit,phase):
    import pipeline
    kernel=pipeline.load("colab-kernel")
    compile(body,"audit-remote","exec")
    path=tmp/"audit-control.py";path.write_text(body)
    ready=False;last=time.monotonic()
    def on_line(line):
        nonlocal ready,last
        if line==marker: ready=True;last=time.monotonic()
        else:
            def emit(value,**kw):
                nonlocal last
                last=time.monotonic();print(value,**kw)
            kernel.safe_progress(line,emit)
    def waiting(elapsed):
        print(f"AUDIT_CONTROL_WAIT={phase}:{elapsed}s",flush=True)
        return time.monotonic()-last<900
    args=["colab","--auth=adc","--config",str(tmp/"sessions.json"),"exec","-s",session,"--timeout",str(limit),"-f",str(path)]
    rc,raw=kernel.invoke(args,limit+15,on_line=on_line,on_wait=waiting)
    if rc or not ready:
        if rc: kernel.report_failure(phase,raw,kernel.assignment_count,print)
        raise RuntimeError("AUDIT_CONTROL_FAILED:"+phase)

def execute(tmp,session,inputs,results):
    import pipeline,subprocess
    manifest=json.loads((inputs/"manifest.json").read_text())
    batches=manifest["batches"]
    # Keep independent row checkpoints in the same runner; never allocate again.
    work=tmp/"audit-batches";work.mkdir()
    os.environ["RO_AUDIT_REUSE_MODEL"]="1"
    os.environ["RO_LIVE_AUDIT"]="1"
    os.environ["RO_AUDIT_DEADLINE"]=str(time.monotonic()+5*3600)
    counts={k:0 for k in MODELS}
    try:
        for b in batches:
            folder=work/b["batch"]
            subprocess.run(["node","tools/llm/live-audit.mjs","unpack",str(inputs),b["batch"],str(folder)],check=True)
        for stage,name in MODELS.items():
            if float(os.environ["RO_AUDIT_DEADLINE"])-time.monotonic()<1000: raise RuntimeError("AUDIT_TIME_BUDGET")
            marker="AUDIT_START_"+uuid.uuid4().hex
            bootstrap=json.loads((tmp/("bootstrap-"+name+".json")).read_text())
            remote(tmp,session,start_source(bootstrap,os.environ["RO_REVIEW_SHARED_ROOT"],stage,marker),marker,960,"START_"+stage)
            print("AUDIT_MODEL_LOADED="+stage,flush=True)
            try:
                for b in batches:
                    folder=work/b["batch"]
                    for file in {"index":["pending.json"],"correct":["indexed.json"],"verify":["corrected.json","audit-references.json"]}[stage]:
                        shutil.copyfile(folder/file,tmp/file)
                    print("AUDIT_BATCH="+stage+":"+b["batch"],flush=True)
                    pipeline.run(tmp,session,stage)
                    output={"index":"indexed.json","correct":"corrected.json","verify":"verified.json"}[stage]
                    shutil.copyfile(tmp/output,folder/output)
                    if stage=="verify":
                        shutil.copyfile(tmp/"audit-review.json",folder/"audit-review.json")
                        subprocess.run([sys.executable,str(ROOT/"live-audit-report.py"),str(folder),str(results)],check=True)
                    counts[stage]+=b["count"]
                    print("AUDIT_STAGE_PROGRESS="+stage+":"+str(counts[stage])+"/"+str(manifest["total"]),flush=True)
            finally:
                marker="AUDIT_STOP_"+uuid.uuid4().hex
                remote(tmp,session,stop_source(stage,marker),marker,90,"STOP_"+stage)
                print("AUDIT_MODEL_RELEASED="+stage,flush=True)
    finally:
        print("AUDIT_STAGE_COUNTS="+json.dumps(counts),flush=True)

if __name__=="__main__":
    tmp,session,inputs,results=sys.argv[1:]
    execute(pathlib.Path(tmp),session,pathlib.Path(inputs),pathlib.Path(results))
