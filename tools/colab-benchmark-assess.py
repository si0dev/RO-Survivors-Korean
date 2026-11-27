import json,sys,re,collections
refs=json.load(open(sys.argv[1]))
raw=open(sys.argv[2],errors="replace").read()
rows={}
for line in raw.splitlines():
    if "BENCHMARK_RESULT=" not in line: continue
    try: row,_=json.JSONDecoder().raw_decode(line.split("BENCHMARK_RESULT=",1)[1])
    except ValueError: continue
    if row["id"] in rows: raise SystemExit("Duplicate benchmark result")
    rows[row["id"]]=row
if set(rows)!={r["id"] for r in refs} or "BENCHMARK_DONE" not in raw:
    raise SystemExit(f"Incomplete benchmark: {len(rows)}/200")
def normalize(s): return re.sub(r"\s+","",s).casefold()
def similarity(a,b):
    a,b=normalize(a),normalize(b)
    def grams(s): return collections.Counter(s[i:i+2] for i in range(max(0,len(s)-1)))
    x,y=grams(a),grams(b)
    return 2*sum((x&y).values())/max(1,sum(x.values())+sum(y.values())) if min(len(a),len(b))>=2 else float(a==b)
stats=collections.defaultdict(collections.Counter)
for ref in refs:
    row=rows[ref["id"]]
    checks=row["checks"]
    ok=all(checks.values())
    exact=normalize(row["ko"])==normalize(ref["reference"])
    score=similarity(row["ko"],ref["reference"])
    s=stats[ref["group"]]
    s["total"]+=1;s["structural_pass"]+=ok;s["exact"]+=exact;s["first_attempt"]+=row["attempts"]==1
    for k,v in checks.items(): s[k+"_pass"]+=v
    # Only the selected benchmark rows, no raw game dump or credentials.
    print("BENCHMARK_ROW "+json.dumps({**ref,**row,"exact":exact,"bigram_similarity":round(score,3)},ensure_ascii=False))
total=collections.Counter()
for group,s in stats.items():
    total.update(s);print("BENCHMARK_GROUP "+json.dumps({"group":group,**s}))
print("BENCHMARK_SUMMARY "+json.dumps(dict(total)))
# Structural validation is not a semantic accuracy verdict; separately review outputs.
if total["structural_pass"]!=200: raise SystemExit("Some translations failed structural checks")
