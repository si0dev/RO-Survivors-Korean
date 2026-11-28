import importlib.util,pathlib,unittest
ROOT=pathlib.Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location("pipeline",ROOT/"pipeline.py")
p=importlib.util.module_from_spec(spec);spec.loader.exec_module(p)
class Contract(unittest.TestCase):
    def test_payloads_and_reference_isolation(self):
        row={"id":"1","source":"Damage +2","context":"game","terms":{},"draft":"피해 +2","corrected":"피해량 +2","reference":"SECRET"}
        review=p.load("colab-review")
        for stage in ("index","correct","verify"):
            code=p.payload([row],"marker=",stage,review)
            compile(code,stage,"exec")
            self.assertNotIn("SECRET",code)
        self.assertNotIn('"draft"',p.payload([row],"marker=","index",review).split("rows=json.loads(")[1])
    def test_audit_reference_isolation(self):
        row={"id":"1","source":"Damage +2","context":"game","terms":{},"draft":"피해 +2","corrected":"피해량 +2"}
        review=p.load("colab-review")
        for stage in ("index","correct","verify"):
            code=p.payload([row],"marker=",stage,review,{"1":"PRIVATE_BASELINE"})
            compile(code,stage,"exec")
            self.assertEqual("PRIVATE_BASELINE" in code,stage=="verify")
        code=p.payload([row],"marker=","verify",review)
        self.assertNotIn("audit_reference",code)
    def test_gate_and_fallback(self):
        row={"id":"1","source":"Damage +2","terms":{},"draft":"피해 +2","corrected":"피해 +3","index_status":"COMPLETED","correction_status":"COMPLETED"}
        self.assertEqual(p.choose(row,{"original":"ACCEPT","corrected":"ACCEPT"})["ko"],row["draft"])
        self.assertEqual(p.choose(row,{"original":"REJECT","corrected":"ACCEPT"})["status"],"REVIEW_REQUIRED")
        row["corrected"]="피해량 +2"
        self.assertEqual(p.choose(row,{"original":"REJECT","corrected":"ACCEPT"})["ko"],row["corrected"])
    def test_approved_term_required(self):
        self.assertFalse(p.quality_checks("Haste","재빠름",{"Haste":"가속"})["terms"])
        self.assertTrue(p.quality_checks("Haste","가속",{"Haste":"가속"})["terms"])
if __name__=="__main__":unittest.main()
