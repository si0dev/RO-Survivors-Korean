"""Read actual Index checkpoint, correct with Hy-MT3, verify with Qwen3. No fresh Index inference."""
import hashlib,importlib.util,inspect,json,os,pathlib,re,sys,uuid

ROOT=pathlib.Path(__file__).resolve().parent

def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module

def write(path,data):
    path.write_text(json.dumps(data,ensure_ascii=False),encoding="utf-8")

def read(path):
    return json.loads(path.read_text(encoding="utf-8"))

def select_drafts(inputs,rows):
    # One known regression and one fixed-duration control from the same real sample.
    selected=[]
    for i in ("189","005"):
        source=next(r for r in inputs if r["id"]==i)
        draft=rows[i]
        if not all(draft["checks"].values()) or not draft["ko"]:
            raise RuntimeError("CHAIN_DRAFT_NOT_STRUCTURALLY_VALID")
        selected.append({**source,"draft":draft["ko"]})
    if selected[0]["source"]!="+0.3 s of freeze.":
        raise RuntimeError("CHAIN_FIXTURE_CHANGED")
    return selected

def restore_logged_drafts(inputs,refs):
    fixture=read(ROOT/"colab-benchmark-chain-index-run42.json")
    if (fixture["schema"],fixture["run_id"],fixture["job_id"],fixture["head_sha"])!=(1,46094961170,140825568619,"97616b2423e1e04e13f33987a8aeac4ee4778f95"):
        raise RuntimeError("CHAIN_LOG_PROVENANCE")
    records={r["id"]:r for r in refs}
    rows={}
    for row in fixture["rows"]:
        i=row["id"]
        if i in rows or i not in records:
            raise RuntimeError("CHAIN_LOG_ID")
        if any(row[k]!=records[i][k] for k in ("source","group","context","recordId")):
            raise RuntimeError("CHAIN_LOG_SOURCE_MISMATCH")
        rows[i]=row
    if set(rows)!={"005","189"}: raise RuntimeError("CHAIN_LOG_SELECTION")
    return select_drafts(inputs,rows)

def restore(tmp,bench,historical):
    cp=load("historical_checkpoint",historical/"colab-benchmark-checkpoint.py")
    inputs=read(bench/"inputs.json");refs=read(bench/"references.json")
    ids={r["id"] for r in inputs}
    config=tmp/"drive.conf"
    reader=cp.Store(config,"",ids,tmp/"unused.json")
    manifest=json.loads(reader.run("cat",cp.CACHE+"/manifest.json"))
    scripts={name:cp.digest((historical/name).read_bytes()) for name in cp.SCRIPTS}
    key=cp.current_key(inputs,refs,manifest,scripts)
    # Only this verified checkpoint namespace, not a retranslation or arbitrary search.
    def readonly(*args):
        if args[0]=="mkdir": return b""
        if args[0] not in ("lsjson","cat"): raise RuntimeError("CHAIN_READ_ONLY")
        return reader.run(*args)
    store=cp.Store(config,key,ids,tmp/"unused.json",run=readonly)
    try:
        rows=store.restore()
        if len(rows)!=200: raise RuntimeError("CHAIN_CHECKPOINT_INCOMPLETE")
    except RuntimeError as exc:
        # The two selected drafts are also present verbatim in the actual #42
        # assessment log. Use that fixed record rather than regenerate anything.
        if str(exc) not in ("CHECKPOINT_DRIVE_IO","CHECKPOINT_DRIVE_TIMEOUT","CHAIN_CHECKPOINT_INCOMPLETE"):
            raise
        print("CHAIN_DRIVE_RESTORE_UNAVAILABLE="+str(exc),flush=True)
        selected=restore_logged_drafts(inputs,refs)
        print("CHAIN_INDEX_SOURCE=RUN42_LOG SELECTED=2 INDEX_INFERENCE=0",flush=True)
    else:
        selected=select_drafts(inputs,rows)
        print("CHAIN_INDEX_CHECKPOINT_RESTORED=200 SELECTED=2 INDEX_INFERENCE=0",flush=True)
    write(tmp/"chain-drafts.json",selected)

