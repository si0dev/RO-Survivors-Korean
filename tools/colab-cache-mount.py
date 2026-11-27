import os,subprocess,time,pathlib,tempfile,shutil,atexit
MOUNT=pathlib.Path(tempfile.mkdtemp(prefix="ro-drive-mount-"))
mount_proc=None
def cleanup_mount():
    if os.path.ismount(MOUNT):
        subprocess.run(["fusermount3","-u",str(MOUNT)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    if mount_proc and mount_proc.poll() is None:
        mount_proc.terminate()
        try: mount_proc.wait(timeout=10)
        except subprocess.TimeoutExpired: mount_proc.kill()
    pathlib.Path(CONFIG).unlink(missing_ok=True)
    if not os.path.ismount(MOUNT): MOUNT.rmdir()
atexit.register(cleanup_mount)
stage="init"
try:
    os.chmod(CONFIG,0o600)
    stage="install"
    if not shutil.which("rclone") or not shutil.which("fusermount3"):
        subprocess.run(["apt-get","update","-qq"],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=120)
        subprocess.run(["apt-get","install","-y","-qq","rclone","fuse3"],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=120)
    stage="fuse_device"
    assert pathlib.Path("/dev/fuse").exists()
    stage="mount"
    mount_proc=subprocess.Popen(["rclone","--config",CONFIG,"mount","rocache:RO-Survivors-Korean-cache-v2/index-translate-9b-q6k-b12343-v1",str(MOUNT),"--read-only","--vfs-cache-mode","off"],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    for _ in range(60):
        if os.path.ismount(MOUNT): break
        assert mount_proc.poll() is None
        time.sleep(1)
    assert os.path.ismount(MOUNT) and (MOUNT/"manifest.json").is_file()
    print("RCLONE_MODEL_MOUNT_OK",flush=True)
except Exception as e:
    print("RCLONE_TEST_ERROR:"+stage+":"+type(e).__name__,flush=True)
    raise
