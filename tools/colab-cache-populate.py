"""Populate a private Drive cache via rclone; refresh credentials only on Actions."""
import hashlib,json,os,pathlib,subprocess,time,requests,traceback,re
TAG="b12343"
REPO="IndexTeam/Index-Translate-9B-GGUF"
MODEL="Index-Translate-9B.Q6_K.gguf"
REMOTE="rocache:RO-Survivors-Korean-cache-v2/index-translate-9b-q6k-b12343-v1"
tmp=pathlib.Path(os.environ["RO_CACHE_TMP"])
conf=tmp/"drive.conf"
def rc(*args,limit=120):
    try:
        p=subprocess.run(["rclone","--config",str(conf),"--contimeout","30s","--timeout","60s","--retries","1","--low-level-retries","3",*args],capture_output=True,timeout=limit)
    except subprocess.TimeoutExpired:
        raise RuntimeError("RCLONE_FAILED:timeout") from None
    if p.returncode:
        msg=p.stderr.decode(errors="replace").lower()
        category=next((x for x in ("invalid_grant","invalid_scope","storagequotaexceeded","userratelimitexceeded","ratelimitexceeded","quota","403","401","429","503","timeout","no space") if x in msg),"other")
        raise RuntimeError("RCLONE_FAILED:"+category)
    return p.stdout
def metadata():
    r=requests.get("https://huggingface.co/api/models/"+REPO,params={"blobs":"true"},timeout=60)
    r.raise_for_status();m=r.json();rev=m["sha"]
    lfs=next(x["lfs"] for x in m["siblings"] if x["rfilename"]==MODEL)
    entries=[({"kind":"model","name":MODEL,"size":lfs["size"],"sha256":lfs["sha256"]},"https://huggingface.co/"+REPO+"/resolve/"+rev+"/"+MODEL)]
    r=requests.get("https://api.github.com/repos/ggml-org/llama.cpp/releases/tags/"+TAG,timeout=60)
    r.raise_for_status();assets=r.json()["assets"]
    for kind,prefix in (("llama","llama-"),("cudart","cudart-")):
        matches=[x for x in assets if x["name"].startswith(prefix) and "ubuntu-cuda-12" in x["name"] and "x64" in x["name"] and x["name"].endswith((".tar.gz",".tar.xz"))]
        assert len(matches)==1,"ENGINE_ASSET_UNAVAILABLE"
        x=matches[0];digest=x.get("digest") or ""
        entries.append(({"kind":kind,"name":x["name"],"size":x["size"],"sha256":digest.removeprefix("sha256:") if digest.startswith("sha256:") else None},x["browser_download_url"]))
    return rev,entries
def listing():
    rows=json.loads(rc("lsjson",REMOTE,"--files-only","--hash"))
    files={}
    for row in rows:
        name=row["Name"]
        if name in files: raise RuntimeError("CACHE_DUPLICATE_NAME")
        files[name]=row
    return files
def hashes(row):
    return {re.sub(r"[^a-z0-9]","",k.lower()):v.lower() for k,v in (row.get("Hashes") or {}).items() if isinstance(v,str) and v}
def file_info(name,size):
    for _ in range(6):
        f=listing().get(name)
        if f and f.get("Size")==size: return f
        time.sleep(2)
    return f
def remote_digest(name):
    # One-time recovery when the prior upload succeeded but its manifest was lost.
    # Read the existing Drive file as a stream, never write a second local copy.
    sha=hashlib.sha256();md5=hashlib.md5();size=0
    with (tmp/"digest-error.log").open("wb") as err:
        proc=subprocess.Popen(["rclone","--config",str(conf),"--contimeout","30s","--timeout","180s","cat",REMOTE+"/"+name],stdout=subprocess.PIPE,stderr=err)
        try:
            while b:=proc.stdout.read(4*1024*1024):
                sha.update(b);md5.update(b);size+=len(b)
            assert proc.wait(timeout=60)==0,"REMOTE_DIGEST_READ_FAILED"
        finally:
            if proc.poll() is None: proc.kill();proc.wait()
            proc.stdout.close()
    return {"size":size,"sha256":sha.hexdigest(),"md5":md5.hexdigest()}
