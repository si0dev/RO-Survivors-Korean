import os,json,time,tempfile,pathlib,hashlib,uuid,requests,shutil,subprocess,re
TAG="b12343"
REPO="IndexTeam/Index-Translate-9B-GGUF"
MODEL="Index-Translate-9B.Q6_K.gguf"
cache=MOUNT
assert os.path.ismount(cache),"DRIVE_NOT_MOUNTED"
manifest_path=cache/"manifest.json"
def hash_file(p):
    with p.open("rb") as f: return hashlib.file_digest(f,"sha256").hexdigest()
def verified_manifest():
    if not manifest_path.is_file(): return None
    d=json.loads(manifest_path.read_text())
    assert d["schema"]==2 and d["repo"]==REPO and d["engine"]==TAG
    assert len(d["files"])==3 and {x["kind"] for x in d["files"]}=={"model","llama","cudart"}
    for x in d["files"]:
        assert pathlib.PurePath(x["name"]).name==x["name"] and x["name"] not in (".","..")
        p=cache/x["name"]
        assert p.is_file() and p.stat().st_size==x["size"],"CACHE_SIZE_MISMATCH"
        assert len(x["sha256"])==64
        if x["kind"]=="model":
            assert x["name"]==MODEL and x["size"]>7_000_000_000
            with p.open("rb") as f: assert f.read(4)==b"GGUF"
    return d

def copy_verified_model(config,local_path,entry):
    """Copy with short-lived credentials; never use a failed or incomplete local model."""
    copy_start=time.monotonic()
    print("LOCAL_MODEL_COPY_START",flush=True)
    complete=False
    try:
        try:
            result=subprocess.run(["rclone","--config",config,"copyto",
                "rocache:RO-Survivors-Korean-cache-v2/index-translate-9b-q6k-b12343-v1/"+MODEL,
                str(local_path),"--contimeout","30s","--timeout","120s",
                "--retries","1","--low-level-retries","1"],capture_output=True,timeout=900)
        except subprocess.TimeoutExpired:
            raise RuntimeError("LOCAL_MODEL_COPY_TIMEOUT") from None
        if result.returncode:
            msg=result.stderr.decode(errors="replace").lower()
            if re.search(r"\b401\b|invalid_grant|invalid_token|invalid credentials|unauthenticated|token (?:has )?expired|expired (?:access )?token|(?:no|missing|empty) refresh token|refresh token (?:is )?(?:missing|empty)",msg):
                raise RuntimeError("LOCAL_MODEL_COPY_AUTH_FAILED")
            if re.search(r"\b403\b|permission denied|insufficientpermissions|invalid_scope",msg):
                raise RuntimeError("LOCAL_MODEL_COPY_ACCESS_DENIED")
            raise RuntimeError("LOCAL_MODEL_COPY_FAILED")
        copy_seconds=time.monotonic()-copy_start
        verify_start=time.monotonic()
        if not local_path.is_file() or local_path.stat().st_size!=entry["size"] or hash_file(local_path)!=entry["sha256"]:
            raise RuntimeError("LOCAL_MODEL_HASH_MISMATCH")
        complete=True
        return copy_seconds,time.monotonic()-verify_start
    finally:
        if not complete:
            local_path.unlink(missing_ok=True)
