"""Compare all three model stages to the same live source and pinned approved data."""
import hashlib,importlib.util,json,pathlib,sys,unicodedata
from collections import Counter
from difflib import SequenceMatcher
ROOT=pathlib.Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location("pipeline",ROOT/"pipeline.py")
pipeline=importlib.util.module_from_spec(spec);spec.loader.exec_module(pipeline)
def read(p): return json.loads(p.read_text())
def norm(s): return " ".join(unicodedata.normalize("NFC",s).split())
def similarity(a,b): return SequenceMatcher(None,norm(a),norm(b),autojunk=False).ratio()
def collect(tmp):
    data=read(tmp/"audit-batch.json")
    rows=data["rows"];ids={r["id"] for r in rows}
    def by_id(file):
        values=read(tmp/file);result={r["id"]:r for r in values}
        if len(result)!=len(values) or set(result)!=ids: raise RuntimeError("AUDIT_MISSING_STAGE_ROWS")
        return result
    indexed=by_id("indexed.json");corrected=by_id("corrected.json");final=by_id("verified.json")
    verdicts=read(tmp/"audit-review.json")
    if not set(verdicts)<=ids: raise RuntimeError("AUDIT_UNKNOWN_VERDICT")
    metrics=Counter();details=[];examples=[]
    for row in rows:
        i=row["id"];a=indexed[i];b=corrected[i];c=final[i];v=verdicts.get(i,{})
        if any(x[k]!=row[k] for x in (a,b) for k in ("source","context","terms")): raise RuntimeError("AUDIT_SOURCE_CHANGED")
        ref=row["reference"];draft=a["draft"];correction=b["corrected"];selected=c["ko"]
        checks={name:pipeline.quality_checks(row["source"],value,row["terms"]) for name,value in (("index",draft),("hy",correction),("final",selected))}
        metrics["rows"]+=1
        metrics["reference_available"]+=ref is not None
        metrics["index_completed"]+=a["index_status"]=="COMPLETED"
        metrics["hy_completed"]+=b["correction_status"]=="COMPLETED"
        metrics["qwen_reviewed"]+=i in verdicts
        metrics["hy_changed"]+=draft!=correction
        for stage,verdict in (("index",v.get("original","NOT_RUN")),("hy",v.get("corrected","NOT_RUN"))):
            metrics[stage+"_blind_accept"]+=verdict=="ACCEPT"
            metrics[stage+"_blind_reject"]+=verdict=="REJECT"
            metrics[stage+"_blind_error_or_unrun"]+=verdict not in ("ACCEPT","REJECT")
            metrics[stage+"_combined_pass"]+=verdict=="ACCEPT" and all(checks[stage].values()) and (a["index_status"] if stage=="index" else b["correction_status"])=="COMPLETED"
        metrics["hy_semantic_improvement"]+=v.get("original")=="REJECT" and v.get("corrected")=="ACCEPT"
        metrics["hy_semantic_regression"]+=v.get("original")=="ACCEPT" and v.get("corrected")=="REJECT"
        metrics["final_model_verified"]+=c["status"]=="MODEL_VERIFIED"
        metrics["final_review_required"]+=c["status"]!="MODEL_VERIFIED"
        chosen="corrected" if selected and selected==correction and b["correction_status"]=="COMPLETED" else "original" if selected else None
        compare={"index":v.get("reference_original","NOT_RUN"),"hy":v.get("reference_corrected","NOT_RUN"),"final":v.get("reference_"+chosen,"NOT_RUN") if chosen else "NOT_RUN"}
        exact={};sim={}
        for stage,value in (("index",draft),("hy",correction),("final",selected)):
            metrics[stage+"_structure_pass"]+=all(checks[stage].values())
            for k,ok in checks[stage].items():
                if not ok: metrics[stage+"_failed_"+k]+=1
            if ref is not None:
                exact[stage]=norm(value)==norm(ref)
                sim[stage]=round(similarity(value,ref),6)
                metrics[stage+"_reference_exact"]+=exact[stage]
                metrics[stage+"_reference_"+compare[stage].lower()]+=1
        details.append({"id":i,"recordId":row["recordId"],"sourceHash":row["sourceHash"],"kind":row["kind"],"indexStatus":a["index_status"],"hyStatus":b["correction_status"],"blind":{k:v.get(k,"NOT_RUN") for k in ("original","corrected")},"referenceComparison":compare,"exact":exact,"similarity":sim,"checks":checks,"finalStatus":c["status"]})
        # A small set of diagnostics is enough for the public log; the full
        # extracted source, references, and generated candidates remain transient.
        severity=(3 if c["status"]!="MODEL_VERIFIED" else 0)+(3 if compare["final"]=="DIFFERENT" else 0)+(2 if compare["final"] in ("REFERENCE_ISSUE","UNSURE","ERROR") else 0)+(1 if v.get("original")=="ACCEPT" and v.get("corrected")=="REJECT" else 0)
        if severity:
            examples.append((severity,{"id":i,"kind":row["kind"],"source":row["source"][:450],"approved":ref[:450] if ref else None,"index":draft[:450],"hy":correction[:450],"final":selected[:450],"qwen":v,"status":c["status"],"checks":checks["final"]}))
    digest=hashlib.sha256(json.dumps([[r["id"],r["recordId"],r["sourceHash"]] for r in rows],separators=(",",":"),ensure_ascii=False).encode()).hexdigest()
    return {"build":data["build"],"batch":data["batch"],"count":len(rows),"digest":digest,"metrics":dict(metrics),"details":details,"examples":[e for _,e in sorted(examples,key=lambda x:-x[0])[:3]]}
if __name__=="__main__":
    tmp,out=map(pathlib.Path,sys.argv[1:])
    report=collect(tmp)
    out.mkdir(parents=True,exist_ok=True)
    (out/("result-"+report["batch"]+".json")).write_text(json.dumps(report,ensure_ascii=False))
    print("LIVE_AUDIT_BATCH_RESULT "+json.dumps({k:v for k,v in report.items() if k not in ("details","examples")},ensure_ascii=False),flush=True)
    for example in report["examples"]: print("LIVE_AUDIT_EXAMPLE "+json.dumps(example,ensure_ascii=False),flush=True)
