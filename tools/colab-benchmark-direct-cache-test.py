"""Exercise actual pinned rclone locally, without credentials or GPU."""
import hashlib,pathlib,runpy,shutil,subprocess,tempfile,zipfile
root=pathlib.Path(__file__).resolve().parent
with tempfile.TemporaryDirectory() as td:
    tmp=pathlib.Path(td)
    archive=pathlib.Path.home()/".cache/ro-llm/rclone/rclone-v1.70.3-linux-amd64.zip"
    binary=tmp/"rclone"
    with zipfile.ZipFile(archive) as z:
        with z.open("rclone-v1.70.3-linux-amd64/rclone") as src,binary.open("wb") as dst:
            shutil.copyfileobj(src,dst)
    binary.chmod(0o700)
    assert subprocess.check_output([str(binary),"version"],text=True).splitlines()[0]=="rclone v1.70.3"
    src=tmp/"src";src.mkdir()
    cache=tmp/"cache";cache.mkdir()
    config=tmp/"empty.conf";config.touch()
    payload=b"verified local fixture"
    (src/"fixture.bin").write_bytes(payload)
    ns=runpy.run_path(str(root/"colab-benchmark-cache.py"),init_globals={"cache":cache,"REMOTE":str(src),"RCLONE":str(binary)})
    entry={"kind":"llama","size":len(payload),"sha256":hashlib.sha256(payload).hexdigest()}
    ns["copy_asset"](str(config),"fixture.bin",cache/"verified.bin",entry)
    assert (cache/"verified.bin").read_bytes()==payload
    try:
        ns["copy_asset"](str(config),"fixture.bin",cache/"corrupt.bin",dict(entry,sha256="0"*64))
    except RuntimeError as e:
        assert str(e)=="LOCAL_MODEL_HASH_MISMATCH"
    else: raise AssertionError("hash failure not detected")
    assert not (cache/"corrupt.bin").exists()
print("DIRECT_CACHE_SMOKE_PASS",flush=True)
