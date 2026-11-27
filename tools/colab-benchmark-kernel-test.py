import importlib.util,json,pathlib,tempfile,unittest,io,contextlib
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
        self.assertEqual(rc,1)
        self.assertEqual(len(store.snapshots[-1]),4)
        self.assertEqual(len(kernel.calls),2)
        self.assertEqual(probes,[0])
        self.assertIn("COLAB_FAILURE_ACTIVE_ASSIGNMENTS=0",out)
        self.assertNotIn("BENCHMARK_DONE",log)
    def test_completed_benchmark_does_not_contact_kernel(self):
        saved={row(i)["id"]:row(i) for i in range(1,201)}
        rc,log,store,kernel,out,probes=self.execute(saved)
        self.assertEqual(rc,0);self.assertFalse(kernel.calls)
        self.assertEqual(log.count("BENCHMARK_RESULT="),200)
if __name__=="__main__":unittest.main()
