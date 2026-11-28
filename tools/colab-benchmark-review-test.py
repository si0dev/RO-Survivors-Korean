import importlib.util,pathlib,unittest,json,os,subprocess,tempfile,re,contextlib,io
from unittest.mock import Mock,patch
import requests

path=pathlib.Path(__file__).with_name("colab-benchmark-review.py")
spec=importlib.util.spec_from_file_location("review",path)
r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)
class ReviewTests(unittest.TestCase):
    def test_balanced_blind_cases(self):
        rows=r.sample_rows()
        self.assertEqual(len(rows),12)
        self.assertEqual(len({x["id"] for x in rows}),12)
        self.assertEqual(sum(x["expected"]=="ACCEPT" for x in rows),6)
        remote=r.remote_source(rows,"marker=")
        compile(remote,"remote.py","exec")
        self.assertNotIn('"expected"',remote)
        self.assertNotIn('"category"',remote)
        self.assertNotIn("translate_one",remote)
    def test_targeted_scope_keeps_both_verdicts(self):
        with patch.dict(os.environ,{"RO_REVIEW_SCOPE":"duration"}):
            rows=r.selected_rows()
            self.assertEqual({x["id"] for x in rows},{"01","02"})
            self.assertEqual({x["expected"] for x in rows},{"ACCEPT","REJECT"})
            self.assertNotIn('"expected"',r.remote_source(rows,"marker="))
        with patch.dict(os.environ,{"RO_REVIEW_SCOPE":"all"}):
            self.assertEqual(len(r.selected_rows()),12)
        with patch.dict(os.environ,{"RO_REVIEW_SCOPE":"unknown"}):
            with self.assertRaises(ValueError): r.selected_rows()
    def test_verdict_strict_and_no_reference(self):
        row=r.sample_rows()[0]
        for answer,finish,expected in [("ACCEPT","stop","ACCEPT"),("REJECT","stop","REJECT"),
                ("ACCEPT because good","stop","INVALID"),("ACCEPT","length","INVALID")]:
            response=Mock(status_code=200)
            response.json.return_value={"choices":[{"message":{"content":answer},"finish_reason":finish}]}
            with patch.object(requests,"post",return_value=response) as post:
                self.assertEqual(r.review_one(row,"mock"),expected)
                prompt=post.call_args.kwargs["json"]["messages"][0]["content"]
                self.assertNotIn('"expected"',prompt)
                self.assertIn(row["source"],prompt)
                self.assertIn(row["candidate"],prompt)
                self.assertIn("变化量",prompt)
                self.assertIn("固定持续时间",prompt)
    def test_assessment_rejects_false_accept_and_invalid(self):
        rows=r.sample_rows()
        verdicts={x["id"]:x["expected"] for x in rows}
        emit=lambda *a,**kw:None
        self.assertEqual(r.assess(rows,verdicts,emit),0)
        bad=next(x for x in rows if x["expected"]=="REJECT")
        verdicts[bad["id"]]="ACCEPT"
        self.assertEqual(r.assess(rows,verdicts,emit),1)
        verdicts[bad["id"]]="INVALID"
        self.assertEqual(r.assess(rows,verdicts,emit),1)

    def test_shared_remote_body_and_cleanup_gate(self):
        rows=r.sample_rows()
        with tempfile.TemporaryDirectory() as d:
            tmp=pathlib.Path(d)
            (tmp/"bootstrap.json").write_text(json.dumps({"RCLONE_DRIVE_ID":"fake","RCLONE_ZIP_SHA":"0"*64,"MANIFEST_SHA":"1"*64,"CACHE_SPEC":{}}))
            for cleanup,expected in ((True,0),(False,2)):
                fake=Mock()
                def invoke(args,limit,on_line,on_wait):
                    body=pathlib.Path(args[-1]).read_text()
                    compile(body,"remote.py","exec")
                    self.assertIn("REVIEW_SHARED_ROOT=",body)
                    self.assertIn("child.wait(timeout=30)",body)
                    self.assertNotIn('"expected"',body)
                    marker=re.search(r"RO_REVIEW_[a-f0-9]{32}=",body).group()
                    for row in rows: on_line(marker+row["id"]+":"+row["expected"])
                    if cleanup: on_line(marker+"CLEANUP")
                    return 0,""
                fake.invoke.side_effect=invoke
                loader=Mock()
                with patch.object(r.importlib.util,"spec_from_file_location",return_value=loader), patch.object(r.importlib.util,"module_from_spec",return_value=fake), patch.dict(os.environ,{"REMOTE_CONFIG":"/tmp/test.conf","RO_REVIEW_SHARED_ROOT":"/tmp/test-shared","RO_REVIEW_SCOPE":"all"}), contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(r.main(tmp,"one-session"),expected)
    def test_comparison_profiles_and_shell_syntax(self):
        profiles=json.loads((r.ROOT/"colab-benchmark-profiles.json").read_text())
        self.assertEqual(len(profiles),3)
        self.assertEqual(len({x["name"] for x in profiles}),3)
        self.assertEqual(len({x["profile"]["engine"] for x in profiles}),1)
        subprocess.run(["bash","-n",str(r.ROOT/"colab-benchmark-workflow.sh")],check=True)
        compile((r.ROOT/"colab-cache-populate.py").read_text(),"cache-populate.py","exec")
        workflow=(r.ROOT.parent/".github/workflows/colab-smoke.yml").read_text()
        self.assertNotIn("matrix:",workflow)
        self.assertEqual(workflow.count("prepare_comparison_model_cache "),3)
        self.assertEqual(workflow.count("run_comparison_model "),3)
        self.assertEqual(workflow.count("allocate_comparison_session"),1)
        self.assertIn("summarize_comparison",workflow)
        self.assertIn("steps.review_index.outputs.safe_to_continue",workflow)
        self.assertIn("steps.review_hymt.outputs.safe_to_continue",workflow)
        self.assertIn("RO_REVIEW_COMPARISON: '1'",workflow)

    def test_session_survives_distinct_workflow_shells(self):
        with tempfile.TemporaryDirectory() as d:
            tmp=pathlib.Path(d)/"ro-colab-state"; tmp.mkdir()
            output=pathlib.Path(d)/"outputs"
            env=dict(os.environ,RUNNER_TEMP=d,GITHUB_RUN_ID="100",GITHUB_RUN_ATTEMPT="1",GITHUB_OUTPUT=str(output))
            source='source "$1"; shift; '
            script=str(r.ROOT/"colab-benchmark-workflow.sh")
            names=[x["name"] for x in json.loads((r.ROOT/"colab-benchmark-profiles.json").read_text())]
            (tmp/"profiles.tsv").write_text("".join(n+"\t{}\n" for n in names))
            for n in names: (tmp/("bootstrap-"+n+".json")).write_text("{}")
            def shell(code,*args):
                return subprocess.run(["bash","-c",source+code,"test",script,*args],env=env,capture_output=True,text=True)
            result=shell('allocate_gpu() { echo allocated >> "$tmp/count"; printf "{}" > "$tmp/sessions.json"; }; allocate_comparison_session')
            self.assertEqual(result.returncode,0,result.stderr)
            for n in names:
                result=shell('run_session() { test "$allocation_ready" = 1; test "$gpu" = "ro-translate-100-1"; session_rc=0; }; run_comparison_model "$1"',n)
                self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual((tmp/"count").read_text().splitlines(),["allocated"])
            self.assertEqual(output.read_text().splitlines().count("safe_to_continue=true"),3)
            self.assertEqual(shell("summarize_comparison").returncode,0)

if __name__=="__main__":
    unittest.main()