def correction_issues(source,text):
    from collections import Counter
    numbers=r"[+-]?\d+(?:\.\d+)?%?"
    issues=[]
    if Counter(re.findall(numbers,source))!=Counter(re.findall(numbers,text)):
        issues.append("numeric_tokens_changed")
    # Only target terse signed duration modifiers, not ordinary fixed-duration effects.
    if re.fullmatch(r"[+-]\d+(?:\.\d+)?\s*(?:s|sec|seconds?)\s+of\s+[^.!?]+[.]?",source.strip(),re.I):
        if not re.search(r"(?:지속\s*시간|시간|증가|감소|연장|단축)",text) or re.search(r"초\s*동안",text):
            issues.append("duration_modifier_rendered_as_fixed_duration")
    if re.search(r"\bhalf as long\b",source,re.I) and not re.search(r"절반|반으로|반만|반의",text):
        issues.append("relative_duration_not_preserved")
    return issues

def correct_one(row,base):
    import json,requests
    prompt=("你是英韩游戏翻译校订员。英文原文是事实依据，韩语初稿是需要校订的已有译文。"
            "保留初稿中正确的部分，仅修正错误、遗漏或术语问题；不得从头自由重译。"
            "原文的前置正负号是属性变化量，不是固定状态持续时间。"
            "属性词条必须保留属性变化的语法，不能变成施加状态的描述。"
            "例如：+2 s of poison 表示 중독 지속 시간 +2초，而不是 +2초 동안 중독됩니다。"
            "保留相对时长表达，如 half as long 应保留为 절반，不计算新的绝对秒数。"
            "必须保留全部数值、变量、单位、目标、条件、频率及否定。使用自然韩语游戏用语。"
            "若初稿准确，原样返回。只输出最终一行韩语译文，不要解释。\n")
    data={"English":row["source"],"Korean draft":row["draft"],"Context":row["context"]}
    for attempt in range(1,4):
        response=requests.post(base+"/v1/chat/completions",json={"messages":[{"role":"user","content":prompt+json.dumps(data,ensure_ascii=False)}],
            "temperature":0,"max_tokens":min(512,max(96,3*len(row["source"]))),"stream":False,
            "chat_template_kwargs":{"enable_thinking":False}},timeout=(10,90))
        response.raise_for_status()
        choice=response.json()["choices"][0]
        text=choice["message"]["content"].strip()
        if choice["finish_reason"]!="stop" or not text or "\n" in text or not re.search(r"[가-힣]",text):
            raise ValueError("CHAIN_CORRECTION_INVALID")
        issues=correction_issues(row["source"],text)
        if not issues or attempt==3: return text
        print("CHAIN_CORRECTION_RETRY="+str(attempt)+":"+",".join(issues),flush=True)
        data={"English":row["source"],"Korean draft":row["draft"],"Context":row["context"],
              "Previous correction":text,"Detected errors":issues,
              "Instruction":"修复上述错误，严格保留原文的数值及运算关系。"}
    raise AssertionError("unreachable")

def payload(rows,marker,stage,review):
    if stage=="correct":
        worker=correct_one
        public=[{k:r[k] for k in ("id","source","draft","context")} for r in rows]
    else:
        worker=review.review_one
        public=[{"id":r["id"],"source":r["source"],"candidate":r["corrected"]} for r in rows]
    helpers=inspect.getsource(correction_issues)+"\n" if stage=="correct" else ""
    return ("\nimport json,re\n"+helpers+inspect.getsource(worker)+"\n"
        +"chain_rows=json.loads("+repr(json.dumps(public,ensure_ascii=False))+")\n"
        +"for row in chain_rows:\n"
        +"    result="+worker.__name__+"(row,base)\n"
        +"    print("+repr(marker)+"+json.dumps({'id':row['id'],'value':result},ensure_ascii=False),flush=True)\n")

