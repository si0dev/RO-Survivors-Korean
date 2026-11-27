"""Populate a private Drive cache via rclone; refresh credentials only on Actions."""
import configparser,datetime,hashlib,json,os,pathlib,subprocess,tempfile,time,requests
TAG="b12343"
REPO="IndexTeam/Index-Translate-9B-GGUF"
MODEL="Index-Translate-9B.Q6_K.gguf"
REMOTE="rocache:RO-Survivors-Korean-cache/index-translate-9b-q6k-b12343-v1"
tmp=pathlib.Path(os.environ["RO_CACHE_TMP"])
conf=tmp/"drive.conf"
def rc(*args):
    p=subprocess.run(["rclone","--config",str(conf),"--contimeout","30s","--timeout","180s",*args],capture_output=True,timeout=2400)
    if p.returncode:
        msg=p.stderr.decode(errors="replace").lower()
        category=next((x for x in ("invalid_grant","invalid_scope","quota","403","401","429","timeout","no space") if x in msg),"other")
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
    return {x["Name"]:x for x in json.loads(rc("lsjson",REMOTE,"--files-only","--hash"))}
def valid(d,files):
    if d.get("schema")!=2 or d.get("repo")!=REPO or d.get("engine")!=TAG: return False
    entries=d.get("files",[])
    if len(entries)!=3 or {x["kind"] for x in entries}!={"model","llama","cudart"}: return False
    for e in entries:
        f=files.get(e["name"],{})
        if pathlib.PurePath(e["name"]).name!=e["name"] or f.get("Size")!=e["size"] or f.get("Hashes",{}).get("MD5","").lower()!=e.get("md5") or len(e.get("sha256",""))!=64: return False
        if e["kind"]=="model" and (e["name"]!=MODEL or e["size"]<7_000_000_000): return False
    return True
def main():
    t=time.monotonic()
    rc("mkdir",REMOTE)
    files=listing()
    mode="created"
    if "manifest.json" in files:
        d=json.loads(rc("cat",REMOTE+"/manifest.json"))
        if not valid(d,files): raise RuntimeError("CACHE_MANIFEST_MISMATCH")
        mode="hit"
    else:
        revision,entries=metadata()
        for e,url in entries:
            # One local file at a time; never upload before checking its source digest.
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
                rc("copyto",str(p),REMOTE+"/"+e["name"],"--checksum","--drive-chunk-size","64M")
                f=listing()[e["name"]]
                assert f["Size"]==e["size"] and f["Hashes"]["MD5"].lower()==e["md5"],"UPLOAD_HASH_MISMATCH"
                print("CACHE_FILE_SAVED",e["kind"],e["size"],flush=True)
            finally: p.unlink(missing_ok=True)
        d={"schema":2,"repo":REPO,"revision":revision,"engine":TAG,"files":[e for e,_ in entries]}
        assert valid(d,listing())
        p=tmp/"manifest.json";p.write_text(json.dumps(d))
        rc("copyto",str(p),REMOTE+"/manifest.json","--checksum")
        assert valid(json.loads(rc("cat",REMOTE+"/manifest.json")),listing())
    print("CACHE_PREPARED="+json.dumps({"mode":mode,"bytes":sum(x["size"] for x in d["files"]),"seconds":round(time.monotonic()-t,1)}),flush=True)
if __name__=="__main__":
    try: main()
    except Exception as e:
        # Never dump request URLs, headers, paths or remote account information.
        safe={"CACHE_MANIFEST_MISMATCH","ENGINE_ASSET_UNAVAILABLE","DOWNLOAD_SIZE_MISMATCH","DOWNLOAD_HASH_MISMATCH","UPLOAD_HASH_MISMATCH"}
        msg=str(e)
        print("CACHE_ERROR:"+type(e).__name__+":"+(msg if msg in safe or msg.startswith("RCLONE_FAILED:") else "other"),flush=True)
        raise SystemExit(1)
