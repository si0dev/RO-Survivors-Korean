"""Production runner. No benchmark fixtures or reference answers."""
import importlib.util,inspect,json,os,pathlib,re,sys,time,uuid
ROOT=pathlib.Path(__file__).resolve().parent
def load(name,path=None):
    spec=importlib.util.spec_from_file_location(name,path or ROOT/(name+".py"))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module
def read(path):
    return json.loads(path.read_text(encoding="utf-8"))
def write(path,data):
    path.write_text(json.dumps(data,ensure_ascii=False),encoding="utf-8")
contract=load("colab-translate")
check_output=contract.check_output
required_terms=contract.required_terms

def is_duration_modifier(source):
    return bool(re.fullmatch(r"[+-]\d+(?:\.\d+)?\s*(?:s|sec|seconds?)\s+of\s+[^.!?]+[.]?",source.strip(),re.I))

def chain_terms(source,hints=None):
    terms=required_terms(source)
    hints=hints or {}
    # A verified longer phrase supersedes a generic nested term.
    for key in list(terms):
        if any(key.casefold() in phrase.casefold() for phrase in hints):
            del terms[key]
    return {**terms,**hints}

def correction_issues(source,text,hints=None):
    checks=check_output(source,text,chain_terms(source,hints))
    issues=["numeric_tokens_changed" if k=="numbers" else "structural_"+k for k,v in checks.items() if not v]
    # Only target terse signed duration modifiers, not ordinary fixed-duration effects.
    if is_duration_modifier(source):
        if not re.search(r"(?:지속\s*시간|시간|증가|감소|연장|단축)",text) or re.search(r"초\s*동안",text):
            issues.append("duration_modifier_rendered_as_fixed_duration")
    if re.search(r"\bhalf as long\b",source,re.I) and not re.search(r"절반|반으로|반만|반의",text):
        issues.append("relative_duration_not_preserved")
    # Narrow regression guard: a status introduced by a prior prompt example
    # is not supported by an unrelated source sentence.
    if re.search(r"중독|독\s*상태|독\s*피해",text) and not re.search(r"\b(?:poison\w*|toxic\w*|toxins?|venom\w*|intoxicat\w*)\b",source,re.I):
        issues.append("unsupported_poison_effect")
    return issues

def correct_one(row,base):
    import json,requests
    prompt=("你是英韩游戏翻译校订员。以英文原文为依据检查已有韩语译文。"
            "如果初稿没有语义错误，逐字原样返回；仅修正明确错误，不要为润色而重写。"
            "不得添加原文没有的状态、伤害、对象或条件。保留原文的数字、符号、变量、单位和关系。"
            "只输出最终一行韩语译文，不要解释。\n")
    # Reuse the signed-modifier prompt that actually corrected the regression in #53.
    # Its example must never be passed to unrelated ordinary descriptions.
    if is_duration_modifier(row["source"]):
        prompt=("你是英韩游戏翻译校订员。英文原文是事实依据，韩语初稿是需要校订的已有译文。"
                "保留初稿中正确的部分，仅修正错误、遗漏或术语问题；不得从头自由重译。"
                "原文的前置正负号是属性变化量，不是固定状态持续时间。"
                "属性词条必须保留属性变化的语法，不能变成施加状态的描述。"
                "例如：+2 s of poison 表示 중독 지속 시간 +2초，而不是 +2초 동안 중독됩니다。"
                "保留相对时长表达，如 half as long 应保留为 절반，不计算新的绝对秒数。"
                "必须保留全部数值、变量、单位、目标、条件、频率及否定。使用自然韩语游戏用语。"
                "若初稿准确，原样返回。只输出最终一行韩语译文，不要解释。\n")
    if re.search(r"\bhalf as long\b",row["source"],re.I):
        prompt+=("本条有相对时长条件。必须保留相对于前述时长的比例关系，"
                 "不得计算或写入新的绝对秒数。\n")
    terms=chain_terms(row["source"],row.get("terms"))
    if terms:
        prompt+="必须使用指定术语，不得替换："+json.dumps(terms,ensure_ascii=False)+"。\n"
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
        issues=correction_issues(row["source"],text,row.get("terms"))
        if not issues: return text
        if attempt==3:
            # Do not replace an otherwise structurally valid draft with a
            # correction that violates known constraints. Qwen still verifies it.
            if not correction_issues(row["source"],row["draft"],row.get("terms")):
                print("CHAIN_CORRECTION_FALLBACK=original_draft",flush=True)
                return row["draft"]
            print("CHAIN_CORRECTION_UNRESOLVED",flush=True)
            return text
        print("CHAIN_CORRECTION_RETRY="+str(attempt)+":"+",".join(issues),flush=True)
        data={"English":row["source"],"Korean draft":row["draft"],"Context":row["context"],
              "Previous correction":text,"Detected errors":issues,
              "Instruction":"修复上述错误，严格保留原文的数值及运算关系。"}
    raise AssertionError("unreachable")

