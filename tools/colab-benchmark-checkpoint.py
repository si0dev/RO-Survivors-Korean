"""Private immutable checkpoints; no model, references, or credentials stored."""
import hashlib,importlib.util,json,pathlib,re,subprocess,sys
ROOT=pathlib.Path(__file__).resolve().parent
CACHE="rocache:RO-Survivors-Korean-cache-v2/index-translate-9b-q6k-b12343-v1"
STORE=CACHE+"/benchmark-checkpoints-v1"
SCRIPTS=("colab-cache-mount.py","colab-benchmark-cache.py","colab-benchmark-model.py","colab-benchmark-translate.py")
CHECKS={"hangul","placeholders","numbers","abbreviations","terms","format"}
def canonical(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode("utf-8")
def digest(data):
    return hashlib.sha256(data).hexdigest()
def fingerprint(inputs,refs,manifest,scripts):
    assets=sorted([{k:f[k] for k in ("kind","name","size","sha256")} for f in manifest["files"]],key=lambda f:f["kind"])
    return digest(canonical({"schema":1,"inputs":inputs,"references":refs,"assets":assets,
        "engine":manifest["engine"],"repo":manifest["repo"],"scripts":scripts}))
def validate_rows(rows,ids):
    if not isinstance(rows,list) or len(rows)>len(ids):
        raise ValueError("CHECKPOINT_ROW_COUNT")
    out={}
    for row in rows:
        if not isinstance(row,dict) or set(row)!={"id","ko","checks","attempts"}:
            raise ValueError("CHECKPOINT_ROW_SCHEMA")
        i=row["id"]
        if not isinstance(i,str) or i not in ids or i in out:
            raise ValueError("CHECKPOINT_ROW_ID")
        if not isinstance(row["ko"],str) or type(row["attempts"]) is not int or not 1<=row["attempts"]<=3:
            raise ValueError("CHECKPOINT_ROW_VALUE")
        if not isinstance(row["checks"],dict) or set(row["checks"])!=CHECKS or any(type(v) is not bool for v in row["checks"].values()):
            raise ValueError("CHECKPOINT_ROW_CHECKS")
        out[i]=row
    return out
def rows_from_log(data,ids):
    rows=[]
    for line in data.splitlines(keepends=True):
        if line.startswith(b"BENCHMARK_RESULT=") and line.endswith(b"\n"):
            rows.append(json.loads(line.removeprefix(b"BENCHMARK_RESULT=")))
    return validate_rows(rows,ids)
def encode(key,rows):
    return canonical({"schema":1,"fingerprint":key,"rows":list(rows.values())})
def decode(data,key,ids):
    obj=json.loads(data)
    if set(obj)!={"schema","fingerprint","rows"} or obj["schema"]!=1 or obj["fingerprint"]!=key:
        raise ValueError("CHECKPOINT_FINGERPRINT")
    return validate_rows(obj["rows"],ids)

class Store:
    def __init__(self,config,key,ids,local,run=None):
        self.key,self.ids,self.local=key,ids,pathlib.Path(local)
        self.remote=STORE+"/"+key
        self.config=config
        self.run=run or self.rclone
    def rclone(self,*args):
        try:
            p=subprocess.run(["rclone","--config",str(self.config),"--contimeout","15s","--timeout","30s",
                "--retries","2","--low-level-retries","2",*args],capture_output=True,timeout=90)
        except subprocess.TimeoutExpired:
            raise RuntimeError("CHECKPOINT_DRIVE_TIMEOUT") from None
        if p.returncode:
            raise RuntimeError("CHECKPOINT_DRIVE_IO") from None
        return p.stdout
    def restore(self):
        self.run("mkdir",self.remote)
        listing=json.loads(self.run("lsjson",self.remote,"--files-only"))
        files={}
        for f in listing:
            name=f["Name"]
            m=re.fullmatch(r"(\d{3})-([0-9a-f]{64})\.json",name)
            if not m: continue
            count=int(m[1])
            if name in files or not 1<=count<=len(self.ids):
                raise RuntimeError("CHECKPOINT_DUPLICATE_OR_COUNT")
            files[name]=(count,m[2])
        for count in sorted({v[0] for v in files.values()},reverse=True):
            valid=[]
            for name,(n,sha) in files.items():
                if n!=count: continue
                raw=self.run("cat",self.remote+"/"+name)
                try:
                    if digest(raw)!=sha: raise ValueError("CHECKPOINT_DIGEST")
                    rows=decode(raw,self.key,self.ids)
                    if len(rows)!=count: raise ValueError("CHECKPOINT_COUNT")
                except (ValueError,TypeError,KeyError):
                    print("CHECKPOINT_INVALID_SNAPSHOT",count,flush=True)
                    continue
                valid.append(rows)
            if len(valid)>1: raise RuntimeError("CHECKPOINT_CONFLICT")
            if valid: return valid[0]
        if files: raise RuntimeError("CHECKPOINT_NO_VERIFIED_SNAPSHOT")
        return {}
    def save(self,rows):
        data=encode(self.key,rows)
        name=f"{len(rows):03d}-{digest(data)}.json"
        self.local.write_bytes(data)
        self.run("copyto",str(self.local),self.remote+"/"+name,"--checksum")
        if self.run("cat",self.remote+"/"+name)!=data:
            raise RuntimeError("CHECKPOINT_WRITE_VERIFICATION")
        print("CHECKPOINT_SAVED",len(rows),flush=True)

def advance(store,saved,data):
    rows=rows_from_log(data,store.ids)
    if any(i in rows and rows[i]!=r for i,r in saved.items()):
        raise RuntimeError("CHECKPOINT_RESULT_CONFLICT")
    if not set(saved)<=set(rows):
        return saved
    if len(rows)>len(saved):
        store.save(rows)
        return rows
    return saved

def main():
    mode,config,bench,tmp,*args=sys.argv[1:]
    bench,tmp=pathlib.Path(bench),pathlib.Path(tmp)
    inputs=json.loads((bench/"inputs.json").read_text())
    ids={r["id"] for r in inputs}
    if len(inputs)!=200 or len(ids)!=200: raise RuntimeError("CHECKPOINT_INPUTS")
    if mode=="prepare":
        store=Store(config,"",ids,tmp/"checkpoint-upload.json")
        manifest=json.loads(store.run("cat",CACHE+"/manifest.json"))
        refs=json.loads((bench/"references.json").read_text())
        key=fingerprint(inputs,refs,manifest,{name:digest((ROOT/name).read_bytes()) for name in SCRIPTS})
        store=Store(config,key,ids,tmp/"checkpoint-upload.json")
        rows=store.restore()
        (tmp/"checkpoint-key").write_text(key)
        (tmp/"resume.json").write_bytes(canonical(list(rows.values())))
        print("CHECKPOINT_RESTORED",len(rows),flush=True)
        if len(rows)==200:
            (tmp/"translation.log").write_text("".join("BENCHMARK_RESULT="+json.dumps(r,ensure_ascii=False)+"\n" for r in rows.values())+"BENCHMARK_DONE\n",encoding="utf-8")
            (tmp/"checkpoint-complete").touch()
        return 0
    if mode!="collect": raise RuntimeError("CHECKPOINT_MODE")
    session,run_id,attempt=args
    if not run_id.isdigit() or not attempt.isdigit(): raise RuntimeError("CHECKPOINT_RUN_ID")
    key=(tmp/"checkpoint-key").read_text()
    if not re.fullmatch(r"[0-9a-f]{64}",key): raise RuntimeError("CHECKPOINT_KEY")
    saved=validate_rows(json.loads((tmp/"resume.json").read_text()),ids)
    store=Store(config,key,ids,tmp/"checkpoint-upload.json")
    spec=importlib.util.spec_from_file_location("kernel",ROOT/"colab-benchmark-kernel.py")
    kernel=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(kernel)
    return kernel.collect(["colab","--auth=adc","--config",str(tmp/"sessions.json")],
        session,(tmp/"benchmark.py").read_text(),tmp/"translation.log",inputs,saved,store,validate_rows)

if __name__=="__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError,ValueError,KeyError,TypeError,OSError) as exc:
        msg=str(exc)
        print(msg if re.fullmatch(r"CHECKPOINT_[A-Z_]+",msg) else "CHECKPOINT_ERROR_"+type(exc).__name__,flush=True)
        raise SystemExit(1) from None
