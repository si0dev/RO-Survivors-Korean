import importlib.util,json,pathlib,tempfile,unittest,io,contextlib,sys,threading
ROOT=pathlib.Path(__file__).resolve().parent
def load(name):
    spec=importlib.util.spec_from_file_location(name,ROOT/(name+".py"))
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);return mod
k=load("colab-benchmark-kernel");ck=load("colab-benchmark-checkpoint")
INPUTS=[{"id":f"{i:03}","source":"test","context":"skill","group":"skill"} for i in range(1,201)]
MODEL="base='mock'\ndef translate_one(r,base):\n    return {'id':r['id'],'ko':'번역','checks':{k:True for k in ('hangul','placeholders','numbers','abbreviations','terms','format')},'attempts':1}\nprint('MODEL_READY',flush=True)\n"
def row(i):
    return {"id":f"{i:03}","ko":"번역","checks":{x:True for x in ck.CHECKS},"attempts":1}
class Store:
    def __init__(self):self.snapshots=[]
    def save(self,rows):self.snapshots.append(dict(rows))
class FakeKernel:
    def __init__(self,fail=None):self.ns={};self.calls=[];self.fail=fail
    def run(self,args,limit):
        assert args[0]=="colab" and "exec" in args and "download" not in args
        source=pathlib.Path(args[-1]).read_text()
        self.calls.append(source)
        out=io.StringIO()
        with contextlib.redirect_stdout(out):exec(source,self.ns)
        if self.fail==len(self.calls):
            return 1,out.getvalue().rsplit("RO_BATCH_DONE_",1)[0]+"File or directory not found\n"
        return 0,out.getvalue()