def correct_task(row,base):
    import requests
    try:
        return {"value":correct_one(row,base),"status":"COMPLETED"}
    except (requests.RequestException,ValueError,KeyError,IndexError,TypeError,AttributeError):
        # A malformed/failed individual completion must not discard the batch.
        return {"value":row["draft"],"status":"ERROR"}


def quality_checks(source,value,hints=None):
    checks=check_output(source,value,chain_terms(source,hints))
    issues=correction_issues(source,value,hints)
    checks["duration_semantics"]=not any(i in ("duration_modifier_rendered_as_fixed_duration","relative_duration_not_preserved") for i in issues)
    checks["unsupported_effect"]="unsupported_poison_effect" not in issues
    return checks

def index_task(row,base):
    try:
        result=translate_one(row,base)
        return {"value":result["ko"],"status":"COMPLETED"}
    except TranslationFailure:
        return {"value":"","status":"ERROR"}

def verify_task(row,base):
    context={"terms":row.get("terms",{}),"context":row.get("context","")}
    original=review_one({"source":row["source"],"candidate":row["draft"],**context},base)
    corrected=original if row["candidate"]==row["draft"] else review_one({"source":row["source"],"candidate":row["candidate"],**context},base)
    return {"original":original,"corrected":corrected}

def choose(row,verdicts):
    original_ok=(row["index_status"]=="COMPLETED" and verdicts["original"]=="ACCEPT"
                 and all(quality_checks(row["source"],row["draft"],row["terms"]).values()))
    corrected_ok=(row["correction_status"]=="COMPLETED" and verdicts["corrected"]=="ACCEPT"
                  and all(quality_checks(row["source"],row["corrected"],row["terms"]).values()))
    if corrected_ok: return {"id":row["id"],"ko":row["corrected"],"status":"MODEL_VERIFIED"}
    if original_ok: return {"id":row["id"],"ko":row["draft"],"status":"MODEL_VERIFIED"}
    return {"id":row["id"],"ko":"","status":"REVIEW_REQUIRED"}

def payload(rows,marker,stage,review):
    code=(ROOT/"colab-translate.py").read_text()
    if stage=="index":
        worker=index_task
        public=[{k:r[k] for k in ("id","source","context","terms")} for r in rows]
        helpers=code+"\n"
    elif stage=="correct":
        worker=correct_task
        public=[{k:r[k] for k in ("id","source","draft","context","terms")} for r in rows]
        helpers=code+"\n"+inspect.getsource(is_duration_modifier)+"\n"+inspect.getsource(chain_terms)+"\n"+inspect.getsource(correction_issues)+"\n"+inspect.getsource(correct_one)+"\n"
    else:
        worker=verify_task
        public=[{"id":r["id"],"source":r["source"],"draft":r["draft"],"candidate":r["corrected"],"terms":r["terms"],"context":r["context"]} for r in rows]
        helpers=inspect.getsource(review.review_one)+"\n"
    return ("\nimport json,re\n"+helpers+inspect.getsource(worker)+"\n"
        +"rows=json.loads("+repr(json.dumps(public,ensure_ascii=False))+")\n"
        +"from concurrent.futures import ThreadPoolExecutor,as_completed\n"
        +"with ThreadPoolExecutor(max_workers=2) as pool:\n"
        +"    tasks={pool.submit("+worker.__name__+",row,base):row['id'] for row in rows}\n"
        +"    for task in as_completed(tasks):\n"
        +"        print("+repr(marker)+"+json.dumps({'id':tasks[task],'value':task.result()},ensure_ascii=False),flush=True)\n")

