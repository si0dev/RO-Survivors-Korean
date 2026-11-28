"""Bootstrap pinned rclone from private Drive; no FUSE or apt."""
import os, pathlib, tempfile, subprocess, shutil, atexit, configparser, json, hashlib, zipfile, re
import requests
REMOTE=CACHE_SPEC["model_remote"]
cache=pathlib.Path(tempfile.mkdtemp(prefix="ro-drive-local-"))
atexit.register(lambda: shutil.rmtree(cache,ignore_errors=True))
atexit.register(lambda: pathlib.Path(CONFIG).unlink(missing_ok=True))
os.chmod(CONFIG,0o600)
assert re.fullmatch(r"[A-Za-z0-9_-]+",RCLONE_DRIVE_ID)
assert re.fullmatch(r"[a-f0-9]{64}",RCLONE_ZIP_SHA)
cfg=configparser.ConfigParser(interpolation=None);cfg.read(CONFIG)
token=json.loads(cfg["rocache"]["token"])["access_token"]
archive=cache/"rclone.zip"
print("RCLONE_BOOTSTRAP_START",flush=True)
try:
    with requests.get("https://www.googleapis.com/drive/v3/files/"+RCLONE_DRIVE_ID,params={"alt":"media"},headers={"Authorization":"Bearer "+token},stream=True,timeout=(15,90)) as response:
        if response.status_code!=200:
            raise RuntimeError("RCLONE_BOOTSTRAP_AUTH" if response.status_code in (401,403) else "RCLONE_BOOTSTRAP_HTTP_"+str(response.status_code))
        with archive.open("wb") as f:
            for chunk in response.iter_content(1024*1024): f.write(chunk)
except requests.RequestException:
    raise RuntimeError("RCLONE_BOOTSTRAP_CONNECTION") from None
finally:
    del token,cfg
with archive.open("rb") as f:
    assert hashlib.file_digest(f,"sha256").hexdigest()==RCLONE_ZIP_SHA,"RCLONE_BOOTSTRAP_HASH_MISMATCH"
RCLONE=str(cache/"rclone")
with zipfile.ZipFile(archive) as z:
    with z.open("rclone-v1.70.3-linux-amd64/rclone") as src,open(RCLONE,"wb") as dst:
        shutil.copyfileobj(src,dst)
os.chmod(RCLONE,0o700)
archive.unlink()
assert subprocess.check_output([RCLONE,"version"],text=True,timeout=20).splitlines()[0]=="rclone v1.70.3","RCLONE_VERSION_MISMATCH"
print("RCLONE_BOOTSTRAP_READY",flush=True)
