# Executed inside the allocated Colab runtime after the verified rclone bootstrap.
# Do not load a model into GPU memory here.
shared=pathlib.Path(REVIEW_SHARED_ROOT)
manifests=[]
try:
    # Validate each manifest before committing disk space or copying assets.
    for name,bootstrap in BOOTSTRAPS:
        assert bootstrap["RCLONE_DRIVE_ID"]==RCLONE_DRIVE_ID
        assert bootstrap["RCLONE_ZIP_SHA"]==RCLONE_ZIP_SHA
        CACHE_SPEC=bootstrap["CACHE_SPEC"]
        REMOTE=CACHE_SPEC["model_remote"]
        MANIFEST_SHA=bootstrap["MANIFEST_SHA"]
        exec(CACHE_CODE,globals())
        d=verified_manifest()
        manifests.append((name,bootstrap,d,manifest_path.read_bytes()))
    engine_root=shared/"engine"
    engine_entries=[e for e in manifests[0][2]["files"] if e["kind"]!="model"]
    def proof(entries):
        return [{k:e[k] for k in ("name","size","sha256")} for e in sorted(entries,key=lambda e:e["kind"])]
    engine_proof=proof(engine_entries)
    for _,_,d,_ in manifests:
        assert proof([e for e in d["files"] if e["kind"]!="model"])==engine_proof,"SHARED_ENGINE_MANIFEST_MISMATCH"
    model_bytes=sum(next(e["size"] for e in d["files"] if e["kind"]=="model") for _,_,d,_ in manifests)
    required=model_bytes+3*sum(e["size"] for e in engine_entries)+2*1024**3
    free=shutil.disk_usage(shared).free
    print("PREFETCH_DISK_FREE_BYTES="+str(free),flush=True)
    print("PREFETCH_DISK_REQUIRED_BYTES="+str(required),flush=True)
    if free<required: raise RuntimeError("LOCAL_DISK_SPACE_INSUFFICIENT")
    if engine_root.exists(): raise RuntimeError("PREFETCH_ENGINE_ALREADY_EXISTS")
    engine_root.mkdir(mode=0o700)
    for entry in engine_entries:
        archive=cache/entry["name"]
        copy_asset(CONFIG,entry["name"],archive,entry)
        with tarfile.open(archive,"r:*") as tf: tf.extractall(engine_root,filter="data")
        archive.unlink()
    (engine_root/"verified-engine.json").write_text(json.dumps(engine_proof))
    for name,bootstrap,d,raw in manifests:
        print("PREFETCH_MODEL_START="+name,flush=True)
        CACHE_SPEC=bootstrap["CACHE_SPEC"]
        REMOTE=CACHE_SPEC["model_remote"]
        MANIFEST_SHA=bootstrap["MANIFEST_SHA"]
        exec(CACHE_CODE,globals())
        model_dir=shared/"models"/CACHE_SPEC["slug"]/CACHE_SPEC["quant"]
        model_dir.mkdir(mode=0o700,parents=True,exist_ok=False)
        entry=next(e for e in d["files"] if e["kind"]=="model")
        model_path=model_dir/entry["name"]
        seconds,verification=copy_asset(CONFIG,entry["name"],model_path,entry)
        with model_path.open("rb") as f: assert f.read(4)==b"GGUF","LOCAL_MODEL_HASH_MISMATCH"
        (model_dir/"manifest.json").write_bytes(raw)
        (model_dir/"verified-model.json").write_text(json.dumps({"sha256":entry["sha256"],"size":entry["size"],"mtime_ns":model_path.stat().st_mtime_ns}))
        print("LOCAL_MODEL_COPY="+json.dumps({"bytes":entry["size"],"copy_seconds":round(seconds,1),"verify_seconds":round(verification,1)}),flush=True)
        print("PREFETCH_MODEL_READY="+name,flush=True)
finally:
    pathlib.Path(CONFIG).unlink(missing_ok=True)
    shutil.rmtree(cache,ignore_errors=True)
print(DONE_MARKER,flush=True)
