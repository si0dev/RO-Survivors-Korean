"""Offline layout, shared engine reuse and runtime routing contract tests."""
import hashlib
import importlib.util
import json
import os
import pathlib
import runpy
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch

ROOT=pathlib.Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
from colab_cache_layout import DEFAULT, profile

class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=pathlib.Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.enterContext(patch.dict(os.environ,{"RO_CACHE_TMP":str(self.tmp),"RO_CACHE_PROFILE_JSON":""}))
        self.enterContext(patch.dict(sys.modules,{"requests":types.ModuleType("requests")}))
        spec=importlib.util.spec_from_file_location("populate",ROOT/"colab-cache-populate.py")
        self.p=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.p)
        self.enterContext(patch.object(self.p,"rc",side_effect=AssertionError("Unexpected remote call")))

    def test_paths(self):
        a=profile()
        b=profile(dict(DEFAULT,slug="test-model",quant="q4_k_m",repo="example/model",filename="test.gguf",min_bytes=1))
        self.assertTrue(a["model_remote"].endswith("/index-translate-9b-q6k-b12343-v1"))
        self.assertTrue(b["model_remote"].endswith("/models/test-model/q4_k_m"))
        self.assertEqual(a["engine_remote"],b["engine_remote"])
        self.assertNotEqual(a["engine_remote"],profile(dict(DEFAULT,slug="test-model",engine="b99999"))["engine_remote"])
        for bad in (dict(DEFAULT,slug="../bad"),dict(DEFAULT,filename="../bad.gguf"),dict(DEFAULT,quant="x/y")):
            with self.assertRaises(ValueError):
                profile(bad)

    def test_listing_excludes_legacy_engine(self):
        p=self.p
        model={p.MODEL:{"Size":1},"manifest.json":{},"llama.tar.gz":{"Size":2}}
        engine={"llama.tar.gz":{"Size":3},"cudart.tar.gz":{"Size":4}}
        with patch.object(p,"list_remote",side_effect=[model,engine]):
            self.assertEqual(p.listing()["llama.tar.gz"]["Size"],3)

    def test_promotion_copies_only_missing_verified_engine(self):
        p=self.p
        entries=[dict(kind="model",name=p.MODEL,size=7_000_000_001,sha256="a"*64,md5="b"*32),
                 dict(kind="llama",name="llama.tar.gz",size=10,sha256="c"*64,md5="d"*32),
                 dict(kind="cudart",name="cudart.tar.gz",size=12,sha256="e"*64,md5="f"*32)]
        d=dict(schema=2,repo=p.REPO,engine=p.TAG,revision="mock",files=entries)
        old={e["name"]:dict(Size=e["size"],Hashes={"SHA-256":e["sha256"],"MD5":e["md5"]}) for e in entries}
        existing={p.MODEL:old[p.MODEL],"cudart.tar.gz":old["cudart.tar.gz"]}
        with patch.object(p,"list_remote",return_value=old),patch.object(p,"listing",return_value=old),patch.object(p,"rc") as rc:
            self.assertEqual(p.promote_legacy_engine(d,existing),old)
            rc.assert_called_once_with("copyto",p.REMOTE+"/llama.tar.gz",p.ENGINE_REMOTE+"/llama.tar.gz","--checksum",limit=600)
        broken=dict(old);broken["llama.tar.gz"]={"Size":10,"Hashes":{"SHA-256":"0"*64}}
        with patch.object(p,"list_remote",return_value=broken):
            self.assertEqual(p.promote_legacy_engine(d,existing),existing)

    def test_runtime_uses_profile_paths(self):
        p=self.p
        ns=runpy.run_path(str(ROOT/"colab-benchmark-cache.py"),init_globals={"cache":self.tmp,"REMOTE":p.REMOTE,"CACHE_SPEC":p.SPEC,"RCLONE":"rclone"})
        self.assertEqual(ns["ENGINE_REMOTE"],p.ENGINE_REMOTE)
        # Exercise actual routing with a fake subprocess and verified local content.
        payload=b"fixture"
        class Process:
            stderr=iter(())
            def __init__(self,args,**kw):
                self.args=args
                pathlib.Path(args[5]).write_bytes(payload)
            def __enter__(self): return self
            def __exit__(self,*args): pass
            def wait(self,timeout=None): return 0
            def poll(self): return 0
        for kind,name,remote in (("llama","llama.tar.gz",p.ENGINE_REMOTE),("model",p.MODEL,p.REMOTE)):
            entry=dict(kind=kind,size=len(payload),sha256=hashlib.sha256(payload).hexdigest())
            with patch("subprocess.Popen",side_effect=Process) as popen:
                ns["copy_asset"]("config",name,self.tmp/"local",entry)
                self.assertEqual(popen.call_args.args[0][4],remote+"/"+name)

if __name__=="__main__":
    unittest.main()