def prefetch_source(bootstraps,shared,config,marker):
    # All model files live on the same Colab VM, outside per-model log directories.
    first=bootstraps[0][1]
    body="CONFIG="+repr(config)+"\nREVIEW_SHARED_ROOT="+repr(shared)+"\n"
    for key in ("RCLONE_DRIVE_ID","RCLONE_ZIP_SHA","MANIFEST_SHA","CACHE_SPEC"):
        body+=key+"="+repr(first[key])+"\n"
    body+=(ROOT/"colab-cache-mount.py").read_text()+"\n"
    body+="import tarfile\n"
    body+="BOOTSTRAPS="+repr(bootstraps)+"\n"
    body+="CACHE_CODE="+repr((ROOT/"colab-benchmark-cache.py").read_text())+"\n"
    body+="DONE_MARKER="+repr(marker)+"\n"
    body+=(ROOT/"colab-benchmark-prefetch-remote.py").read_text()+"\n"
    return body

def prefetch(tmp,session):
    kernel=load("kernel",ROOT/"colab-benchmark-kernel.py")
    names=("Hy-MT3-7B-Q8_0","Qwen3-14B-Q4_K_M")
    bootstraps=[(name,read(tmp/("bootstrap-"+name+".json"))) for name in names]
    marker="RO_PREFETCH_"+uuid.uuid4().hex
    body=prefetch_source(bootstraps,os.environ["RO_REVIEW_SHARED_ROOT"],os.environ["REMOTE_CONFIG"],marker)
    compile(body,"prefetch-remote.py","exec")
    path=tmp/"prefetch-remote.py";path.write_text(body,encoding="utf-8")
    ready=False
    seen=set()
    def on_line(line):
        nonlocal ready
        if line==marker:
            ready=True
        elif line.startswith("PREFETCH_MODEL_READY="):
            name=line.split("=",1)[1]
            if name not in names or name in seen: raise RuntimeError("PREFETCH_RESULT_CONFLICT")
            seen.add(name);print(line,flush=True)
        elif line in {"PREFETCH_MODEL_START="+n for n in names} or re.fullmatch(r"PREFETCH_DISK_(?:FREE|REQUIRED)_BYTES=\d+",line):
            print(line,flush=True)
        else:
            kernel.safe_progress(line,print)
    args=["colab","--auth=adc","--config",str(tmp/"sessions.json"),"exec","-s",session,"--timeout","1650","-f",str(path)]
    rc,raw=kernel.invoke(args,1680,on_line=on_line,on_wait=lambda elapsed:print(f"PREFETCH_WAIT={elapsed}s models={len(seen)}/{len(names)}",flush=True))
    if rc or not ready or seen!=set(names):
        if rc: kernel.report_failure("PREFETCH",raw,kernel.assignment_count,print)
        raise RuntimeError("CHAIN_PREFETCH_INCOMPLETE")
    (tmp/"chain-prefetch-ready").touch()
    print("CHAIN_PREFETCH_READY=2 MODELS GPU_LOADS=0",flush=True)
    return 0

