# Live-LLM experiment protocol (base-repository upgrade v17)

This protocol applies to **new** live runs started from this repository revision. It does not alter or relabel historical run artifacts.

## What a run does

For each selected scenario and repeat, `benchmarks.repeated_trials` prints timestamped, flushed progress markers for these stages:

1. Inject the configured fault and collect the generated incident.
2. Run root-cause analysis and report the predicted root-cause code.
3. Build the deterministic rule-based candidate.
4. Request and structurally validate one LLM candidate, shared by the two LLM comparison arms.
5. Evaluate `rule_based_gated`, `llm_direct_isolated`, and `llm_validated`; dependency changes remain human-review-only.
6. Persist one row per method and print the case duration.

The run header displays the model identifier, capture path, raw results path, summary path, planned number of scenarios/repeats, and expected number of method rows. The end of the run reports each method's recovery, eligibility, review, rate-limit, and operational-failure counts.

## Preflight a fresh capture location

Run commands from the project root. Use a **new directory and new capture file per run**. A non-empty capture file is rejected to prevent evidence from separate runs being mixed.

```bash
RUN_DIR="research_artifacts/live_llm_v17/pilot_01"
mkdir -p "$RUN_DIR"
export SHMLP_LLM_IO_LOG_PATH="$PWD/$RUN_DIR/llm_io.jsonl"

python -u -m benchmarks.repeated_trials \
  --output-dir "$RUN_DIR" \
  --preflight-only
```

Preflight writes a timestamped manifest and checks that the configured model, API-key presence, pinned SDK, source hashes, and a fresh capture file are available. **Preflight does not send an API request.** It exits nonzero when configuration is incomplete.

## Run a small four-family smoke test

The smoke test uses one scenario from each fault family. It verifies plumbing and is not part of the final benchmark denominator.

```bash
set -o pipefail
python -u -m benchmarks.repeated_trials \
  --case-ids schema_01 data_01 config_01 dependency_01 \
  --repeats 1 \
  --output-dir "$RUN_DIR" \
  2>&1 | tee "$RUN_DIR/console.log"
```

Check the summary, `llm_io.jsonl`, and the manifest. Do not count a smoke test as a full 32-scenario repeat. For the full experiment, create a new directory, set `SHMLP_LLM_IO_LOG_PATH` to that directory's own `llm_io.jsonl`, and omit `--case-ids`. Example for a five-repeat run (after quota review):

```bash
RUN_DIR="research_artifacts/live_llm_v17/full_01"
mkdir -p "$RUN_DIR"
export SHMLP_LLM_IO_LOG_PATH="$PWD/$RUN_DIR/llm_io.jsonl"
python -u -m benchmarks.repeated_trials --output-dir "$RUN_DIR" --preflight-only
set -o pipefail
python -u -m benchmarks.repeated_trials --repeats 5 --output-dir "$RUN_DIR" \
  2>&1 | tee "$RUN_DIR/console.log"
```

Do not reuse the smoke-test capture path; each distinct run needs its own directory and capture file.

## Rate limits and partial runs

- The runner retries only temporary HTTP 429 errors a bounded number of times.
- If the provider error indicates daily quota exhaustion (for example TPD/RPD), the runner does not retry immediately. It records the affected LLM method outcomes and completes the current case's deterministic baseline, then stops issuing further LLM requests.
- If a provider asks for a wait longer than `--max-rate-limit-wait-seconds` (default 30 seconds), the runner saves a partial result instead of sleeping for a long time.
- A partial/quota-stopped run writes raw rows, a summary with `run_status` and `stop_reason`, and its manifest, then exits nonzero. Treat it as operationally incomplete, not as a clean model-performance repeat.
- Overall recovery rate uses all recorded method rows. Conditional automatic recovery excludes human-review cases and recorded generation/operational failures; both counts and denominators are included in the summary.

Defaults can be overridden for controlled experiments:

```bash
python -m benchmarks.repeated_trials --help
```

The output settings, selected scenario IDs, retry policy, file names, Git provenance where available, and hashes for key behavior-defining source files are recorded in each manifest. If Git metadata is unavailable, the manifest leaves the commit null and records source hashes; do not fabricate a commit ID.

## Reproducibility and security

- Preserve raw JSONL, summary JSON, manifest JSON, console log, and capture log together.
- Never reuse a non-empty capture file for another run. Do not overwrite historical raw results.
- Capture contains prompts and provider responses. Keep it private and inspect it before sharing.
- Never package `.env` or provider credentials. `.env.example` contains names/placeholders only. If a real key was included in an archive shared outside its authorized environment, revoke it and create a replacement.
- Report repeated fixed templates as repeated observations of project-authored scenarios—not independent real-world incidents.
- Only finalize a paper table after the run reports `run_status: completed`, has no provider rate-limit failures, has the expected method row count, and the capture timestamps/statuses align with the run's time window.

## Offline result files

`benchmarks.seed_sensitivity` now writes an expanded, version-labelled result for the 24 active eligible templates across the requested number of seeds (480 checks at the default 20 seeds). Do not mix this with older nine-template/180-check reports; report each exact output file separately. `benchmarks.failure_stress_challenge` and `benchmarks.seed_sensitivity` use timestamped output names and refuse to overwrite an existing explicit path.
