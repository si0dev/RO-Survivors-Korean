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
    def test_equivalent_numeric_expressions(self):
        pairs=[
            ("repeats 2 more times, once per second, with 30% healing","1초에 한 번씩 2회 더 반복되며 회복량은 30%"),
            ("up to double within 6 m","6m 이내에서 최대 2배"),
            ("One primary stat + crit","주 스탯 1개 + 크리티컬"),
            ("at most 4 or 8; each boss drops at most one","최대 4개 또는 8개, 보스는 최대 1개"),
            ("half per level of difference","레벨 차이 1당 절반"),
            ("100 points halve cooldowns; 300 leave a quarter","100포인트면 절반, 300포인트면 4분의 1"),
            ("within the first minute","첫 1분 이내"),
            ("two columns","2열"),
            ("1M","100만"),("2.5M","250만"),("2B","20억"),
        ]
        for source,ko in pairs:
            with self.subTest(source=source):
                self.assertTrue(mod.check_output(source,ko,mod.required_terms(source))["numbers"])
    def test_numbers_still_reject_real_errors(self):
        for source,ko in [
            ("+0.3 s of freeze.","0.3초 동안 동빙"),
            ("6 m, up to double","5m, 최대 2배"),
            ("two columns","3열"),
            ("1M","10만"),
            ("Deals 10% damage","피해량 10"),
            ("Deals 10% damage","피해량 10%, 1회"),
            ("double damage","피해량 2배, 2배"),
            ("one primary stat + 2 ATK","주 스탯 1개 + 3 ATK"),
        ]:
            with self.subTest(source=source):
                self.assertFalse(mod.check_output(source,ko,mod.required_terms(source))["numbers"])
        self.assertFalse(mod.check_output("+2 armor · +2 INT","방어력 +2 · 지능 +2",{})["abbreviations"])
        self.assertFalse(mod.check_output("1M","1M",{})["hangul"])
    def test_targeted_retry_instructions(self):
        _,prompt,_=mod.request_for(dict(ROW,source="+2 INT"),["numbers","abbreviations"])
        self.assertIn("+2",prompt)
        self.assertIn("INT",prompt)
        self.assertIn("不可译成全称",prompt)
        self.assertTrue(prompt.endswith("〖源文〗+2 INT"))
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
