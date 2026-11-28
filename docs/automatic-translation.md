# Automatic translation updates

Daily workflow and manual dispatch run on main only. The PR contract job
does not use Google credentials, download models or start Colab.

- Scan both game entry pages, current news and visible wiki. Verify matching
  builds and retain only missing/changed records in temporary files.
- Reuse unambiguous exact English source hashes and preserve existing records.
- Only unresolved rows use Index-Translate, Hy-MT3 and Qwen3. Copy all
  three models and the shared engine once into one T4 runtime; unload each
  model before the next. Existing Drive cache paths are unchanged.
- Reject malformed, structurally invalid or semantically rejected results.
  Model candidates are not human-approved merely because they pass.
- Create a candidate PR with validated translations; existing main CI
  publishes after merge. Never publish unreviewed model output directly.
- Delete extracted source and temporary candidates and close the allocated
  runtime. Do not terminate another person's existing Colab sessions.

Existing secrets: COLAB_ADC_JSON, RCLONE_CONFIG_V2.
The candidate PR uses GITHUB_TOKEN if repository Actions settings allow
creating pull requests. Optional TRANSLATION_UPDATE_TOKEN can be used for
a scoped token with contents and pull-request write access (and to trigger
normal PR CI). No secret is stored in source.

At most 200 unresolved rows per run; long/multiline and numeric shorthand
requiring review are deferred and reported by record ID. An existing open
candidate PR prevents duplicate model runs until reviewed. No deletion or
automatic publication of rejected rows is performed.
