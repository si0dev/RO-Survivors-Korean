"""Drive cache locations; preserve the current model directory and share engines."""
import json
import os
import re

ROOT = "rocache:RO-Survivors-Korean-cache-v2"
DEFAULT = {
    "slug": "index-translate-9b",
    "quant": "q6_k",
    "repo": "IndexTeam/Index-Translate-9B-GGUF",
    "filename": "Index-Translate-9B.Q6_K.gguf",
    "engine": "b12343",
    "min_bytes": 7_000_000_000,
}

def profile(data=None):
    data = dict(DEFAULT if data is None else data)
    if set(data) != set(DEFAULT):
        raise ValueError("CACHE_PROFILE_FIELDS")
    for key in ("slug", "quant"):
        if not isinstance(data[key], str) or not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,79}", data[key]):
            raise ValueError("CACHE_PROFILE_PATH")
    if not isinstance(data["repo"], str) or not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", data["repo"]):
        raise ValueError("CACHE_PROFILE_REPO")
    if any(part in (".", "..") for part in data["repo"].split("/")):
        raise ValueError("CACHE_PROFILE_REPO")
    if not isinstance(data["filename"], str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]+\.gguf", data["filename"]):
        raise ValueError("CACHE_PROFILE_FILENAME")
    if not isinstance(data["engine"], str) or not re.fullmatch(r"b[0-9]+", data["engine"]):
        raise ValueError("CACHE_PROFILE_ENGINE")
    if type(data["min_bytes"]) is not int or data["min_bytes"] <= 0:
        raise ValueError("CACHE_PROFILE_SIZE")
    # Existing model/checkpoint paths must not be changed or duplicated.
    legacy = data == DEFAULT
    if not legacy and (data["slug"], data["quant"]) == (DEFAULT["slug"], DEFAULT["quant"]):
        raise ValueError("CACHE_PROFILE_RESERVED")
    data["model_remote"] = ROOT + ("/index-translate-9b-q6k-b12343-v1" if legacy else "/models/" + data["slug"] + "/" + data["quant"])
    data["engine_remote"] = ROOT + "/llama.cpp/" + data["engine"] + "/ubuntu-cuda-12-x64"
    data["bootstrap_remote"] = ROOT + "/bootstrap"
    data["legacy"] = legacy
    return data

def selected():
    raw = os.environ.get("RO_CACHE_PROFILE_JSON")
    return profile(json.loads(raw) if raw else None)

if __name__ == "__main__":
    print(selected()["model_remote"])
