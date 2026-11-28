"""Independent small semantic-review experiment. Never generate translations."""
import inspect,json,os,pathlib,re,sys,uuid
import importlib.util

ROOT=pathlib.Path(__file__).resolve().parent
# Controlled pairs: same numbers and generally similar wording, opposite verdict.
# Synthetic test data except the known duration/increase example. Expected
# verdicts stay on the runner and are never inserted in the remote source.
CASES=[
    ("duration"," +0.3 s of freeze.".strip(),"동빙 시간 +0.3초.","+0.3초 동안 동빙됩니다."),
    ("direction","Reduces casting time by 20%.","캐스팅 시간이 20% 감소합니다.","캐스팅 시간이 20% 증가합니다."),
    ("target","Heals nearby allies for 10% of their max HP.","주변 아군의 최대 HP를 10% 회복합니다.","주변 적의 최대 HP를 10% 회복합니다."),
    ("condition","While the shield is active, damage increases by 15%.","보호막이 활성화된 동안 피해량이 15% 증가합니다.","보호막이 종료되면 피해량이 15% 증가합니다."),
    ("frequency","Deals 30 damage every 2 seconds.","2초마다 30의 피해를 줍니다.","2초 후 30의 피해를 한 번 줍니다."),
    ("negation","Bosses cannot be frozen.","보스는 동빙되지 않습니다.","보스는 동빙될 수 있습니다."),
]
def sample_rows():
    rows=[]
    for i,(category,source,good,bad) in enumerate(CASES):
        candidates=((good,"ACCEPT"),(bad,"REJECT")) if i%2==0 else ((bad,"REJECT"),(good,"ACCEPT"))
        for j,(candidate,expected) in enumerate(candidates):
            rows.append({"id":f"{i*2+j+1:02}","category":category,"source":source,"candidate":candidate,"expected":expected})
    # Avoid showing related pairs consecutively to the model (each call is isolated).
    return rows[::2]+rows[1::2]

def selected_rows():
    scope=os.environ.get("RO_REVIEW_SCOPE","all")
    rows=sample_rows()
    if scope=="all":
        return rows
    if scope=="duration":
        # Include the correct counterpart, so rejecting everything cannot pass.
        return [row for row in rows if row["category"]=="duration"]
    raise ValueError("UNKNOWN_REVIEW_SCOPE")

def review_one(row,base):
    import json,requests
    prompt=("你是英韩游戏数值与技能效果的语义审校员，不是译者。"
            "独立解析英文和韩文，再比较它们表示的机制，而不是比较相同的数字或单词。\n"
            "检查清单：效果主体、目标、属性、运算方式、数值、单位、持续时间、触发条件、频率、否定、概率、上限和下限。"
            "运算方式必须一致：增加量、减少量、倍率、百分比、绝对值、固定持续时间不能互换。"
            "尤其是简短属性词条：前置 + 或 - 表示相对于原有属性的变化量；"
            "正数持续时间的加成不是一次施加状态的固定持续时间。"
            "例如，某个状态时长增加 2 秒与使目标进入该状态 2 秒是不同机制。"
            "译文即使保留 + 符号和数值，如果语法把变化量改成固定时长，也应拒绝。"
            "同样，不得把增加的伤害值当成最终伤害，不得省略或新增条件。"
            "允许自然的韩语词序和简洁属性标签，不因非实质措辞差异拒绝。\n"
            "只有所有明确的原文机制均被保留且没有新增或冲突含义时输出 ACCEPT。"
            "发现任一明确语义差异或无法确认机制一致时输出 REJECT。"
            "只输出一个英文标签 ACCEPT 或 REJECT，不要翻译、解释或输出其他内容。\n"
            +json.dumps({"English":row["source"],"Korean":row["candidate"]},ensure_ascii=False))
    try:
        res=requests.post(base+"/v1/chat/completions",
                          json={"messages":[{"role":"user","content":prompt}],
                                "temperature":0,"max_tokens":24,"stream":False,
                                "chat_template_kwargs":{"enable_thinking":False}},
                          timeout=(10,90))
        if res.status_code!=200:
            return "ERROR"
        choice=res.json()["choices"][0]
        verdict=choice["message"]["content"].strip()
        if choice["finish_reason"]!="stop" or verdict not in ("ACCEPT","REJECT"):
            return "INVALID"
        return verdict
    except (requests.RequestException,ValueError,KeyError,IndexError,TypeError,AttributeError):
        return "ERROR"

def remote_source(rows,marker):
    payload=[{k:r[k] for k in ("id","source","candidate")} for r in rows]
    return ("\n"+inspect.getsource(review_one)+"\n"
            +"review_rows=json.loads("+repr(json.dumps(payload,ensure_ascii=False))+")\n"
            +"from concurrent.futures import ThreadPoolExecutor,as_completed\n"
            +"with ThreadPoolExecutor(max_workers=4) as review_pool:\n"
            +"    review_futures={review_pool.submit(review_one,r,base):r['id'] for r in review_rows}\n"
            +"    for review_future in as_completed(review_futures):\n"
            +"        print("+repr(marker)+"+review_futures[review_future]+':'+review_future.result(),flush=True)\n")

