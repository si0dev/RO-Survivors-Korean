import os,json,time,tempfile,pathlib,hashlib,uuid,requests,shutil
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
