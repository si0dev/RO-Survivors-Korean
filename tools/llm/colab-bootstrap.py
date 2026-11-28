"""Publish pinned public rclone archive; pass verified Drive ID."""
import hashlib,json,pathlib,re,subprocess,sys
tmp,assets=map(pathlib.Path,sys.argv[1:])
name="rclone-v1.70.3-linux-amd64.zip"
archive=assets/name
sums=(assets/"SHA256SUMS").read_text()
matches=[m.group(1) for line in sums.splitlines() if (m:=re.fullmatch(r"([a-f0-9]{64})\s+\*?"+re.escape(name),line))]
assert len(matches)==1,"RCLONE_CHECKSUM_MISSING"
with archive.open("rb") as f: assert hashlib.file_digest(f,"sha256").hexdigest()==matches[0],"RCLONE_HASH_MISMATCH"
import runpy
spec=runpy.run_path(str(pathlib.Path(__file__).with_name("colab_cache_layout.py")))["selected"]()
remote=spec["model_remote"]
def run(*args):
    p=subprocess.run(["rclone","--config",str(tmp/"drive.conf"),*args],capture_output=True,timeout=180)
    if p.returncode: raise RuntimeError("RCLONE_BOOTSTRAP_DRIVE_IO")
    return p.stdout
dest=spec["bootstrap_remote"]+"/"+name
shared=tmp/"rclone-bootstrap-verified.json"
if shared.exists():
    prior=json.loads(shared.read_text())
    assert prior["sha256"]==matches[0] and prior["dest"]==dest
    entry=prior["entry"]
else:
    run("copyto",str(archive),dest,"--checksum")
    entry=json.loads(run("lsjson",dest,"--stat","--hash"))
    assert entry["Size"]==archive.stat().st_size and re.fullmatch(r"[A-Za-z0-9_-]+",entry["ID"])
    remote_md5=entry.get("Hashes",{}).get("MD5")
    if remote_md5:
        with archive.open("rb") as f: assert hashlib.file_digest(f,"md5").hexdigest()==remote_md5,"RCLONE_REMOTE_HASH_MISMATCH"
    shared.write_text(json.dumps({"sha256":matches[0],"dest":dest,"entry":entry}))
manifest=run("cat",remote+"/manifest.json")
(tmp/"bootstrap.json").write_text(json.dumps({"RCLONE_DRIVE_ID":entry["ID"],"RCLONE_ZIP_SHA":matches[0],"MANIFEST_SHA":hashlib.sha256(manifest).hexdigest(),"CACHE_SPEC":spec}))
print("RCLONE_BOOTSTRAP_CACHE_READY",flush=True)
