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
    scope=os.environ.get("RO_CHAIN_SCOPE","duration")
    if scope not in ("duration","all"): raise RuntimeError("CHAIN_SCOPE")
    wanted=("189","005") if scope=="duration" else tuple(r["id"] for r in inputs)
    if scope=="all" and (len(wanted)!=200 or len(set(wanted))!=200):
        raise RuntimeError("CHAIN_FULL_INPUT_COUNT")
    selected=[]
    by_id={r["id"]:r for r in inputs}
    for i in wanted:
        source=by_id[i]
        draft=rows[i]
        if not draft["ko"]: raise RuntimeError("CHAIN_EMPTY_DRAFT")
        row={**source,"draft":draft["ko"]}
        # Previously agreed exception: numeric shorthand is not translation work.
        if source["source"]=="1M" and draft["ko"]=="1M":
            row["excluded"]="numeric_shorthand"
        elif not all(draft["checks"].values()):
            raise RuntimeError("CHAIN_DRAFT_NOT_STRUCTURALLY_VALID")
        selected.append(row)
    if by_id["189"]["source"]!="+0.3 s of freeze.":
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
    if len(rows)!=200 or set(rows)!=set(records): raise RuntimeError("CHAIN_LOG_SELECTION")
    return select_drafts(inputs,rows)

def restore_retry(tmp,bench):
    snapshot=read(ROOT/"colab-benchmark-chain-run57.json")
    if (snapshot["schema"],snapshot["run_id"],snapshot["job_id"],snapshot["head_sha"])!=(1,46131466704,140937416429,"0f74e262cda783c5b8f569802df0508c9b8c5c12"):
        raise RuntimeError("CHAIN_RETRY_PROVENANCE")
    refs={r["id"]:r for r in read(bench/"references.json")}
    rows=snapshot["rows"]
    if len(rows)!=200 or {r["id"] for r in rows}!=set(refs):
        raise RuntimeError("CHAIN_RETRY_IDS")
    for row in rows:
        if any(row[k]!=refs[row["id"]][k] for k in ("source","group","context")):
            raise RuntimeError("CHAIN_RETRY_SOURCE_MISMATCH")
    active=[r for r in rows if not r.get("excluded") and (r["verdict"]!="ACCEPT" or not all(r["final_checks"].values()))]
    if len(active)!=28 or sum(bool(r.get("excluded")) for r in rows)!=1:
        raise RuntimeError("CHAIN_RETRY_COUNT")
    memory=read(tmp/"chain-memory.json")
    by_id={r["id"]:r for r in memory}
    if len(memory)!=28 or set(by_id)!={r["id"] for r in active}:
        raise RuntimeError("CHAIN_MEMORY_IDS")
    drafts=[];reused=[]
    reuse=os.environ.get("RO_CHAIN_MEMORY_REUSE")=="1"
    for row in active:
        hint=by_id[row["id"]]
        if hint["source"]!=row["source"]: raise RuntimeError("CHAIN_MEMORY_SOURCE")
        # Exact memory reuse is not an LLM quality verdict. Keep it outside
        # model requests and measure it independently.
        if reuse and isinstance(hint.get("exact"),str) and hint["exact"].strip():
            reused.append({"id":row["id"],"source":row["source"],"approved":hint["exact"],"selection":"approved_memory"})
        else:
            drafts.append({k:row[k] for k in ("id","source","group","context")}|{"draft":row["final"],"terms":hint["terms"]})
    write(tmp/"chain-drafts.json",drafts)
    if reuse:
        write(tmp/"chain-memory-reused.json",reused)
    print(f"CHAIN_RETRY_REUSED=171 APPROVED_MEMORY={len(reused)} EXCLUDED=1 PENDING={len(drafts)} INDEX_INFERENCE=0",flush=True)

def restore(tmp,bench,historical):
    if os.environ.get("RO_CHAIN_SCOPE")=="retry":
        return restore_retry(tmp,bench)
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
        # The fixed #42 assessment log contains the actual 200 drafts.
        # Use the validated log record rather than regenerate anything.
        if str(exc) not in ("CHECKPOINT_DRIVE_IO","CHECKPOINT_DRIVE_TIMEOUT","CHAIN_CHECKPOINT_INCOMPLETE"):
            raise
        print("CHAIN_DRIVE_RESTORE_UNAVAILABLE="+str(exc),flush=True)
        selected=restore_logged_drafts(inputs,refs)
        print(f"CHAIN_INDEX_SOURCE=RUN42_LOG SELECTED={len(selected)} INDEX_INFERENCE=0",flush=True)
    else:
        selected=select_drafts(inputs,rows)
        print(f"CHAIN_INDEX_CHECKPOINT_RESTORED=200 SELECTED={len(selected)} INDEX_INFERENCE=0",flush=True)
    write(tmp/"chain-drafts.json",selected)

