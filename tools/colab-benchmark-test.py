import contextlib
import importlib.util
import io
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock,patch
import requests

ROOT=pathlib.Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location("translate",ROOT/"colab-benchmark-translate.py")
mod=importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
BASE="http://127.0.0.1:18080"
ROW={"id":"001","source":"Deals 120% ATK damage.","context":"skill","group":"skill"}
KO="120% ATK 피해를 줍니다."
def response(status=200,content=KO,finish="stop"):
    r=Mock(status_code=status)
    r.json.return_value={"choices":[{"message":{"content":content},"finish_reason":finish}]}
    return r

class TranslationTests(unittest.TestCase):
    def run_row(self,side_effect):
        out=[]
        with patch.object(mod.requests,"post",side_effect=side_effect) as post:
            result=mod.translate_one(ROW,BASE,lambda s,**kw:out.append(s),lambda _:None)
        return result,post,out
    def test_valid_request(self):
        row,post,_=self.run_row([response()])
        self.assertTrue(all(row["checks"].values()))
        self.assertEqual(row["attempts"],1)
        self.assertEqual(post.call_args.args[0],BASE+"/v1/chat/completions")
        self.assertFalse(post.call_args.kwargs["json"]["stream"])
    def test_timeout_and_503_retry(self):
        row,_,out=self.run_row([requests.Timeout(),response(503),response()])
        self.assertEqual(row["attempts"],3)
        self.assertIn("HTTP_TIMEOUT",out[0])
        self.assertIn('"status": 503',out[1])
    def test_quality_repair(self):
        row,post,_=self.run_row([response(content="피해를 줍니다."),response()])
        self.assertEqual(row["attempts"],2)
        self.assertTrue(all(row["checks"].values()))
        self.assertIn("numbers",post.call_args.kwargs["json"]["messages"][0]["content"])
    def test_source_is_last_and_short_output_budget(self):
        short=dict(ROW,source="Frost")
        _,prompt,_=mod.request_for(short,["format","numbers"])
        self.assertTrue(prompt.endswith("〖源文〗Frost"))
        self.assertEqual(mod.initial_token_budget("Frost"),64)
    def test_instruction_echo_retries_without_accepting_extra_text(self):
        bad="120% ATK 피해를 줍니다. 〖주의사항〗"
        row,post,out=self.run_row([response(content=bad),response()])
        self.assertEqual(row["attempts"],2)
        self.assertEqual(row["ko"],KO)
        self.assertTrue(all(row["checks"].values()))
        self.assertIn("TRANSLATION_RETRY=",out[0])
        self.assertTrue(post.call_args.kwargs["json"]["messages"][0]["content"].endswith(ROW["source"]))
    def test_truncation_repair(self):
        row,post,_=self.run_row([response(finish="length"),response()])
        self.assertEqual(row["attempts"],2)
        self.assertEqual(post.call_args.kwargs["json"]["max_tokens"],2*mod.initial_token_budget(ROW["source"]))
    def test_persistent_truncation_counts_as_failure(self):
        row,_,_=self.run_row([response(finish="length") for _ in range(3)])
        self.assertFalse(row["checks"]["format"])
        self.assertEqual(row["attempts"],3)
    def test_bad_request_fails_without_retry(self):
        out=[]
        with patch.object(mod.requests,"post",return_value=response(400)) as post:
            with self.assertRaises(mod.TranslationFailure):
                mod.translate_one(ROW,BASE,lambda s,**kw:out.append(s),lambda _:None)
        self.assertEqual(post.call_count,1)
        self.assertIn('"status": 400',out[0])
    def test_malformed_response(self):
        r=response();r.json.return_value={}
        with patch.object(mod.requests,"post",return_value=r):
            with self.assertRaisesRegex(mod.TranslationFailure,"RESPONSE_SCHEMA"):
                mod.generate_one([],BASE)
    def test_reference_not_sent(self):
        with self.assertRaisesRegex(RuntimeError,"INVALID_BENCHMARK_INPUT"):
            mod.translate_samples([dict(ROW,reference=KO)],BASE)
    def test_200_rows_and_assessment(self):
        rows=[dict(ROW,id=f"{i+1:03}") for i in range(200)]
        buf=io.StringIO()
        with patch.object(mod.requests,"post",side_effect=lambda *a,**kw:response()),contextlib.redirect_stdout(buf):
            mod.translate_samples(rows,BASE)
        raw=buf.getvalue()
        self.assertEqual(raw.count("BENCHMARK_RESULT="),200)
        self.assertIn("TRANSLATION_PROGRESS 200/200",raw)
        self.assertIn("BENCHMARK_DONE",raw)
        with tempfile.TemporaryDirectory() as tmp:
            refs=pathlib.Path(tmp)/"refs.json";log=pathlib.Path(tmp)/"run.log"
            refs.write_text(json.dumps([dict(r,reference=KO) for r in rows]))
            log.write_text(raw)
            result=subprocess.run([sys.executable,str(ROOT/"colab-benchmark-assess.py"),str(refs),str(log)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertIn('"structural_pass": 200',result.stdout)
    def test_persistent_connection_error_is_bounded(self):
        with patch.object(mod.requests,"post",side_effect=requests.ConnectionError()) as post:
            with self.assertRaisesRegex(mod.TranslationFailure,"HTTP_CONNECTION"):
                mod.translate_one(ROW,BASE,lambda *a,**kw:None,lambda _:None)
            self.assertEqual(post.call_count,3)

if __name__=="__main__":
    unittest.main()