def prefetch_source(bootstraps,shared,config,marker):
    # All model files live on the same Colab VM, outside per-model log directories.
    first=bootstraps[0][1]
    body="CONFIG="+repr(config)+"\nREVIEW_SHARED_ROOT="+repr(shared)+"\n"
    for key in ("RCLONE_DRIVE_ID","RCLONE_ZIP_SHA","MANIFEST_SHA","CACHE_SPEC"):
        body+=key+"="+repr(first[key])+"\n"
    body+=(ROOT/"colab-cache-mount.py").read_text()+"\n"
    body+="import tarfile\n"
    body+="BOOTSTRAPS="+repr(bootstraps)+"\n"
    body+="CACHE_CODE="+repr((ROOT/"colab-cache.py").read_text())+"\n"
    body+="DONE_MARKER="+repr(marker)+"\n"
    body+=(ROOT/"colab-prefetch-remote.py").read_text()+"\n"
    return body

def prefetch(tmp,session):
    kernel=load("kernel",ROOT/"colab-kernel.py")
    names=("Index-Translate-9B-Q6_K","Hy-MT3-7B-Q8_0","Qwen3-14B-Q4_K_M")
    bootstraps=[(name,read(tmp/("bootstrap-"+name+".json"))) for name in names]
    marker="RO_PREFETCH_"+uuid.uuid4().hex
    body=prefetch_source(bootstraps,os.environ["RO_REVIEW_SHARED_ROOT"],os.environ["REMOTE_CONFIG"],marker)
    compile(body,"prefetch-remote.py","exec")
    path=tmp/"prefetch-remote.py";path.write_text(body,encoding="utf-8")
    ready=False
    seen=set()
    last_signal=time.monotonic()
    def on_line(line):
        nonlocal ready,last_signal
        if line==marker:
            ready=True
        elif line.startswith("PREFETCH_MODEL_READY="):
            name=line.split("=",1)[1]
            if name not in names or name in seen: raise RuntimeError("PREFETCH_RESULT_CONFLICT")
            seen.add(name);print(line,flush=True)
        elif line in {"PREFETCH_MODEL_START="+n for n in names} or re.fullmatch(r"PREFETCH_DISK_(?:FREE|REQUIRED)_BYTES=\d+",line):
            print(line,flush=True)
        else:
            def safe(value,**kw):
                nonlocal last_signal
                last_signal=time.monotonic()
                print(value,**kw)
            kernel.safe_progress(line,safe)
        if line==marker or line.startswith(("PREFETCH_MODEL_READY=","PREFETCH_MODEL_START=","PREFETCH_DISK_")):
            last_signal=time.monotonic()
    def waiting(elapsed):
        age=int(time.monotonic()-last_signal)
        print(f"PREFETCH_WAIT={elapsed}s models={len(seen)}/{len(names)} signal_age={age}s",flush=True)
        return age<420
    args=["colab","--auth=adc","--config",str(tmp/"sessions.json"),"exec","-s",session,"--timeout","2400","-f",str(path)]
    rc,raw=kernel.invoke(args,2430,on_line=on_line,on_wait=waiting)
    if rc or not ready or seen!=set(names):
        if rc: kernel.report_failure("PREFETCH",raw,kernel.assignment_count,print)
        raise RuntimeError("CHAIN_PREFETCH_INCOMPLETE")
    (tmp/"chain-prefetch-ready").touch()
    print("LLM_PREFETCH_READY=3 MODELS GPU_LOADS=0",flush=True)
    return 0