def run(tmp,session,stage):
    if stage not in ("correct","verify"): raise ValueError("CHAIN_STAGE")
    review=load("review",ROOT/"colab-benchmark-review.py")
    kernel=load("kernel",ROOT/"colab-benchmark-kernel.py")
    rows=read(tmp/("chain-drafts.json" if stage=="correct" else "chain-corrected.json"))
    marker="RO_CHAIN_"+uuid.uuid4().hex+"="
    if not (tmp/"chain-prefetch-ready").is_file():
        raise RuntimeError("CHAIN_PREFETCH_REQUIRED")
    body,cleanup_marker=review.build_remote(tmp,payload(rows,marker,stage,review),marker,preloaded=True)
    if cleanup_marker is None: raise RuntimeError("CHAIN_SHARED_SESSION_REQUIRED")
    compile(body,"chain-remote.py","exec")
    path=tmp/"chain-remote.py";path.write_text(body,encoding="utf-8")
    results={};cleaned=False
    ids={r["id"] for r in rows}
    def on_line(line):
        nonlocal cleaned
        if line==cleanup_marker:
            cleaned=True
            print("CHAIN_MODEL_RELEASED="+stage,flush=True)
        elif line.startswith(marker):
            item=json.loads(line[len(marker):])
            i,value=item["id"],item["value"]
            if i not in ids or i in results or not isinstance(value,str):
                raise RuntimeError("CHAIN_RESULT_CONFLICT")
            results[i]=value
            print(f"CHAIN_PROGRESS={stage}:{len(results)}/{len(rows)} id={i}",flush=True)
        elif line=="PRELOADED_MODEL_REUSED" or re.fullmatch(r"CHAIN_CORRECTION_RETRY=[12]:[a-z_,]+",line):
            print(line,flush=True)
        else:
            kernel.safe_progress(line,print)
    args=["colab","--auth=adc","--config",str(tmp/"sessions.json"),"exec","-s",session,"--timeout","1500","-f",str(path)]
    rc,raw=kernel.invoke(args,1530,on_line=on_line,on_wait=lambda elapsed:print(f"CHAIN_WAIT={stage}:{elapsed}s {len(results)}/{len(rows)}",flush=True))
    if rc or not cleaned or set(results)!=ids:
        if rc: kernel.report_failure("CHAIN_"+stage.upper(),raw,kernel.assignment_count,print)
        raise RuntimeError("CHAIN_REMOTE_INCOMPLETE")
    if stage=="correct":
        translator=load("translator",ROOT/"colab-benchmark-translate.py")
        corrected=[]
        for row in rows:
            value=results[row["id"]]
            checks=translator.check_output(row["source"],value,translator.required_terms(row["source"]))
            issues=correction_issues(row["source"],value)
            checks["duration_semantics"]=not any(i!="numeric_tokens_changed" for i in issues)
            if not all(checks.values()):
                print("CHAIN_STRUCTURAL_FAILURE="+row["id"]+":"+",".join(k for k,v in checks.items() if not v),flush=True)
            corrected.append({**row,"corrected":value,"checks":checks})
        write(tmp/"chain-corrected.json",corrected)
    else:
        write(tmp/"chain-verified.json",[{**row,"verdict":results[row["id"]]} for row in rows])
    return 0

def report(tmp,bench):
    path=tmp/"chain-verified.json"
    if not path.exists():
        print("CHAIN_REPORT=INCOMPLETE",flush=True)
        return 1
    refs={r["id"]:r["reference"] for r in read(bench/"references.json")}
    rows=read(path)
    for row in rows:
        print("CHAIN_RESULT="+json.dumps({k:row[k] for k in ("id","source","draft","corrected","verdict","checks")}|{"reference":refs[row["id"]]},ensure_ascii=False),flush=True)
    # Exact match is diagnostic only: equivalent wording is not an execution
    # failure. Semantic verdicts and independent checks remain mandatory.
    ok=all(row["verdict"]=="ACCEPT" and all(row["checks"].values()) for row in rows)
    regression=next(row for row in rows if row["id"]=="189")
    exact=regression["corrected"]==refs["189"]
    print(f"CHAIN_REPORT=verified:{sum(row['verdict']=='ACCEPT' for row in rows)}/{len(rows)} regression_reference_exact:{str(exact).lower()}",flush=True)
    return 0 if ok else 1

if __name__=="__main__":
    mode,tmp,*args=sys.argv[1:];tmp=pathlib.Path(tmp)
    if mode=="restore": restore(tmp,*map(pathlib.Path,args))
    elif mode=="prefetch": raise SystemExit(prefetch(tmp,*args))
    elif mode=="run": raise SystemExit(run(tmp,*args))
    elif mode=="report": raise SystemExit(report(tmp,pathlib.Path(args[0])))
    else: raise SystemExit("CHAIN_MODE")
