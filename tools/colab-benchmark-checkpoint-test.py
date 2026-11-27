import contextlib,importlib.util,io,json,pathlib,subprocess,sys,tempfile,unittest
from unittest.mock import patch
ROOT=pathlib.Path(__file__).resolve().parent
def load(name):
    spec=importlib.util.spec_from_file_location(name,ROOT/(name+".py"))
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);return mod
ck=load("colab-benchmark-checkpoint")
tr=load("colab-benchmark-translate")
ids={f"{i:03}" for i in range(1,201)}
key="a"*64
source="Deals 120% ATK damage."
ko="120% ATK 피해를 줍니다."
def row(i):
    return {"id":f"{i:03}","ko":ko,"checks":{k:True for k in ck.CHECKS},"attempts":1}
def raw(rows):
    return b"".join(b"BENCHMARK_RESULT="+ck.canonical(r)+b"\n" for r in rows)
class FakeDrive:
    def __init__(self): self.files={};self.fail=False
    def run(self,*args):
        op=args[0]
        if op=="mkdir": return b""
        if op=="lsjson": return ck.canonical([{"Name":p.rsplit("/",1)[1]} for p in self.files if p.startswith(args[1]+"/")])
        if op=="cat": return self.files[args[1]]
        if op=="copyto":
            if self.fail: raise RuntimeError("CHECKPOINT_DRIVE_IO")
            self.files[args[2]]=pathlib.Path(args[1]).read_bytes();return b""
        raise AssertionError(op)
class CheckpointTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.drive=FakeDrive()
        self.store=ck.Store("",key,ids,pathlib.Path(self.tmp.name)/"upload.json",self.drive.run)
    def test_restart_restores_verified_60_and_adds_140(self):
        saved=ck.advance(self.store,{},raw([row(i) for i in range(1,61)]))
        self.assertEqual(len(saved),60)
        restored=self.store.restore()
        self.assertEqual(saved,restored)
        samples=[{"id":f"{i:03}","source":source,"group":"skill","context":"skill"} for i in range(1,201)]
        buf=io.StringIO()
        calls=[]
        def translate(r,*a):
            calls.append(r["id"]);return row(int(r["id"]))
        with patch.object(tr,"translate_one",side_effect=translate),contextlib.redirect_stdout(buf):
            tr.translate_samples(samples,"mock",resume=list(restored.values()))
        self.assertEqual(len(calls),140)
        self.assertEqual(set(calls),ids-set(restored))
        final=ck.advance(self.store,restored,buf.getvalue().encode())
        self.assertEqual(len(final),200)
        self.assertEqual(self.store.restore(),final)
        self.assertIn("BENCHMARK_DONE",buf.getvalue())
        refs=pathlib.Path(self.tmp.name)/"refs.json";log=refs.with_name("log")
        refs.write_text(json.dumps([dict(r,reference=ko) for r in samples]))
        log.write_text(buf.getvalue())
        r=subprocess.run([sys.executable,str(ROOT/"colab-benchmark-assess.py"),str(refs),str(log)],capture_output=True,text=True)
        self.assertEqual(r.returncode,0,r.stderr)
    def test_partial_line_not_committed(self):
        self.assertEqual(len(ck.advance(self.store,{},raw([row(1)])+b'BENCHMARK_RESULT={"id":')),1)
    def test_failed_upload_keeps_previous_snapshot(self):
        a=ck.advance(self.store,{},raw([row(1)]))
        self.drive.fail=True
        with self.assertRaisesRegex(RuntimeError,"CHECKPOINT_DRIVE_IO"):
            ck.advance(self.store,a,raw([row(1),row(2)]))
        self.assertEqual(self.store.restore(),a)
    def test_corrupt_latest_falls_back(self):
        a=ck.advance(self.store,{},raw([row(1)]))
        ck.advance(self.store,a,raw([row(1),row(2)]))
        latest=next(p for p in self.drive.files if "/002-" in p)
        self.drive.files[latest]=b"bad"
        self.assertEqual(self.store.restore(),a)
    def test_fingerprint_mismatch_and_duplicate_rejected(self):
        with self.assertRaisesRegex(ValueError,"CHECKPOINT_FINGERPRINT"):
            ck.decode(ck.encode(key,{"001":row(1)}),"b"*64,ids)
        with self.assertRaisesRegex(ValueError,"CHECKPOINT_ROW_ID"):
            ck.rows_from_log(raw([row(1),row(1)]),ids)
    def test_conflicting_replayed_row_is_rejected(self):
        a=ck.advance(self.store,{},raw([row(1)]))
        with self.assertRaisesRegex(RuntimeError,"CHECKPOINT_RESULT_CONFLICT"):
            ck.advance(self.store,a,raw([dict(row(1),ko="다름")]))
    def test_changed_input_or_model_invalidates_fingerprint(self):
        manifest={"engine":"b12343","repo":"Index","files":[{"kind":"model","name":"m","size":10,"sha256":"a"*64}]}
        a=ck.fingerprint([1],[2],manifest,{"script":"a"})
        self.assertNotEqual(a,ck.fingerprint([3],[2],manifest,{"script":"a"}))
        self.assertNotEqual(a,ck.fingerprint([1],[2],manifest,{"script":"b"}))
        manifest["files"][0]["sha256"]="b"*64
        self.assertNotEqual(a,ck.fingerprint([1],[2],manifest,{"script":"a"}))
    def test_replay_does_not_overwrite_or_duplicate(self):
        saved=ck.advance(self.store,{},raw([row(1),row(2)]))
        self.assertEqual(ck.advance(self.store,saved,raw([row(1)])),saved)
        self.assertEqual(len(self.drive.files),1)
    def test_all_completed_no_translation_calls(self):
        samples=[{"id":f"{i:03}","source":source,"context":"skill"} for i in range(1,201)]
        with patch.object(tr,"translate_one") as call,contextlib.redirect_stdout(io.StringIO()):
            tr.translate_samples(samples,"mock",resume=[row(i) for i in range(1,201)])
            call.assert_not_called()
if __name__=="__main__": unittest.main()
