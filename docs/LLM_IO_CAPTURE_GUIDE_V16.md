# Opt-in LLM request/response capture for the V16 live rerun

This is for a **new** experiment only. The historical 2026-10-24 requests cannot be reconstructed.

The repeated-trial runner calls `LLMRepairGenerator`, which now supports opt-in capture through `SHMLP_LLM_IO_LOG_PATH`. When set, each completion request records the exact model/temperature/response format/messages, a SHA-256 of the request payload, the full SDK response object (including returned model/id/usage where supplied), attempt number, and timestamp. Failed requests record the request plus a credential-scrubbed exception message. The API-key value is not passed into the capture function or written into the JSONL.

**Privacy:** prompts and responses may include incident context. Enable this only for the repository's controlled synthetic fixture, use a private output path, inspect the result before sharing or committing it, and never include `.env` or credentials in a release. The JSONL is created with restrictive file permissions where supported. The old prompt spec hashes remain identifiers for the old V16 source and do not identify this patched capture build; generate a new manifest after applying this patch.

## Run

```bash
export SHMLP_LLM_IO_LOG_PATH="research_artifacts/2026-10-25/live_rerun/llm_io.jsonl"
python -m benchmarks.llm_run_manifest --output research_artifacts/2026-10-25/live_rerun/llm_run_manifest.json
python -m benchmarks.repeated_trials --repeats 1
```

The repeated-trial runner writes timestamped raw result JSONL and summary JSON under `benchmarks/results/`. Start with one repeat (32 fixed scenario templates and approximately one primary repair-generation call per template; validation retry may add extra requests). Review the summary and provider usage/cost before deciding whether to run `--repeats 5`. Copy the timestamped summary/raw file names into the run manifest/handoff notes. Do not overwrite the historical 2026-10-24 archive.
