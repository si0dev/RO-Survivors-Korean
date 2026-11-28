import importlib.util,pathlib,unittest,json
from unittest.mock import Mock,patch
import requests
ROOT=pathlib.Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location("chain",ROOT/"colab-benchmark-chain.py")
c=importlib.util.module_from_spec(spec);spec.loader.exec_module(c)
class ChainTests(unittest.TestCase):
    def test_real_draft_selection(self):
        inputs=[{"id":"189","source":"+0.3 s of freeze.","context":"game","group":"ui"},{"id":"005","source":"fixed duration","context":"game","group":"skill"}]
        rows={i:{"ko":v,"checks":{"format":True}} for i,v in [("189","+0.3초 동안 동빙됩니다."),("005","고정 지속시간")]}
        selected=c.select_drafts(inputs,rows)
        self.assertEqual(selected[0]["draft"],rows["189"]["ko"])
        self.assertNotIn("reference",selected[0])
    def test_logged_actual_drafts_match_fixed_fixture(self):
        refs=c.read(ROOT/"colab-benchmark-fixture.json")["rows"]
        inputs=[{k:r[k] for k in ("id","source","group","context")} for r in refs]
        selected=c.restore_logged_drafts(inputs,refs)
        self.assertEqual([r["id"] for r in selected],["189","005"])
        self.assertEqual(selected[0]["draft"],"+0.3초 동안 얼음 상태가 됩니다.")
        self.assertEqual(selected[1]["draft"],"적 그룹에게 마법 모래를 던지면 2.5초 동안 잠들게 됩니다(보스는 절반 시간).")
        self.assertTrue(all("reference" not in r for r in selected))
        refs= [dict(r,source="wrong") if r["id"]=="189" else r for r in refs]
        with self.assertRaisesRegex(RuntimeError,"CHAIN_LOG_SOURCE_MISMATCH"):
            c.restore_logged_drafts(inputs,refs)
    def test_chained_payload(self):
        review=c.load("review",ROOT/"colab-benchmark-review.py")
        row={"id":"189","source":"source-example","draft":"original-draft","corrected":"corrected-draft","context":"game","reference":"secret-reference"}
        first=c.payload([row],"marker=","correct",review)
        second=c.payload([row],"marker=","verify",review)
        compile(first,"correct.py","exec");compile(second,"verify.py","exec")
        self.assertIn("original-draft",first)
        self.assertNotIn("corrected-draft",first)
        self.assertIn("corrected-draft",second)
        self.assertNotIn("original-draft",second)
        self.assertNotIn("secret-reference",first+second)
    def test_prefetch_and_execution_are_separate(self):
        import os,tempfile
        review=c.load("review",ROOT/"colab-benchmark-review.py")
        b={"RCLONE_DRIVE_ID":"fake","RCLONE_ZIP_SHA":"0"*64,"MANIFEST_SHA":"1"*64,"CACHE_SPEC":{}}
        prefetch=c.prefetch_source([("first",b),("second",b)],"/tmp/test-shared","/tmp/short.conf","done")
        compile(prefetch,"prefetch.py","exec")
        self.assertIn("copy_asset(CONFIG,entry",prefetch)
        self.assertNotIn("proc=subprocess.Popen",prefetch)
        with tempfile.TemporaryDirectory() as d:
            tmp=pathlib.Path(d)
            c.write(tmp/"bootstrap.json",b)
            with patch.dict(os.environ,{"RO_REVIEW_SHARED_ROOT":"/tmp/test-shared"}):
                body,marker=review.build_remote(tmp,"print('test')\n","marker=",preloaded=True)
            compile(body,"execute.py","exec")
            self.assertIn("PRELOADED_MODEL=True",body)
            self.assertNotIn("RCLONE_BOOTSTRAP_START",body)
            self.assertNotIn("def copy_asset(",body)
            self.assertNotIn("CONFIG=",body)
            self.assertIn("PRELOADED_MODEL_REUSED",body)
    def test_correction_consumes_draft(self):
        response=Mock()
        response.json.return_value={"choices":[{"message":{"content":"동빙 시간 +0.3초."},"finish_reason":"stop"}]}
        with patch.object(requests,"post",return_value=response) as post:
            value=c.correct_one({"source":"+0.3 s of freeze.","draft":"+0.3초 동안 동빙됩니다.","context":"talent"},"mock")
            self.assertEqual(value,"동빙 시간 +0.3초.")
            self.assertIn("+0.3초 동안 동빙됩니다.",post.call_args.kwargs["json"]["messages"][0]["content"])
if __name__=="__main__": unittest.main()