# Use the same structural contract already tested by the first-model benchmark.
_contract=load("chain_translation_contract",ROOT/"colab-benchmark-translate.py")
check_output=_contract.check_output
required_terms=_contract.required_terms

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

def verify_task(row,base):
    context={"terms":row.get("terms",{}),"context":row.get("context","")}
    original=review_one({"source":row["source"],"candidate":row["draft"],**context},base)
    corrected=original if row["candidate"]==row["draft"] else review_one({"source":row["source"],"candidate":row["candidate"],**context},base)
    return {"original":original,"corrected":corrected}

def payload(rows,marker,stage,review):
    if stage=="correct":
        worker=correct_task
        public=[{k:r[k] for k in ("id","source","draft","context")}|{"terms":r.get("terms",{})} for r in rows]
        # Execute the existing structural contract in its own namespace.
        contract=(ROOT/"colab-benchmark-translate.py").read_text().split("# Use the model family's constrained translation structure",1)[0]
        helpers="contract_ns={}\nexec("+repr(contract)+",contract_ns)\ncheck_output=contract_ns['check_output']\nrequired_terms=contract_ns['required_terms']\n"
        helpers+=inspect.getsource(is_duration_modifier)+"\n"+inspect.getsource(chain_terms)+"\n"+inspect.getsource(correction_issues)+"\n"+inspect.getsource(correct_one)+"\n"
    else:
        worker=verify_task
        # Separate review requests for original and corrected text; no approved references.
        public=[{"id":r["id"],"source":r["source"],"draft":r["draft"],"candidate":r["corrected"],"terms":r.get("terms",{}),"context":r.get("context","")} for r in rows]
        helpers=inspect.getsource(review.review_one)+"\n"
    return ("\nimport json,re\n"+helpers+inspect.getsource(worker)+"\n"
        +"chain_rows=json.loads("+repr(json.dumps(public,ensure_ascii=False))+")\n"
        +"from concurrent.futures import ThreadPoolExecutor,as_completed\n"
        +"with ThreadPoolExecutor(max_workers=2) as chain_pool:\n"
        +"    chain_futures={chain_pool.submit("+worker.__name__+",row,base):row['id'] for row in chain_rows}\n"
        +"    for chain_future in as_completed(chain_futures):\n"
        +"        print("+repr(marker)+"+json.dumps({'id':chain_futures[chain_future],'value':chain_future.result()},ensure_ascii=False),flush=True)\n")

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
    active=[r for r in rows if not r.get("excluded")]
    body,cleanup_marker=review.build_remote(tmp,payload(active,marker,stage,review),marker,preloaded=True)
    if len(active)>2:
        body="CHAIN_FULL_SCOPE=True\n"+body
    if cleanup_marker is None: raise RuntimeError("CHAIN_SHARED_SESSION_REQUIRED")
    compile(body,"chain-remote.py","exec")
    path=tmp/"chain-remote.py";path.write_text(body,encoding="utf-8")
    results={};cleaned=False
    ids={r["id"] for r in active}
    def on_line(line):
        nonlocal cleaned
        if line==cleanup_marker:
            cleaned=True
            print("CHAIN_MODEL_RELEASED="+stage,flush=True)
        elif line.startswith(marker):
            item=json.loads(line[len(marker):])
            i,value=item["id"],item["value"]
            if i not in ids or i in results or not isinstance(value,dict):
                raise RuntimeError("CHAIN_RESULT_CONFLICT")
            if stage=="correct":
                if set(value)!={"value","status"} or not isinstance(value["value"],str) or value["status"] not in ("COMPLETED","ERROR"):
                    raise RuntimeError("CHAIN_CORRECTION_SCHEMA")
            elif set(value)!={"original","corrected"} or any(v not in ("ACCEPT","REJECT","ERROR","INVALID") for v in value.values()):
                raise RuntimeError("CHAIN_VERDICT_SCHEMA")
            results[i]=value
            print(f"CHAIN_PROGRESS={stage}:{len(results)}/{len(active)} id={i}",flush=True)
        elif line in ("PRELOADED_MODEL_REUSED","CHAIN_CORRECTION_FALLBACK=original_draft","CHAIN_CORRECTION_UNRESOLVED") or re.fullmatch(r"CHAIN_CORRECTION_RETRY=[12]:[a-z_,]+",line):
            print(line,flush=True)
        else:
            kernel.safe_progress(line,print)
    limit=4200 if len(active)>2 else 1500
    args=["colab","--auth=adc","--config",str(tmp/"sessions.json"),"exec","-s",session,"--timeout",str(limit),"-f",str(path)]
    rc,raw=kernel.invoke(args,limit+30,on_line=on_line,on_wait=lambda elapsed:print(f"CHAIN_WAIT={stage}:{elapsed}s {len(results)}/{len(active)}",flush=True))
    if rc or not cleaned or set(results)!=ids:
        if rc: kernel.report_failure("CHAIN_"+stage.upper(),raw,kernel.assignment_count,print)
        raise RuntimeError("CHAIN_REMOTE_INCOMPLETE")
    if stage=="correct":
        corrected=[]
        for row in rows:
            if row.get("excluded"):
                corrected.append({**row,"corrected":row["draft"],"correction_status":"EXCLUDED","checks":{},"draft_checks":{}})
                continue
            result=results[row["id"]]
            value=result["value"]
            checks=quality_checks(row["source"],value,row.get("terms"))
            if not all(checks.values()):
                print("CHAIN_STRUCTURAL_FAILURE="+row["id"]+":"+",".join(k for k,v in checks.items() if not v),flush=True)
            corrected.append({**row,"corrected":value,"correction_status":result["status"],"checks":checks,"draft_checks":quality_checks(row["source"],row["draft"],row.get("terms"))})
        write(tmp/"chain-corrected.json",corrected)
    else:
        verified=[finalize(row,results.get(row["id"])) for row in rows]
        write(tmp/"chain-verified.json",verified)
    return 0

