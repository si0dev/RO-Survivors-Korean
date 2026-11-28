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
    def test_correction_consumes_draft(self):
        response=Mock()
        response.json.return_value={"choices":[{"message":{"content":"동빙 시간 +0.3초."},"finish_reason":"stop"}]}
        with patch.object(requests,"post",return_value=response) as post:
            value=c.correct_one({"source":"+0.3 s of freeze.","draft":"+0.3초 동안 동빙됩니다.","context":"talent"},"mock")
            self.assertEqual(value,"동빙 시간 +0.3초.")
            self.assertIn("+0.3초 동안 동빙됩니다.",post.call_args.kwargs["json"]["messages"][0]["content"])
if __name__=="__main__": unittest.main()