class KernelTests(unittest.TestCase):
    def execute(self,saved,fail=None):
        store=Store();kernel=FakeKernel(fail);out=[];probes=[]
        with tempfile.TemporaryDirectory() as t:
            log=pathlib.Path(t)/"translation.log"
            rc=k.collect(["colab"],"test",MODEL,log,INPUTS,saved,store,ck.validate_rows,
                run=kernel.run,probe=lambda:probes.append(0) or 0,emit=lambda s,**kw:out.append(s))
            return rc,log.read_text(),store,kernel,out,probes
    def test_restore_58_only_infer_142(self):
        saved={row(i)["id"]:row(i) for i in range(1,59)}
        rc,log,store,kernel,out,probes=self.execute(saved)
        self.assertEqual(rc,0)
        self.assertEqual(len(ck.rows_from_log(log.encode(),{r["id"] for r in INPUTS})),200)
        self.assertEqual(len(store.snapshots[-1]),200)
        self.assertEqual(len(kernel.calls),37)
        self.assertNotIn('"id": "058"',kernel.calls[1])
        self.assertIn("BENCHMARK_DONE",log)
        self.assertFalse(probes)
    def test_lost_batch_ack_saves_received_rows_and_reports_backend_count(self):
        rc,log,store,kernel,out,probes=self.execute({},2)
        self.assertEqual(rc,75)
        self.assertEqual(len(store.snapshots[-1]),4)
        self.assertEqual(len(kernel.calls),2)
        self.assertEqual(probes,[0])
        self.assertIn("COLAB_FAILURE_ACTIVE_ASSIGNMENTS=0",out)
        self.assertNotIn("BENCHMARK_DONE",log)
    def test_quota_and_permanent_errors_do_not_reallocate(self):
        emit=lambda *a,**kw:None
        for raw in ("quota exceeded","invalid_grant","permission denied","LOCAL_MODEL_HASH_MISMATCH"):
            self.assertEqual(k.report_failure("INIT",raw,lambda:0,emit),1)
        self.assertEqual(k.report_failure("BATCH","File or directory not found",lambda:1,emit),75)
        self.assertEqual(k.report_failure("INIT","unknown error",lambda:1,emit),1)
    def test_streaming_safe_output_and_timeout(self):
        seen=[]
        rc,raw=k.invoke([sys.executable,"-u","-c","import time;print('GPU_READY',flush=True);print('private',flush=True);time.sleep(5)"],1,on_line=lambda line:k.safe_progress(line,lambda s,**kw:seen.append(s)))
        self.assertEqual(rc,124)
        self.assertIn("GPU_READY",raw)
        self.assertEqual(seen,["GPU_READY"])
    def test_heartbeat_and_safe_retry_logs(self):
        seen=[]
        rc,raw=k.invoke([sys.executable,"-u","-c","import time;time.sleep(0.25)"],2,
            on_wait=seen.append,heartbeat=0.05)
        self.assertEqual(rc,0)
        self.assertTrue(seen)
        out=[]
        emit=lambda s,**kw:out.append(s)
        k.safe_progress('TRANSLATION_RETRY={"id":"001","attempt":1,"failures":["format"]}',emit)
        k.safe_progress('TRANSLATION_RETRY={"id":"secret","attempt":1,"failures":["format"]}',emit)
        self.assertEqual(len(out),1)
        self.assertIn("format",out[0])
    def test_remote_signal_states(self):
        clock=[0]
        signal=k.BatchSignal(now=lambda:clock[0])
        self.assertEqual(signal.status(),("COLAB_CONNECTION_UNVERIFIED",0,True))
        signal.observe()
        clock[0]=20
        self.assertEqual(signal.status(),("COLAB_TRANSLATION_WAIT",20,True))
        clock[0]=30
        self.assertEqual(signal.status(),("COLAB_CONNECTION_UNVERIFIED",30,True))
        clock[0]=120
        self.assertEqual(signal.status(),("COLAB_HEARTBEAT_TIMEOUT",120,False))
        signal.observe()
        self.assertEqual(signal.status(),("COLAB_TRANSLATION_WAIT",0,True))
    def test_missing_heartbeat_aborts_and_is_not_confirmed_disconnect(self):
        rc,raw=k.invoke([sys.executable,"-u","-c","import time;time.sleep(5)"],4,
            on_wait=lambda _:False,heartbeat=0.05)
        self.assertEqual(rc,124)
        self.assertIn("COLAB_HEARTBEAT_TIMEOUT",raw)
        out=[]
        emit=lambda s,**kw:out.append(s)
        self.assertEqual(k.report_failure("BATCH",raw,lambda:1,emit),75)
        self.assertTrue(any(s.startswith("COLAB_CONNECTION_UNVERIFIED") for s in out))
        self.assertFalse(any(s.startswith("COLAB_CONNECTION_LOST ") for s in out))
        out.clear()
        self.assertEqual(k.report_failure("BATCH","Connection was lost",lambda:1,emit),75)
        self.assertTrue(any(s.startswith("COLAB_CONNECTION_LOST ") for s in out))
    def test_four_way_concurrency_and_asynchronous_checkpoint(self):
        started=threading.Event()
        release=threading.Event()
        class SlowStore(Store):
            def save(self,rows):
                if len(rows)==4:
                    started.set()
                    if not release.wait(5): raise AssertionError("next batch did not overlap save")
                super().save(rows)
        class OverlapKernel(FakeKernel):
            def run(self,args,limit):
                if len(self.calls)==2:
                    if not started.wait(5): raise AssertionError("save did not start")
                    release.set()
                return super().run(args,limit)
        store=SlowStore();kernel=OverlapKernel()
        with tempfile.TemporaryDirectory() as t:
            rc=k.collect(["colab"],"test",MODEL,pathlib.Path(t)/"log",INPUTS,{},store,ck.validate_rows,run=kernel.run,probe=lambda:0,emit=lambda *a,**kw:None)
        self.assertEqual(rc,0)
        self.assertIn("max_workers=4",kernel.calls[1])
        self.assertIn("RO_BATCH_HEARTBEAT_",kernel.calls[1])
        self.assertEqual(len(store.snapshots[-1]),200)
    def test_completed_benchmark_does_not_contact_kernel(self):
        saved={row(i)["id"]:row(i) for i in range(1,201)}
        rc,log,store,kernel,out,probes=self.execute(saved)
        self.assertEqual(rc,0);self.assertFalse(kernel.calls)
        self.assertEqual(log.count("BENCHMARK_RESULT="),200)
if __name__=="__main__":unittest.main()
