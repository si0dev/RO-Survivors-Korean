import os,json,time,tempfile,pathlib,hashlib,uuid,requests,shutil
TAG="b12343"
REPO="IndexTeam/Index-Translate-9B-GGUF"
MODEL="Index-Translate-9B.Q6_K.gguf"
mount=pathlib.Path("/content/drive")
assert os.path.ismount(mount),"DRIVE_NOT_MOUNTED"
drive=next((p for p in [mount/"MyDrive",mount/"My Drive"] if p.is_dir()),None)
assert drive is not None,"MY_DRIVE_NOT_FOUND"
cache=drive/"RO-Survivors-Korean-cache"/"index-translate-9b-q6k-b12343-v1"
manifest_path=cache/"manifest.json"
def hash_file(p):
    with p.open("rb") as f: return hashlib.file_digest(f,"sha256").hexdigest()
def verified_manifest():
    if not manifest_path.is_file(): return None
    d=json.loads(manifest_path.read_text())
    assert d["schema"]==1 and d["repo"]==REPO and d["engine"]==TAG
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
def fetch_verified(url,entry):
    with tempfile.TemporaryDirectory(prefix="ro-cache-") as tmp:
        local=pathlib.Path(tmp)/entry["name"]
        h=hashlib.sha256()
        with requests.get(url,stream=True,timeout=(30,180)) as r:
            r.raise_for_status()
            with local.open("wb") as f:
                for chunk in r.iter_content(4*1024*1024):
                    if chunk: f.write(chunk);h.update(chunk)
        assert local.stat().st_size==entry["size"],"DOWNLOAD_SIZE_MISMATCH"
        if entry.get("sha256"): assert h.hexdigest()==entry["sha256"],"DOWNLOAD_HASH_MISMATCH"
        entry["sha256"]=h.hexdigest()
        pending=cache/(entry["name"]+"."+uuid.uuid4().hex+".part")
        try:
            with local.open("rb") as src,pending.open("wb") as dst:
                shutil.copyfileobj(src,dst,4*1024*1024)
                dst.flush();os.fsync(dst.fileno())
            assert pending.stat().st_size==entry["size"]
            os.replace(pending,cache/entry["name"])
        finally: pending.unlink(missing_ok=True)
    print("CACHE_FILE_SAVED "+entry["kind"]+" "+str(entry["size"]),flush=True)
def populate():
    t=time.monotonic()
    cache.mkdir(parents=True,exist_ok=True)
    d=verified_manifest()
    mode="hit" if d else "created"
    if not d:
        r=requests.get("https://huggingface.co/api/models/"+REPO,params={"blobs":"true"},timeout=60)
        r.raise_for_status();meta=r.json();revision=meta["sha"]
        lfs=next(x["lfs"] for x in meta["siblings"] if x["rfilename"]==MODEL)
        entries=[({"kind":"model","name":MODEL,"size":lfs["size"],"sha256":lfs["sha256"]},"https://huggingface.co/"+REPO+"/resolve/"+revision+"/"+MODEL)]
        r=requests.get("https://api.github.com/repos/ggml-org/llama.cpp/releases/tags/"+TAG,timeout=60)
        r.raise_for_status()
        for kind,prefix in (("llama","llama-"),("cudart","cudart-")):
            matches=[x for x in r.json()["assets"] if x["name"].startswith(prefix) and "ubuntu-cuda-12" in x["name"] and "x64" in x["name"] and x["name"].endswith((".tar.gz",".tar.xz"))]
            assert len(matches)==1,"ENGINE_ASSET_UNAVAILABLE"
            x=matches[0];digest=x.get("digest") or ""
            entries.append(({"kind":kind,"name":x["name"],"size":x["size"],"sha256":digest.removeprefix("sha256:") if digest.startswith("sha256:") else None},x["browser_download_url"]))
        for entry,url in entries: fetch_verified(url,entry)
        d={"schema":1,"repo":REPO,"revision":revision,"engine":TAG,"files":[x for x,_ in entries]}
        pending=cache/("manifest."+uuid.uuid4().hex+".part")
        with pending.open("w") as f:
            json.dump(d,f);f.flush();os.fsync(f.fileno())
        os.replace(pending,manifest_path)
        assert verified_manifest()
    print("CACHE_PREPARED="+json.dumps({"mode":mode,"bytes":sum(x["size"] for x in d["files"]),"seconds":round(time.monotonic()-t,1)}),flush=True)
