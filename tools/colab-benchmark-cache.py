import os,json,time,tempfile,pathlib,hashlib,uuid,requests,shutil,subprocess,re,threading
TAG="b12343"
REPO="IndexTeam/Index-Translate-9B-GGUF"
MODEL="Index-Translate-9B.Q6_K.gguf"
manifest_path=cache/"manifest.json"
def hash_file(p):
    with p.open("rb") as f: return hashlib.file_digest(f,"sha256").hexdigest()
def verified_manifest():
    copy_asset(CONFIG,"manifest.json",manifest_path)
    assert hash_file(manifest_path)==MANIFEST_SHA,"CACHE_MANIFEST_HASH_MISMATCH"
    d=json.loads(manifest_path.read_text())
    assert d["schema"]==2 and d["repo"]==REPO and d["engine"]==TAG
    assert len(d["files"])==3 and {x["kind"] for x in d["files"]}=={"model","llama","cudart"}
    for x in d["files"]:
        assert pathlib.PurePath(x["name"]).name==x["name"] and x["name"] not in (".","..")
        assert len(x["sha256"])==64
        if x["kind"]=="model":
            assert x["name"]==MODEL and x["size"]>7_000_000_000
    return d

def copy_asset(config,name,local_path,entry=None):
    """Copy with short-lived credentials; never use a failed or incomplete local model."""
    copy_start=time.monotonic()
    kind=entry["kind"] if entry else "manifest"
    print("CACHE_COPY_START="+kind,flush=True)
    complete=False
    try:
        try:
            args=[RCLONE,"--config",config,"copyto",REMOTE+"/"+name,str(local_path),
                "--contimeout","30s","--timeout","120s","--retries","1","--low-level-retries","1",
                "--stats","5s","--stats-one-line","--stats-log-level","NOTICE"]
            messages=[]
            with subprocess.Popen(args,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,text=True,errors="replace") as copy:
                def copy_logs():
                    for line in copy.stderr:
                        messages.append(line)
                        # Extract only the percentage, never raw remote paths.
                        match=re.search(r"Transferred:.*?,\s*(\d{1,3})%",line)
                        if match and 0<=int(match[1])<=100:
                            print(f"CACHE_COPY_PERCENT={kind}:{int(match[1])}",flush=True)
                thread=threading.Thread(target=copy_logs,daemon=True)
                thread.start()
                try: code=copy.wait(timeout=900)
                finally:
                    if copy.poll() is None: copy.kill();copy.wait()
                    thread.join(timeout=5)
            result=type("CopyResult",(),{"returncode":code,"stderr":"".join(messages).encode()})()
        except subprocess.TimeoutExpired:
            raise RuntimeError("LOCAL_MODEL_COPY_TIMEOUT") from None
        if result.returncode:
            msg=result.stderr.decode(errors="replace").lower()
            if re.search(r"\b401\b|invalid_grant|invalid_token|invalid credentials|unauthenticated|token (?:has )?expired|expired (?:access )?token|(?:no|missing|empty) refresh token|refresh token (?:is )?(?:missing|empty)",msg):
                raise RuntimeError("LOCAL_MODEL_COPY_AUTH_FAILED")
            if re.search(r"\b403\b|permission denied|insufficientpermissions|invalid_scope",msg):
                raise RuntimeError("LOCAL_MODEL_COPY_ACCESS_DENIED")
            if re.search(r"\b429\b|rate limit|quota",msg): raise RuntimeError("LOCAL_MODEL_COPY_QUOTA")
            raise RuntimeError("LOCAL_MODEL_COPY_FAILED")
        copy_seconds=time.monotonic()-copy_start
        verify_start=time.monotonic()
        if entry and (not local_path.is_file() or local_path.stat().st_size!=entry["size"] or hash_file(local_path)!=entry["sha256"]):
            raise RuntimeError("LOCAL_MODEL_HASH_MISMATCH")
        complete=True
        print("CACHE_COPY_DONE="+kind,flush=True)
        return copy_seconds,time.monotonic()-verify_start
    finally:
        if not complete:
            local_path.unlink(missing_ok=True)
