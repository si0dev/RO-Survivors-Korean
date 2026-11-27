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

    def test_existing_bad_cache_stops_without_download_or_upload(self):
        files = dict(self.files)
        del files[self.model]
        files["manifest.json"] = {}
        with patch.object(self.populate, "listing", return_value=files), \
             patch.object(self.populate, "rc", side_effect=[b"", json.dumps(self.manifest).encode()]) as rc, \
             patch.object(self.populate, "metadata") as metadata, \
             patch.object(self.populate, "upload_verified") as upload:
            with self.assertRaisesRegex(RuntimeError, "CACHE_MANIFEST_MISMATCH"):
                self.populate.main()
            metadata.assert_not_called()
            upload.assert_not_called()
            self.assertEqual([c.args[0] for c in rc.call_args_list], ["mkdir", "cat"])
            self.requests.get.assert_not_called()

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
