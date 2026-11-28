"""One-time migration of the exact old benchmark cache; never touch other Drive files."""
import configparser, json, os, pathlib, subprocess, time, sys
import requests
from importlib.machinery import SourceFileLoader
from importlib.util import spec_from_loader,module_from_spec
def load(name,filename):
    loader=SourceFileLoader(name,str(pathlib.Path(__file__).with_name(filename)))
    spec=spec_from_loader(loader.name,loader)
    module=module_from_spec(spec)
    loader.exec_module(module)
    return module
cache=load("cache","colab-cache-populate.py")
auth=load("auth","colab-drive-auth.py")
OLD="rocache:RO-Survivors-Korean-cache/index-translate-9b-q6k-b12343-v1"
def about(conf):
    c=configparser.ConfigParser(interpolation=None)
    c.read(conf)
    token=json.loads(c["rocache"]["token"])["access_token"]
    r=requests.get("https://www.googleapis.com/drive/v3/about",headers={"Authorization":"Bearer "+token},params={"fields":"user(permissionId),storageQuota(limit,usage,usageInDrive,usageInDriveTrash)"},timeout=30)
    if not r.ok: auth.fail("storage_quota",r)
    return r.json()
def free(d):
    q=d["storageQuota"]
    return int(q["limit"])-int(q["usage"]) if q.get("limit") else None
def old_rc(conf,*args,missing_ok=False):
    r=subprocess.run(["rclone","--config",str(conf),"--contimeout","30s","--timeout","60s","--retries","2","--low-level-retries","3",*args],capture_output=True,timeout=180)
    if r.returncode==3 and missing_ok: return None
    if r.returncode:
        print("LEGACY_CACHE_RCLONE_EXIT",r.returncode,flush=True)
        raise RuntimeError("LEGACY_CACHE_ACCESS_FAILED")
    return r.stdout
def main():
    rev,entries=cache.metadata()
    # Confirm the new credential can access Drive and that source digests exist before deleting.
    assert all(e.get("sha256") and len(e["sha256"])==64 for e,_ in entries),"UPSTREAM_DIGEST_REQUIRED"
    cache.rc("mkdir",cache.REMOTE)
    cache.rc("mkdir",cache.ENGINE_REMOTE)
    current=cache.listing()
    if "manifest.json" in current:
        d=json.loads(cache.rc("cat",cache.REMOTE+"/manifest.json"))
        current=cache.promote_legacy_engine(d,current)
        if cache.valid(d,current):
            print("MIGRATION_ALREADY_COMPLETE",flush=True)
            return
        raise RuntimeError("NEW_CACHE_MANIFEST_INVALID")
    required=sum(e["size"] for e,_ in entries if not (current.get(e["name"]) and current[e["name"]].get("Size")==e["size"]))+1048576
    new=about(cache.conf)
    # Test real write access with a uniquely named small marker and remove only that marker.
    marker="migration-probe-"+os.environ["GITHUB_RUN_ID"]+"-"+os.environ["GITHUB_RUN_ATTEMPT"]+".txt"
    local=cache.tmp/marker
    local.write_bytes(b"ro-survivors-cache-migration")
    cache.rc("copyto",str(local),cache.REMOTE+"/"+marker)
    try:
        assert cache.rc("cat",cache.REMOTE+"/"+marker)==local.read_bytes(),"NEW_CACHE_WRITE_MISMATCH"
    finally:
        cache.rc("deletefile",cache.REMOTE+"/"+marker,"--drive-use-trash=false")
        local.unlink(missing_ok=True)
    print("NEW_CACHE_WRITE: PASS",flush=True)
    raw=os.environ.get("LEGACY_RCLONE_CONFIG_SECRET","")
    if raw:
        c=configparser.ConfigParser(interpolation=None)
        c.read_string(raw)
        assert c.sections()==["rocache"] and c["rocache"].get("type")=="drive" and c["rocache"].get("scope")=="drive.file","LEGACY_CONFIG_INVALID"
        token=json.loads(c["rocache"]["token"])
        assert token.get("refresh_token"),"LEGACY_REFRESH_MISSING"
        token["expiry"]="2000-01-01T00:00:00Z"
        c["rocache"]["token"]=json.dumps(token)
        conf=cache.tmp/"legacy.conf"
        with conf.open("w") as f: c.write(f)
        try:
            result=old_rc(conf,"lsjson",OLD,"--files-only",missing_ok=True)
            rows=json.loads(result) if result is not None else []
            if rows:
                previous=about(conf)
                assert previous["user"]["permissionId"]==new["user"]["permissionId"],"DRIVE_ACCOUNT_MISMATCH"
                allowed={e["name"]:e["size"] for e,_ in entries}
                selected=[r for r in rows if r["Name"] in allowed]
                assert len({r["Name"] for r in selected})==len(selected),"LEGACY_DUPLICATE_NAMES"
                assert all(r["Size"]==allowed[r["Name"]] for r in selected),"LEGACY_FILE_SIZE_MISMATCH"
                reclaim=sum(r["Size"] for r in selected)
                available=free(new)
                print("MIGRATION_CAPACITY "+json.dumps({"required_bytes":required,"free_before_bytes":available,"reclaimable_bytes":reclaim}),flush=True)
                assert available is None or available+reclaim>=required,"DRIVE_SPACE_INSUFFICIENT_AFTER_CLEANUP"
                # Exact known file paths only; permanent removal is required to reclaim quota.
                for row in selected:
                    old_rc(conf,"deletefile",OLD+"/"+row["Name"],"--drive-use-trash=false")
                    print("LEGACY_CACHE_FILE_DELETED",row["Size"],flush=True)
                remaining=old_rc(conf,"lsjson",OLD,"--files-only",missing_ok=True)
                assert not any(r["Name"] in allowed for r in (json.loads(remaining) if remaining is not None else [])),"LEGACY_DELETE_NOT_VERIFIED"
                print("LEGACY_CACHE_CLEANUP: PASS",flush=True)
            else:
                print("LEGACY_CACHE_ALREADY_EMPTY",flush=True)
        finally: conf.unlink(missing_ok=True)
    else:
        print("LEGACY_SECRET_ABSENT",flush=True)
    # Drive quota changes can lag deletion; verify capacity before downloading anything.
    for _ in range(12):
        available=free(about(cache.conf))
        if available is None or available>=required: break
        time.sleep(5)
    else: raise RuntimeError("DRIVE_SPACE_INSUFFICIENT")
    print("MIGRATION_SPACE_READY "+json.dumps({"required_bytes":required,"free_bytes":available}),flush=True)
if __name__=="__main__":
    try: main()
    except SystemExit: raise
    except Exception as e:
        msg=str(e)
        safe={"UPSTREAM_DIGEST_REQUIRED","NEW_CACHE_MANIFEST_INVALID","NEW_CACHE_WRITE_MISMATCH","LEGACY_CONFIG_INVALID","LEGACY_REFRESH_MISSING","LEGACY_CACHE_ACCESS_FAILED","DRIVE_ACCOUNT_MISMATCH","LEGACY_DUPLICATE_NAMES","LEGACY_FILE_SIZE_MISMATCH","DRIVE_SPACE_INSUFFICIENT_AFTER_CLEANUP","LEGACY_DELETE_NOT_VERIFIED","DRIVE_SPACE_INSUFFICIENT"}
        print("MIGRATION_ERROR:"+type(e).__name__+":"+(msg if msg in safe or msg.startswith("RCLONE_FAILED:") else "other"),flush=True)
        sys.exit(1)
