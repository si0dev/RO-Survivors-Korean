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

def review_one(row,base):
    import json,requests
    prompt=("你是英韩游戏翻译审校员。只判断韩语译文是否保留英文原文的游戏效果和条件。"
            "仔细核对增减、时长变化与固定时长、目标、触发条件、频率、否定和数值。"
            "不要因措辞不同而判错。语义正确输出 ACCEPT，语义错误输出 REJECT。"
            "只输出一个英文标签，不要翻译、解释或输出其他内容。\n"
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

def main(tmp,session):
    tmp=pathlib.Path(tmp)
    spec=importlib.util.spec_from_file_location("kernel",ROOT/"colab-benchmark-kernel.py")
    kernel=importlib.util.module_from_spec(spec);spec.loader.exec_module(kernel)
    rows=sample_rows()
    ids={r["id"] for r in rows}
    marker="RO_REVIEW_"+uuid.uuid4().hex+"="
    bootstrap=json.loads((tmp/"bootstrap.json").read_text())
    body="CONFIG="+repr(os.environ["REMOTE_CONFIG"])+"\n"
    for key in ("RCLONE_DRIVE_ID","RCLONE_ZIP_SHA","MANIFEST_SHA"):
        body+=key+"="+repr(bootstrap[key])+"\n"
    for name in ("colab-cache-mount.py","colab-benchmark-cache.py","colab-benchmark-model.py"):
        body+=(ROOT/name).read_text()+"\n"
    body+=remote_source(rows,marker)
    compile(body,"semantic-review.py","exec")
    path=tmp/"semantic-review.py";path.write_text(body,encoding="utf-8")
    verdicts={}
    def on_line(line):
        match=re.fullmatch(re.escape(marker)+r"(\d{2}):(ACCEPT|REJECT|ERROR|INVALID)",line)
        if match:
            if match[1] not in ids or match[1] in verdicts:
                raise RuntimeError("REVIEW_RESULT_CONFLICT")
            verdicts[match[1]]=match[2]
            print(f"SEMANTIC_REVIEW_PROGRESS={len(verdicts)}/{len(rows)} id={match[1]} verdict={match[2]}",flush=True)
        else:
            kernel.safe_progress(line,print)
    print(f"SEMANTIC_REVIEW_START={len(rows)} TRANSLATION_REQUESTS=0",flush=True)
    args=["colab","--auth=adc","--config",str(tmp/"sessions.json"),"exec","-s",session,"--timeout","1500","-f",str(path)]
    rc,raw=kernel.invoke(args,1530,on_line=on_line,
        on_wait=lambda elapsed:print(f"SEMANTIC_REVIEW_WAIT elapsed={elapsed}s completed={len(verdicts)}/{len(rows)}",flush=True))
    if rc:
        kernel.report_failure("SEMANTIC_REVIEW",raw,kernel.assignment_count,print)
        return 1
    return assess(rows,verdicts)

if __name__=="__main__":
    raise SystemExit(main(*sys.argv[1:]))