def quality_checks(source,value,hints=None):
    checks=check_output(source,value,chain_terms(source,hints))
    issues=correction_issues(source,value,hints)
    checks["duration_semantics"]=not any(i in ("duration_modifier_rendered_as_fixed_duration","relative_duration_not_preserved") for i in issues)
    checks["unsupported_effect"]="unsupported_poison_effect" not in issues
    return checks

def finalize(row,verdicts):
    if row.get("excluded"):
        return {**row,"draft_verdict":"EXCLUDED","corrected_verdict":"EXCLUDED","verdict":"EXCLUDED","final":row["draft"],"final_checks":{},"selection":"excluded"}
    original,corrected=verdicts["original"],verdicts["corrected"]
    # A rejected or structurally invalid correction may not replace a verified
    # original. No reference answer is used to select the output.
    use_original=(corrected!="ACCEPT" or not all(row["checks"].values())) and original=="ACCEPT" and all(row["draft_checks"].values())
    return {**row,"draft_verdict":original,"corrected_verdict":corrected,
            "verdict":original if use_original else corrected,
            "final":row["draft"] if use_original else row["corrected"],
            "final_checks":row["draft_checks"] if use_original else row["checks"],
            "selection":"verified_original" if use_original else "corrected" if row["corrected"]!=row["draft"] else "unchanged"}

def normalize(text):
    return re.sub(r"\s+","",text).casefold()

def similarity(a,b):
    from collections import Counter
    a,b=normalize(a),normalize(b)
    if min(len(a),len(b))<2: return float(a==b)
    x,y=(Counter(text[i:i+2] for i in range(len(text)-1)) for text in (a,b))
    return 2*sum((x&y).values())/(sum(x.values())+sum(y.values()))

def summarize(rows,refs):
    from collections import Counter,defaultdict
    total=Counter();groups=defaultdict(Counter)
    for row in rows:
        counts=Counter(total=1)
        if row.get("excluded"):
            counts["excluded"]+=1
        else:
            counts["evaluated"]+=1
            counts["changed_by_hymt"]+=row["corrected"]!=row["draft"]
            counts["retained_original"]+=row["final"]==row["draft"]
            counts["semantic_fallback"]+=row["selection"]=="verified_original"
            counts["correction_errors"]+=row["correction_status"]=="ERROR"
            counts["review_errors"]+=any(row[k] not in ("ACCEPT","REJECT") for k in ("draft_verdict","corrected_verdict"))
            for label,text,checks,verdict in (("draft",row["draft"],row["draft_checks"],row["draft_verdict"]),("corrected",row["corrected"],row["checks"],row["corrected_verdict"]),("final",row["final"],row["final_checks"],row["verdict"])):
                counts[label+"_structure_pass"]+=all(checks.values())
                counts[label+"_terms_pass"]+=checks["terms"]
                counts[label+"_semantic_accept"]+=verdict=="ACCEPT"
                counts[label+"_combined_pass"]+=verdict=="ACCEPT" and all(checks.values())
                counts[label+"_reference_exact"]+=normalize(text)==normalize(refs[row["id"]])
                counts[label+"_similarity_sum"]+=similarity(text,refs[row["id"]])
            counts["corrected_semantic_improved"]+=row["draft_verdict"]=="REJECT" and row["corrected_verdict"]=="ACCEPT"
            counts["corrected_semantic_regressed"]+=row["draft_verdict"]=="ACCEPT" and row["corrected_verdict"]=="REJECT"
        total.update(counts);groups[row["group"]].update(counts)
    def result(counts):
        out=dict(counts)
        for label in ("draft","corrected","final"):
            out[label+"_mean_reference_similarity"]=round(out.pop(label+"_similarity_sum",0)/max(1,out.get("evaluated",0)),4)
        return out
    return result(total),{name:result(counts) for name,counts in groups.items()}