def verified_remote(e,f):
    if not f or f.get("Size")!=e["size"]: return False
    h=hashes(f)
    # Prefer SHA256 when supported; otherwise compare the stored MD5.
    if h.get("sha256") and e.get("sha256"): return h["sha256"]==e["sha256"]
    if h.get("md5") and e.get("md5"): return h["md5"]==e["md5"]
    return False
# Reuse a successful verification within this process only, and only for the
# same remote file identity, size and modification time.
verified_this_run={}
def identity(f):
    if not f or not f.get("ID") or not f.get("ModTime"): return None
    return (f["ID"],f["Size"],f["ModTime"])
def remember(e,f):
    key=identity(f)
    if key is not None: verified_this_run[e["name"]]=(key,e["sha256"],e["md5"])
def check_existing(e,f):
    if not f or f.get("Size")!=e["size"]: return False
    if identity(f) is not None and verified_this_run.get(e["name"])==(identity(f),e["sha256"],e["md5"]): return True
    if not verified_remote(e,f):
        h=hashes(f)
        if h.get("md5") or h.get("sha256"): return False
        actual=remote_digest(e["name"])
        if any(actual[k]!=e[k] for k in ("size","sha256","md5")): return False
    remember(e,f)
    return True
def upload_verified(p,e):
    name=e["name"]
    limit=1200 if e["kind"]=="model" else 600
    for attempt in range(1,4):
        print("CACHE_UPLOAD_ATTEMPT",e["kind"],attempt,flush=True)
        try:
            rc("copyto",str(p),REMOTE+"/"+name,"--checksum","--drive-chunk-size","32M","--tpslimit","4","--tpslimit-burst","4",limit=limit)
        except RuntimeError as exc:
            code=str(exc)
            print("CACHE_UPLOAD_RETRY",e["kind"],attempt,code,flush=True)
            # Authentication failures and confirmed quota exhaustion are not transient.
            if code in ("RCLONE_FAILED:invalid_grant","RCLONE_FAILED:invalid_scope","RCLONE_FAILED:storagequotaexceeded","RCLONE_FAILED:no space","RCLONE_FAILED:401"): raise
            # A timed-out upload can have committed successfully on the server.
            f=file_info(name,e["size"])
            if check_existing(e,f): return
            if attempt==3: raise
            time.sleep(15*attempt)
            continue
        f=file_info(name,e["size"])
        if check_existing(e,f): return
        if attempt==3: raise RuntimeError("UPLOAD_HASH_MISMATCH")
        print("CACHE_UPLOAD_RETRY",e["kind"],attempt,"verification",flush=True)
        time.sleep(15*attempt)
def valid(d,files):
    if not isinstance(d,dict) or d.get("schema")!=2 or d.get("repo")!=REPO or d.get("engine")!=TAG: return False
    entries=d.get("files")
    if not isinstance(entries,list) or len(entries)!=3: return False
    if any(not isinstance(e,dict) for e in entries): return False
    if sorted(str(e.get("kind")) for e in entries)!=["cudart","llama","model"]: return False
    names=set()
    for e in entries:
        name=e.get("name")
        if not isinstance(name,str) or not name or pathlib.PurePath(name).name!=name or name in (".","..") or name in names: return False
        names.add(name)
        if type(e.get("size")) is not int or e["size"]<=0: return False
        if not isinstance(e.get("sha256"),str) or not re.fullmatch(r"[a-f0-9]{64}",e["sha256"]): return False
        if not isinstance(e.get("md5"),str) or not re.fullmatch(r"[a-f0-9]{32}",e["md5"]): return False
        if e["kind"]=="model" and (name!=MODEL or e["size"]<7_000_000_000): return False
    return all(check_existing(e,files.get(e["name"])) for e in entries)
