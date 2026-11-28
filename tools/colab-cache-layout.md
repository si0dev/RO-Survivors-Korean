# Colab model cache layout

The existing Index-Translate model and manifest remain under `RO-Survivors-Korean-cache-v2/index-translate-9b-q6k-b12343-v1`; checkpoints retain their existing paths. Engine archives are shared by compatible models under `llama.cpp/<release>/ubuntu-cuda-12-x64` and the pinned rclone bootstrap under `bootstrap`.

New cache profiles use `models/<slug>/<quant>` under the same Drive root. The cache preparation script accepts an explicit JSON profile in `RO_CACHE_PROFILE_JSON` (slug, quant, Hugging Face repo, GGUF filename, compatible llama.cpp release tag, minimum model bytes). Existing CI uses the original default. Additional models are not enabled or downloaded by this change; their exact GGUF metadata, engine compatibility, inference settings and GPU capacity must be verified separately.

A valid legacy manifest permits a server-side copy of missing verified engine archives. Original files are retained; the large model is never copied for this migration. Invalid or missing files continue through the existing upstream digest and recovery flow. Local copies still undergo SHA-256 verification. No changes to OAuth scopes, secrets, or the translation pipeline.