def report_memory_reuse(tmp,bench):
    refs={r["id"]:r["reference"] for r in read(bench/"references.json")}
    reused=read(tmp/"chain-memory-reused.json")
    pending=read(tmp/"chain-drafts.json")
    all_ids=[r["id"] for r in reused+pending]
    if len(all_ids)!=28 or len(set(all_ids))!=28:
        raise RuntimeError("CHAIN_MEMORY_ROUTING_INCOMPLETE")
    path=tmp/"chain-verified.json"
    results=read(path) if path.exists() else []
    result_ids=[r["id"] for r in results]
    if len(result_ids)!=len(set(result_ids)) or not set(result_ids)<={r["id"] for r in pending}:
        raise RuntimeError("CHAIN_MEMORY_RESULT_IDS")
    passed=sum(r["verdict"]=="ACCEPT" and all(r["final_checks"].values()) and r["correction_status"]!="ERROR" and r["draft_verdict"] in ("ACCEPT","REJECT") and r["corrected_verdict"] in ("ACCEPT","REJECT") for r in results)
    for row in reused:
        print("CHAIN_MEMORY_REUSED="+json.dumps(row,ensure_ascii=False),flush=True)
    for row in results:
        print("CHAIN_RESULT="+json.dumps({**row,"reference":refs[row["id"]]},ensure_ascii=False),flush=True)
    stats={"prior_model_pass":171,"approved_memory_reused":len(reused),
           "memory_matches_frozen_reference":sum(r["approved"]==refs[r["id"]] for r in reused),
           "new_model_evaluated":len(results),"new_model_pass":passed,"pending_model":len(pending),
           "resolved":171+len(reused)+passed,"evaluated":199,"excluded":1,
           "unresolved":len(pending)-passed}
    print("CHAIN_MEMORY_ROUTING_SUMMARY="+json.dumps(stats),flush=True)
    return 0 if len(results)==len(pending) and passed==len(pending) else 1

def report(tmp,bench):
    if os.environ.get("RO_CHAIN_MEMORY_REUSE")=="1":
        return report_memory_reuse(tmp,bench)
    path=tmp/"chain-verified.json"
    if not path.exists():
        print("CHAIN_REPORT=INCOMPLETE",flush=True)
        return 1
    refs={r["id"]:r["reference"] for r in read(bench/"references.json")}
    rows=read(path)
    scope=os.environ.get("RO_CHAIN_SCOPE","duration")
    expected={"all":200,"duration":2,"retry":28}[scope]
    if len(rows)!=expected or len({r["id"] for r in rows})!=expected:
        raise RuntimeError("CHAIN_REPORT_INCOMPLETE")
    for row in rows:
        print("CHAIN_RESULT="+json.dumps({**row,"reference":refs[row["id"]]},ensure_ascii=False),flush=True)
    stats,groups=summarize(rows,refs)
    for name,group in groups.items():
        print("CHAIN_GROUP="+json.dumps({"group":name,**group}),flush=True)
    print("CHAIN_QUALITY_SUMMARY="+json.dumps(stats),flush=True)
    evaluated=stats["evaluated"]
    ok=stats["final_combined_pass"]==evaluated and not stats["correction_errors"] and not stats["review_errors"]
    print(f"CHAIN_REPORT=verified:{stats['final_combined_pass']}/{evaluated} excluded:{stats.get('excluded',0)} total:{len(rows)}",flush=True)
    if scope=="retry":
        # Known approved exact hits are separate from model fallback results.
        memory=read(tmp/"chain-memory.json")
        hits=[m for m in memory if m["exact"] is not None]
        print("CHAIN_RETRY_SUMMARY="+json.dumps({"prior_pass":171,"retried":28,"new_pass":stats["final_combined_pass"],"combined_pass":171+stats["final_combined_pass"],"evaluated":199,"exact_memory_hits":len(hits),"exact_memory_matches_frozen_reference":sum(m["exact"]==refs[m["id"]] for m in hits)}),flush=True)
    # A completed experiment may still fail the quality gate. Never publish.
    return 0 if ok else 1

if __name__=="__main__":
    mode,tmp,*args=sys.argv[1:];tmp=pathlib.Path(tmp)
    if mode=="restore": restore(tmp,*map(pathlib.Path,args))
    elif mode=="prefetch": raise SystemExit(prefetch(tmp,*args))
    elif mode=="run": raise SystemExit(run(tmp,*args))
    elif mode=="report": raise SystemExit(report(tmp,pathlib.Path(args[0])))
    else: raise SystemExit("CHAIN_MODE")