def assess(rows,verdicts,emit=print):
    stats={"total":len(rows),"correct":0,"false_accept":0,"false_reject":0,"invalid":0}
    for row in rows:
        actual=verdicts.get(row["id"],"MISSING")
        expected=row["expected"]
        if actual==expected: stats["correct"]+=1
        elif actual=="ACCEPT": stats["false_accept"]+=1
        elif actual=="REJECT": stats["false_reject"]+=1
        else: stats["invalid"]+=1
        emit("SEMANTIC_REVIEW_ROW="+json.dumps({"id":row["id"],"category":row["category"],"expected":expected,"actual":actual}),flush=True)
    emit("SEMANTIC_REVIEW_SUMMARY="+json.dumps(stats),flush=True)
    # Small screening test, not proof of production accuracy.
    return 0 if stats["correct"]==stats["total"] else 1

def build_remote(tmp,payload,marker):
    cleanup_marker=None
    bootstrap=json.loads((tmp/"bootstrap.json").read_text())
    body="CONFIG="+repr(os.environ["REMOTE_CONFIG"])+"\nREVIEW_ONLY=True\n"
    for key in ("RCLONE_DRIVE_ID","RCLONE_ZIP_SHA","MANIFEST_SHA","CACHE_SPEC"):
        body+=key+"="+repr(bootstrap[key])+"\n"
    shared=os.environ.get("RO_REVIEW_SHARED_ROOT")
    if shared:
        body+="REVIEW_SHARED_ROOT="+repr(shared)+"\n"
    for name in ("colab-cache-mount.py","colab-benchmark-cache.py"):
        body+=(ROOT/name).read_text()+"\n"
    # Explicit process cleanup before the next model in the same VM.
    if shared:
        cleanup_marker=marker+"CLEANUP"
        body+="proc=None; root=None; server_log=None\ntry:\n"
        block=(ROOT/"colab-benchmark-model.py").read_text()+"\n"+payload
        body+="".join("    "+line+"\n" for line in block.splitlines())
        body+="finally:\n"
        body+="    child=globals().get('proc')\n"
        body+="    if child is not None and child.poll() is None:\n"
        body+="        child.terminate()\n"
        body+="        try: child.wait(timeout=30)\n"
        body+="        except subprocess.TimeoutExpired: child.kill(); child.wait(timeout=30)\n"
        body+="    if globals().get('server_log') is not None: server_log.close()\n"
        body+="    if globals().get('root') is not None: shutil.rmtree(root)\n"
        body+="    pathlib.Path(CONFIG).unlink(missing_ok=True)\n"
        body+="    shutil.rmtree(cache,ignore_errors=True)\n"
        body+="    print("+repr(cleanup_marker)+",flush=True)\n"
    else:
        body+=(ROOT/"colab-benchmark-model.py").read_text()+"\n"+payload
    return body,cleanup_marker

def main(tmp,session):
    tmp=pathlib.Path(tmp)
    spec=importlib.util.spec_from_file_location("kernel",ROOT/"colab-benchmark-kernel.py")
    kernel=importlib.util.module_from_spec(spec);spec.loader.exec_module(kernel)
    rows=selected_rows()
    ids={r["id"] for r in rows}
    marker="RO_REVIEW_"+uuid.uuid4().hex+"="
    body,cleanup_marker=build_remote(tmp,remote_source(rows,marker),marker)
    shared=os.environ.get("RO_REVIEW_SHARED_ROOT")
    compile(body,"semantic-review.py","exec")
    path=tmp/"semantic-review.py";path.write_text(body,encoding="utf-8")
    verdicts={}
    cleaned=False
    def on_line(line):
        nonlocal cleaned
        if shared and line==cleanup_marker:
            cleaned=True
            print("SEMANTIC_REVIEW_MODEL_RELEASED",flush=True)
            return
        match=re.fullmatch(re.escape(marker)+r"(\d{2}):(ACCEPT|REJECT|ERROR|INVALID)",line)
        if match:
            if match[1] not in ids or match[1] in verdicts:
                raise RuntimeError("REVIEW_RESULT_CONFLICT")
            verdicts[match[1]]=match[2]
            print(f"SEMANTIC_REVIEW_PROGRESS={len(verdicts)}/{len(rows)} id={match[1]} verdict={match[2]}",flush=True)
        else:
            kernel.safe_progress(line,print)
    print("SEMANTIC_REVIEW_MODEL="+os.environ.get("RO_REVIEW_MODEL","default"),flush=True)
    print("SEMANTIC_REVIEW_SCOPE="+os.environ.get("RO_REVIEW_SCOPE","all"),flush=True)
    print(f"SEMANTIC_REVIEW_START={len(rows)} TRANSLATION_REQUESTS=0",flush=True)
    args=["colab","--auth=adc","--config",str(tmp/"sessions.json"),"exec","-s",session,"--timeout","1500","-f",str(path)]
    rc,raw=kernel.invoke(args,1530,on_line=on_line,
        on_wait=lambda elapsed:print(f"SEMANTIC_REVIEW_WAIT elapsed={elapsed}s completed={len(verdicts)}/{len(rows)}",flush=True))
    if rc:
        kernel.report_failure("SEMANTIC_REVIEW",raw,kernel.assignment_count,print)
        return 2 if shared and not cleaned else 1
    if shared and not cleaned:
        print("SEMANTIC_REVIEW_CLEANUP_UNCONFIRMED",flush=True)
        return 2
    return assess(rows,verdicts)

if __name__=="__main__":
    raise SystemExit(main(*sys.argv[1:]))
