"""Offline regression tests for the actual Colab cache and OAuth scripts."""
import configparser
import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import runpy
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch

TOOLS = Path(__file__).resolve().parents[1] / "tools"


def load(name):
    spec = importlib.util.spec_from_file_location(name, TOOLS / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Offline(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.enterContext(patch.dict(os.environ, {"RO_CACHE_TMP": str(self.tmp)}))
        self.requests = types.ModuleType("requests")
        self.requests.get = Mock(side_effect=AssertionError("Unexpected network GET"))
        self.requests.post = Mock(side_effect=AssertionError("Unexpected network POST"))
        self.enterContext(patch.dict(sys.modules, {"requests": self.requests}))
        self.enterContext(patch("socket.socket", side_effect=AssertionError("Network prohibited")))
        self.enterContext(patch("subprocess.Popen", side_effect=AssertionError("External process prohibited")))
        self.log = self.enterContext(contextlib.redirect_stdout(io.StringIO()))


class CacheTests(Offline):
    def setUp(self):
        super().setUp()
        self.populate = load("colab-cache-populate")
        self.model = self.populate.MODEL
        self.entries = [
            {"kind": "model", "name": self.model, "size": 7_000_000_001,
             "sha256": "a" * 64, "md5": "a" * 32},
            {"kind": "llama", "name": "llama.tar.gz", "size": 3,
             "sha256": hashlib.sha256(b"abc").hexdigest(), "md5": hashlib.md5(b"abc").hexdigest()},
            {"kind": "cudart", "name": "cudart.tar.gz", "size": 3,
             "sha256": hashlib.sha256(b"def").hexdigest(), "md5": hashlib.md5(b"def").hexdigest()},
        ]
        self.manifest = {"schema": 2, "repo": self.populate.REPO, "engine": self.populate.TAG,
                         "revision": "mock", "files": self.entries}
        self.files = {e["name"]: {"Size": e["size"], "Hashes": {"SHA-256": e["sha256"], "MD5": e["md5"]}}
                      for e in self.entries}

    def runtime(self, mounted=True):
        # Execute the same cache script concatenated into the real benchmark.
        with patch("os.path.ismount", return_value=mounted):
            return runpy.run_path(str(TOOLS / "colab-benchmark-cache.py"), init_globals={"MOUNT": self.tmp})

    def local_files(self):
        # Sparse file: no multi-GB download or allocation; only the header is read.
        with (self.tmp / self.model).open("wb") as out:
            out.write(b"GGUF")
            out.truncate(self.entries[0]["size"])
        (self.tmp / "llama.tar.gz").write_bytes(b"abc")
        (self.tmp / "cudart.tar.gz").write_bytes(b"def")
        (self.tmp / "manifest.json").write_text(json.dumps(self.manifest))

    def test_runtime_valid_manifest(self):
        self.local_files()
        self.assertEqual(self.runtime()["verified_manifest"](), self.manifest)

    def test_runtime_mount_missing(self):
        with self.assertRaisesRegex(AssertionError, "DRIVE_NOT_MOUNTED"):
            self.runtime(mounted=False)

    def test_runtime_manifest_missing(self):
        self.assertIsNone(self.runtime()["verified_manifest"]())

    def test_runtime_manifest_invalid_json(self):
        (self.tmp / "manifest.json").write_text("{broken")
        with self.assertRaises(json.JSONDecodeError):
            self.runtime()["verified_manifest"]()

    def test_runtime_file_missing(self):
        self.local_files()
        (self.tmp / "llama.tar.gz").unlink()
        with self.assertRaisesRegex(AssertionError, "CACHE_SIZE_MISMATCH"):
            self.runtime()["verified_manifest"]()

    def test_runtime_file_wrong_size(self):
        self.local_files()
        (self.tmp / "cudart.tar.gz").write_bytes(b"x")
        with self.assertRaisesRegex(AssertionError, "CACHE_SIZE_MISMATCH"):
            self.runtime()["verified_manifest"]()

    def test_runtime_model_header_corrupt(self):
        self.local_files()
        with (self.tmp / self.model).open("r+b") as out:
            out.write(b"BAD!")
        with self.assertRaises(AssertionError):
            self.runtime()["verified_manifest"]()

    def test_remote_valid_manifest(self):
        self.assertTrue(self.populate.valid(self.manifest, self.files))

    def test_remote_same_size_corruption_rejected(self):
        for entry in self.entries:
            with self.subTest(kind=entry["kind"]):
                files = dict(self.files)
                files[entry["name"]] = {"Size": entry["size"], "Hashes": {"SHA-256": "0" * 64}}
                self.assertFalse(self.populate.valid(self.manifest, files))

    def test_remote_missing_file_rejected(self):
        files = dict(self.files)
        del files[self.model]
        self.assertFalse(self.populate.valid(self.manifest, files))

    def exercise_repair(self, corrupt_manifest=None, damaged=None, download_bytes=None):
        # Simulate Drive's directory, upload verification, and manifest publication.
        files = dict(self.files)
        raw = json.dumps(self.manifest).encode() if corrupt_manifest is None else corrupt_manifest
        files["manifest.json"] = {}
        if damaged == "missing":
            del files["llama.tar.gz"]
        elif damaged == "hash":
            files["llama.tar.gz"] = {"Size": 3, "Hashes": {"SHA-256": "0"*64, "MD5": "0"*32}}
        elif damaged == "size":
            files["llama.tar.gz"] = {"Size": 2, "Hashes": {}}
        uploads = []
        def rc(*args, **kwargs):
            nonlocal raw
            if args[0] == "mkdir": return b""
            if args[0] == "cat" and args[1].endswith("/manifest.json"): return raw
            if args[0] == "copyto":
                name = args[2].rsplit("/",1)[-1]
                data = Path(args[1]).read_bytes()
                uploads.append(name)
                if name == "manifest.json":
                    raw = data
                else:
                    files[name] = {"Size":len(data),"Hashes":{
                        "SHA-256":hashlib.sha256(data).hexdigest(),"MD5":hashlib.md5(data).hexdigest()}}
                return b""
            self.fail("Unexpected remote operation: " + args[0])
        if download_bytes is not None:
            response=Mock()
            response.__enter__=Mock(return_value=response)
            response.__exit__=Mock(return_value=False)
            response.iter_content.return_value=[download_bytes]
            self.requests.get.side_effect=None
            self.requests.get.return_value=response
        with patch.object(self.populate,"listing",side_effect=lambda:dict(files)), \
             patch.object(self.populate,"metadata",return_value=("mock",[(dict(e),e["name"]) for e in self.entries])), \
             patch.object(self.populate,"rc",side_effect=rc), \
             patch.object(self.populate,"remote_digest") as digest:
            if download_bytes == b"bad":
                with self.assertRaisesRegex(AssertionError,"DOWNLOAD_HASH_MISMATCH"):
                    self.populate.main()
                self.assertEqual(uploads,[])
                self.assertFalse((self.tmp/"llama.tar.gz").exists())
                return
            self.populate.main()
            self.assertEqual(json.loads(raw),self.manifest)
            self.assertTrue(self.populate.valid(json.loads(raw),files))
            self.assertEqual(uploads, (["llama.tar.gz"] if damaged else [])+["manifest.json"])
            digest.assert_not_called()
            if damaged:
                self.requests.get.assert_called_once()
                self.assertEqual(self.requests.get.call_args.args[0],"llama.tar.gz")
            else:
                self.requests.get.assert_not_called()

    def test_corrupt_manifest_rebuilt_without_redownloading_valid_files(self):
        for raw in (b"{broken",b"[]",b'{"schema":2}',json.dumps({**self.manifest,"files":[None,1,{}]}).encode()):
            with self.subTest(raw=raw):
                self.exercise_repair(corrupt_manifest=raw)

    def test_missing_cache_asset_is_recovered(self):
        self.exercise_repair(damaged="missing",download_bytes=b"abc")

    def test_same_size_corrupted_asset_is_recovered(self):
        self.exercise_repair(damaged="hash",download_bytes=b"abc")

    def test_truncated_asset_is_recovered(self):
        self.exercise_repair(damaged="size",download_bytes=b"abc")

    def test_corrupted_replacement_never_published(self):
        self.exercise_repair(damaged="hash",download_bytes=b"bad")

    def test_manifest_read_auth_error_is_not_treated_as_cache_corruption(self):
        with patch.object(self.populate,"listing",return_value={"manifest.json":{}}), \
             patch.object(self.populate,"rc",side_effect=[b"",RuntimeError("RCLONE_FAILED:401")]), \
             patch.object(self.populate,"metadata") as metadata:
            with self.assertRaisesRegex(RuntimeError,"RCLONE_FAILED:401"):
                self.populate.main()
            metadata.assert_not_called()
    def test_missing_manifest_recovers_verified_existing_files(self):
        published = {}
        def rc(*args, **kwargs):
            if args[0] == "mkdir":
                return b""
            if args[0] == "copyto" and args[2].endswith("/manifest.json"):
                published.update(json.loads(Path(args[1]).read_text()))
                return b""
            if args[0] == "cat" and args[1].endswith("/manifest.json"):
                return json.dumps(published).encode()
            self.fail("Unexpected remote operation: " + args[0])
        with patch.object(self.populate, "listing", return_value=self.files), \
             patch.object(self.populate, "metadata", return_value=("mock", [(dict(e), "mock") for e in self.entries])), \
             patch.object(self.populate, "rc", side_effect=rc), \
             patch.object(self.populate, "upload_verified") as upload, \
             patch.object(self.populate, "remote_digest") as digest:
            self.populate.main()
            self.assertEqual(published, self.manifest)
            upload.assert_not_called()
            digest.assert_not_called()
            self.requests.get.assert_not_called()

    def test_upload_auth_failure_is_not_retried(self):
        for code in ("invalid_grant", "invalid_scope", "401"):
            with self.subTest(code=code), \
                 patch.object(self.populate, "rc", side_effect=RuntimeError("RCLONE_FAILED:" + code)) as rc, \
                 patch.object(self.populate, "file_info") as info, \
                 patch.object(self.populate.time, "sleep") as sleep:
                with self.assertRaisesRegex(RuntimeError, "RCLONE_FAILED:" + code):
                    self.populate.upload_verified(self.tmp / self.model, self.entries[0])
                rc.assert_called_once()
                info.assert_not_called()
                sleep.assert_not_called()

    def test_local_model_copy_auth_failure_removes_partial_file_and_redacts(self):
        copy=self.runtime()["copy_verified_model"]
        dest=self.tmp/"local.gguf"
        entry={"size":3,"sha256":hashlib.sha256(b"abc").hexdigest()}
        for stderr,category in ((b"401 Unauthorized private-error","LOCAL_MODEL_COPY_AUTH_FAILED"),
                                (b"token expired; no refresh token private-error","LOCAL_MODEL_COPY_AUTH_FAILED"),
                                (b"invalid_grant private-error","LOCAL_MODEL_COPY_AUTH_FAILED"),
                                (b"403 permission denied private-error","LOCAL_MODEL_COPY_ACCESS_DENIED")):
            with self.subTest(stderr=stderr):
                def run(*args,**kwargs):
                    dest.write_bytes(b"partial")
                    return Mock(returncode=1,stderr=stderr)
                with patch("subprocess.run",side_effect=run) as call:
                    with self.assertRaisesRegex(RuntimeError,"^"+category+"$"):
                        copy("mock.conf",dest,entry)
                    call.assert_called_once()
                    self.assertIn("--low-level-retries",call.call_args.args[0])
                    self.assertFalse(dest.exists())
                    self.assertNotIn("private-error",self.log.getvalue())

    def test_local_model_copy_success_and_hash_failure(self):
        copy=self.runtime()["copy_verified_model"]
        dest=self.tmp/"local.gguf"
        entry={"size":3,"sha256":hashlib.sha256(b"abc").hexdigest()}
        for data in (b"abc",b"bad"):
            def run(*args,**kwargs):
                dest.write_bytes(data)
                return Mock(returncode=0,stderr=b"")
            with patch("subprocess.run",side_effect=run):
                if data==b"abc":
                    copy("mock.conf",dest,entry)
                    self.assertEqual(dest.read_bytes(),data)
                    dest.unlink()
                else:
                    with self.assertRaisesRegex(RuntimeError,"LOCAL_MODEL_HASH_MISMATCH"):
                        copy("mock.conf",dest,entry)
                    self.assertFalse(dest.exists())

    def test_local_model_copy_timeout_removes_partial_file(self):
        import subprocess
        copy=self.runtime()["copy_verified_model"]
        dest=self.tmp/"local.gguf"
        def run(*args,**kwargs):
            dest.write_bytes(b"partial")
            raise subprocess.TimeoutExpired("rclone",900)
        with patch("subprocess.run",side_effect=run):
            with self.assertRaisesRegex(RuntimeError,"LOCAL_MODEL_COPY_TIMEOUT"):
                copy("mock.conf",dest,{"size":3,"sha256":"a"*64})
            self.assertFalse(dest.exists())


class AuthTests(Offline):
    def setUp(self):
        super().setUp()
        cfg = configparser.ConfigParser(interpolation=None)
        cfg["rocache"] = {"type": "drive", "scope": "drive.file", "client_id": "mock-client",
                          "client_secret": "mock-secret", "token": json.dumps({
                              "access_token": "mock-expired", "refresh_token": "mock-refresh",
                              "token_type": "Bearer", "expiry": "2000-01-01T00:00:00Z"})}
        config = io.StringIO()
        cfg.write(config)
        self.enterContext(patch.dict(os.environ, {"RCLONE_CONFIG_SECRET": config.getvalue()}))
        self.auth = load("colab-drive-auth")
        self.token = {"access_token": "mock-new", "token_type": "Bearer", "expires_in": 3600}
        self.requests.post.side_effect = None
        self.requests.post.return_value = self.response(200, self.token)
        self.requests.get.side_effect = None
        self.requests.get.return_value = self.response(200, {"files": []})

    @staticmethod
    def response(status, body):
        return Mock(ok=200 <= status < 300, status_code=status, **{"json.return_value": body})

    def check_secret_free(self):
        for secret in ("mock-client", "mock-secret", "mock-refresh", "mock-new", "mock-expired", "private-error"):
            self.assertNotIn(secret, self.log.getvalue())

    def test_expired_access_token_refreshes(self):
        self.auth.main()
        self.assertEqual(self.requests.post.call_args.kwargs["data"]["grant_type"], "refresh_token")
        self.assertEqual(self.requests.get.call_args.kwargs["headers"]["Authorization"], "Bearer mock-new")
        cfg = configparser.ConfigParser(interpolation=None)
        cfg.read(self.tmp / "drive.conf")
        token = json.loads(cfg["rocache"]["token"])
        self.assertEqual(token["access_token"], "mock-new")
        self.assertEqual(token["refresh_token"], "mock-refresh")
        self.assertNotEqual(token["expiry"], "2000-01-01T00:00:00Z")
        self.check_secret_free()

    def test_revoked_refresh_token_stops_before_drive_access(self):
        self.requests.post.return_value = self.response(400, {"error": "invalid_grant", "error_description": "private-error"})
        with self.assertRaises(SystemExit) as e:
            self.auth.main()
        self.assertEqual(e.exception.code, 1)
        self.assertIn("phase=refresh http=400 reasons=invalid_grant", self.log.getvalue())
        self.requests.get.assert_not_called()
        self.assertFalse((self.tmp / "drive.conf").exists())
        self.check_secret_free()

    def test_drive_401_and_403_stop_without_writing_credentials(self):
        for status, reason in ((401, "UNAUTHENTICATED"), (403, "PERMISSION_DENIED")):
            with self.subTest(status=status):
                self.requests.get.return_value = self.response(status, {"error": {"status": reason, "message": "private-error"}})
                with self.assertRaises(SystemExit) as e:
                    self.auth.main()
                self.assertEqual(e.exception.code, 1)
                self.assertIn("phase=files_list http=" + str(status) + " reasons=" + reason.lower(), self.log.getvalue())
                self.assertFalse((self.tmp / "drive.conf").exists())
                self.check_secret_free()


if __name__ == "__main__":
    unittest.main(verbosity=2)
