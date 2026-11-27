"""Prepare a verified read-only model plan; never download or upload the model."""
import configparser,json,os,pathlib,re,subprocess,sys
import requests
from importlib.machinery import SourceFileLoader
from importlib.util import spec_from_loader,module_from_spec
loader=SourceFileLoader("cache_tools",str(pathlib.Path(__file__).with_name("colab-cache-populate.py")))
spec=spec_from_loader(loader.name,loader)
cache=module_from_spec(spec)
loader.exec_module(cache)
cache.REMOTE="rocache:RO-Survivors-Korean-cache/index-translate-9b-q6k-b12343-v1"
def main():
    rev,entries=cache.metadata()
    files=cache.listing()
    for e,url in entries:
        assert e.get("sha256") and len(e["sha256"])==64,"UPSTREAM_DIGEST_REQUIRED"
        if e["kind"]=="cudart":
            e["url"]=url
            continue
        f=files.get(e["name"])
        assert f and f.get("Size")==e["size"],"ORIGINAL_CACHE_NOT_VISIBLE"
        h=cache.hashes(f)
        # rclone's older Drive backend may expose only MD5. Read SHA256 metadata directly.
        c=configparser.ConfigParser(interpolation=None)
        c.read(cache.conf)
        token=json.loads(c["rocache"]["token"])["access_token"]
        assert f.get("ID"),"ORIGINAL_CACHE_ID_MISSING"
        response=requests.get("https://www.googleapis.com/drive/v3/files/"+f["ID"],headers={"Authorization":"Bearer "+token},params={"fields":"size,sha256Checksum,md5Checksum"},timeout=30)
        if not response.ok:
            print("ORIGINAL_CACHE_METADATA_HTTP",response.status_code,flush=True)
            raise RuntimeError("ORIGINAL_CACHE_METADATA_FAILED")
        d=response.json()
        assert int(d["size"])==e["size"] and d.get("sha256Checksum")==e["sha256"],"ORIGINAL_CACHE_HASH_MISMATCH"
        print("ORIGINAL_CACHE_VERIFIED",e["kind"],e["size"],flush=True)
    d={"schema":2,"repo":cache.REPO,"revision":rev,"engine":cache.TAG,"files":[e for e,_ in entries]}
    (cache.tmp/"model-plan.json").write_text(json.dumps(d))
    print("ORIGINAL_CACHE_PLAN_READY",flush=True)
if __name__=="__main__":
    try: main()
    except Exception as e:
        msg=str(e)
        if not (msg.startswith("ORIGINAL_CACHE_") or msg.startswith("RCLONE_FAILED:") or msg=="UPSTREAM_DIGEST_REQUIRED"): msg="other"
        print("ORIGINAL_CACHE_ERROR:"+type(e).__name__+":"+msg,flush=True)
        sys.exit(1)
