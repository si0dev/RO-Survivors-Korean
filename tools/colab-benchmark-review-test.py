import importlib.util,pathlib,unittest
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

if __name__=="__main__":
    unittest.main()