def run(tmp,session,stage):
    if stage not in ("index","correct","verify"): raise ValueError("LLM_STAGE")
    review=load("colab-review")
    kernel=load("colab-kernel")
    rows=read(tmp/{"index":"pending.json","correct":"indexed.json","verify":"corrected.json"}[stage])
    ids=[r["id"] for r in rows]
    if len(set(ids))!=len(ids) or any(not re.fullmatch(r"[0-9]{1,6}",i) for i in ids):
        raise RuntimeError("LLM_INPUT_IDS")
    active=rows if stage=="index" else [r for r in rows if r.get("draft")]
    results={}
    if active:
        if not (tmp/"chain-prefetch-ready").is_file(): raise RuntimeError("LLM_PREFETCH_REQUIRED")
        marker="RO_LLM_"+uuid.uuid4().hex+"="
        body,cleanup_marker=review.build_remote(tmp,payload(active,marker,stage,review),marker,preloaded=True)
        if not cleanup_marker: raise RuntimeError("LLM_SHARED_SESSION_REQUIRED")
        body="CHAIN_FULL_SCOPE=True\n"+body
        compile(body,"llm-remote.py","exec")
        path=tmp/"llm-remote.py";path.write_text(body,encoding="utf-8")
        expected={r["id"] for r in active}
        cleaned=False
        last_signal=time.monotonic()
        def on_line(line):
            nonlocal cleaned,last_signal
            if line==cleanup_marker:
                cleaned=True;last_signal=time.monotonic()
                print("LLM_MODEL_RELEASED="+stage,flush=True)
            elif line.startswith(marker):
                item=json.loads(line[len(marker):])
                i,value=item["id"],item["value"]
                if i not in expected or i in results or not isinstance(value,dict):
                    raise RuntimeError("LLM_RESULT_CONFLICT")
                if stage=="verify":
                    if set(value)!={"original","corrected"} or any(v not in ("ACCEPT","REJECT","ERROR","INVALID") for v in value.values()):
                        raise RuntimeError("LLM_VERDICT_SCHEMA")
                elif set(value)!={"value","status"} or not isinstance(value["value"],str) or value["status"] not in ("COMPLETED","ERROR"):
                    raise RuntimeError("LLM_RESPONSE_SCHEMA")
                results[i]=value;last_signal=time.monotonic()
                print(f"LLM_PROGRESS={stage}:{len(results)}/{len(active)}",flush=True)
            else:
                def safe(value,**kw):
                    nonlocal last_signal
                    last_signal=time.monotonic()
                    print(value,**kw)
                kernel.safe_progress(line,safe)
        def waiting(elapsed):
            age=int(time.monotonic()-last_signal)
            print(f"LLM_WAIT={stage}:{elapsed}s {len(results)}/{len(active)} signal_age={age}s",flush=True)
            return age<900
        limit=4200
        args=["colab","--auth=adc","--config",str(tmp/"sessions.json"),"exec","-s",session,"--timeout",str(limit),"-f",str(path)]
        rc,raw=kernel.invoke(args,limit+30,on_line=on_line,on_wait=waiting)
        if rc or not cleaned or set(results)!=expected:
            if rc: kernel.report_failure("LLM_"+stage.upper(),raw,kernel.assignment_count,print)
            raise RuntimeError("LLM_REMOTE_INCOMPLETE")
    output=[]
    for row in rows:
        result=results.get(row["id"])
        if stage=="index":
            output.append({**row,"draft":result["value"],"index_status":result["status"]})
        elif stage=="correct":
            output.append({**row,"corrected":result["value"] if result else "","correction_status":result["status"] if result else "ERROR"})
        else:
            output.append(choose(row,result) if result else {"id":row["id"],"ko":"","status":"REVIEW_REQUIRED"})
    write(tmp/{"index":"indexed.json","correct":"corrected.json","verify":"verified.json"}[stage],output)

if __name__=="__main__":
    mode,tmp,session,*args=sys.argv[1:]
    if mode=="prefetch": raise SystemExit(prefetch(pathlib.Path(tmp),session))
    if mode=="run": run(pathlib.Path(tmp),session,*args)
    else: raise SystemExit("LLM_MODE")