def main():
    t=time.monotonic()
    print("CACHE_STAGE: listing",flush=True)
    rc("mkdir",REMOTE)
    files=listing()
    mode="created"
    if "manifest.json" in files:
        print("CACHE_STAGE: verify_manifest",flush=True)
        raw=rc("cat",REMOTE+"/manifest.json")
        try:
            d=json.loads(raw)
        except (ValueError, UnicodeError):
            d=None
        if valid(d,files):
            mode="hit"
        else:
            mode="repaired"
            print("CACHE_STAGE: repair_invalid_manifest",flush=True)
    if mode!="hit":
        print("CACHE_STAGE: source_metadata",flush=True)
        revision,entries=metadata()
        for e,url in entries:
            print("CACHE_STAGE: "+e["kind"]+"_recover",flush=True)
            f=files.get(e["name"])
            if f and f.get("Size")==e["size"] and e.get("sha256"):
                # Validate against the upstream SHA256, not merely the file name or size.
                h=hashes(f)
                if h.get("sha256")==e["sha256"] and re.fullmatch(r"[a-f0-9]{32}",h.get("md5","")):
                    e["md5"]=h["md5"]
                    remember(e,f)
                    print("CACHE_FILE_REUSED",e["kind"],e["size"],flush=True)
                    continue
                # A known mismatching SHA256 already proves corruption; do not stream it again.
                actual=remote_digest(e["name"]) if not h.get("sha256") or h["sha256"]==e["sha256"] else None
                if actual and actual["size"]==e["size"] and actual["sha256"]==e["sha256"]:
                    e["md5"]=actual["md5"]
                    remember(e,f)
                    print("CACHE_FILE_REUSED",e["kind"],e["size"],flush=True)
                    continue
            print("CACHE_STAGE: "+e["kind"]+"_download",flush=True)
            p=tmp/e["name"]
            sha=hashlib.sha256();md5=hashlib.md5()
            try:
                with requests.get(url,stream=True,timeout=(30,180)) as r:
                    r.raise_for_status()
                    with p.open("wb") as out:
                        for b in r.iter_content(4*1024*1024):
                            if b: out.write(b);sha.update(b);md5.update(b)
                assert p.stat().st_size==e["size"],"DOWNLOAD_SIZE_MISMATCH"
                assert not e["sha256"] or e["sha256"]==sha.hexdigest(),"DOWNLOAD_HASH_MISMATCH"
                e["sha256"]=sha.hexdigest();e["md5"]=md5.hexdigest()
                print("CACHE_STAGE: "+e["kind"]+"_upload",flush=True)
                upload_verified(p,e)
                print("CACHE_FILE_SAVED",e["kind"],e["size"],flush=True)
            finally: p.unlink(missing_ok=True)
        d={"schema":2,"repo":REPO,"revision":revision,"engine":TAG,"files":[e for e,_ in entries]}
        print("CACHE_STAGE: publish_manifest",flush=True)
        assert valid(d,listing()),"CACHE_MANIFEST_MISMATCH"
        p=tmp/"manifest.json";p.write_text(json.dumps(d))
        rc("copyto",str(p),REMOTE+"/manifest.json","--checksum")
        assert valid(json.loads(rc("cat",REMOTE+"/manifest.json")),listing()),"CACHE_MANIFEST_MISMATCH"
    print("CACHE_PREPARED="+json.dumps({"mode":mode,"bytes":sum(x["size"] for x in d["files"]),"seconds":round(time.monotonic()-t,1)}),flush=True)
if __name__=="__main__":
    try: main()
    except Exception as e:
        # Do not expose arbitrary metadata, filenames, URLs or credentials.
        safe={"CACHE_DUPLICATE_NAME","CACHE_MANIFEST_MISMATCH","ENGINE_ASSET_UNAVAILABLE","DOWNLOAD_SIZE_MISMATCH","DOWNLOAD_HASH_MISMATCH","UPLOAD_SIZE_MISMATCH","UPLOAD_HASH_MISMATCH","REMOTE_DIGEST_READ_FAILED"}
        keys={"Name","Hashes","MD5","Size","sha","siblings","lfs","sha256","size","assets","name","browser_download_url"}
        msg=str(e)
        frame=traceback.extract_tb(e.__traceback__)[-1]
        detail=msg if msg in safe or msg.startswith("RCLONE_FAILED:") else ("key="+str(e.args[0]) if isinstance(e,KeyError) and e.args and e.args[0] in keys else "other")
        print("CACHE_ERROR:"+type(e).__name__+":"+detail+":line="+str(frame.lineno),flush=True)
        raise SystemExit(1)
