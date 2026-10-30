# Base-repository upgrade v17 — implementation and validation report

## Scope

This upgrade is based on the user-provided `self-healing-ml-pipeline.zip`, not on the separate V20-generated repository snapshot. It improves runtime observability and experimental accounting while preserving the active 32-case scenario fixture and the repository's policy-gated repair architecture. It does not change the four fault families or tune the rule-based repair behavior against the new verification outputs.

## Changes

- Added timestamped, flushed runtime stages to the three-path live benchmark so the terminal identifies fault injection, incident collection, RCA, candidate planning, LLM generation, each evaluation arm, and row persistence.
- Added bounded retry handling for temporary HTTP 429 responses, honor of provider retry/reset hints, and immediate stop on daily RPD/TPD exhaustion. The runner records explicit operational-failure statuses and saves partial run artifacts before exiting nonzero.
- Required a new, run-specific LLM request/response capture path for research runs. A non-empty capture is rejected to prevent silent mixing of attempts; preflight-only mode makes no API request. Capture files include prompts and responses and must be kept private.
- Expanded run manifests to hash the key files governing repair, policy, validation, scenarios, and benchmark behavior. The manifest names this a **critical source-set hash**, not a full repository hash; a Git commit is recorded only when actually available.
- Corrected summary accounting so the report exposes status counts, API/rate-limit operational failures, the recovery denominator, and sample sizes for each latency mean. A generation mean over failed and successful requests is no longer presented without its sample count. Each run summary also audits capture JSONL record/status counts, malformed lines, rate-limit failure interactions, and first/last timestamps without copying prompts or response bodies into the summary.
- Made the active seed-sensitivity script accurately identify its 24 eligible fixture templates (24 × 20 = 480 checks at the default) and emit a versioned timestamped output instead of overwriting a historical `v1` file. The alternate-signature stress harness also gets a timestamped output and refuses to overwrite an existing path.
- Lazily imports the optional OpenAI SDK within the live generator and avoids printing a raw malformed model response to the terminal.
- Added offline unit tests for quota classification, retry behavior, output preservation, summary denominators, manifest safety, expanded sensitivity naming, and capture-log integrity summaries.

## Validation performed on the upgraded source

Environment: Python 3.13.5.

| Check | Result | Interpretation |
|---|---|---|
| Full offline pytest suite | **129 passed** | Regression tests pass; no live API requests were made by pytest. |
| Python compile check | Passed | `benchmarks/*.py` and `healing/repair/*.py` compile. |
| Live runner CLI help | Passed | Can inspect the updated CLI without importing the optional OpenAI SDK at module import time. |
| Runner preflight fail-safe check | Passed | With a dummy placeholder credential and the optional SDK absent, preflight exited 2, recorded the missing SDK, and left the capture file at 0 bytes; no API request was sent and the placeholder value was not serialized. |
| Fresh deterministic gated baseline | **24/32 recovered (75%)** | 24/24 automatically eligible cases recovered; 8/8 dependency cases escalated; 0 blocked/failed. Single repeat on fixed project-authored templates. |
| Expanded seed sensitivity | **480/480 validator checks passed** | 24 active templates × 20 split seeds; repeated template checks are not independent operational incidents. |
| Alternate-signature detector stress challenge | **32/40 correct (80.0%, macro-F1 0.8167)** | Project-authored synthetic stress set; not independent external validation. Conditional RCA subcode mapping was 40/40 only when the expected family was supplied. |
| Targeted validator/safety regression | **205/205 expected statuses** | 50/50 valid accepted, 130/130 unsafe/mutated blocked, and 25/25 dependency proposals escalated; handcrafted controls, not a production attack-rate estimate. |
| Failure-family regression | **34/34 correct** | Developer-authored locked regression fixture, not blind/independent. |
| Locked RCA challenge | **33/36 correct (91.67%)** | Developer-authored challenge; not third-party blind or production performance. |
| Policy-gate decision ablation | **3 permitted, 5 human review, 28 rejected of 36** | No candidate actions executed; decision-only handcrafted proposals. |

Machine-readable offline results are in `research_artifacts/v17_upgrade_verification/`. These results validate script compatibility and current deterministic behavior; they do not establish production efficacy or replace the historical live-LLM comparison.

## Archive completeness audit

The supplied base ZIP contains historical `benchmarks/results/` files, but not the dated evidence directories referenced in several existing README/research notes, including `research_artifacts/2026-10-23/`, `2026-10-24/`, and `2026-10-25/`. The source ZIP contained a single `research_artifacts/live_llm_v20/repeat_02/source_fingerprint.json` metadata file but not its matching run log, raw JSONL, summary, or manifest set; that isolated V20 metadata was intentionally excluded from this base-source upgrade to avoid mixing it with the new runner. The missing dated artifacts are not fabricated or reconstructed here. The pre-existing `tools/release_preflight.py --skip-tests` was executed: it exited 1 solely because the October 24 bundle was missing its raw JSONL, summary JSON, and manifest. It reported zero cache/OS-metadata hygiene issues, no active `.env`, no unpinned requirement entries, and no missing core source paths. Restore those original files or deliberately revise the archive-audit specification before treating the historical release preflight as passing; this is a research-evidence completeness blocker, not a pytest failure.

## Not claimed / still required

- No live-LLM experiment was run inside this build environment: the optional OpenAI SDK and live credentials were not available. Consequently, this report makes no claim about current model recovery, API latency, or current LLM-vs-rule-based superiority.
- The uploaded source archive has no usable Git history for this source snapshot. The generated manifest will set `git_commit` to null unless run inside a valid Git checkout. Do not assign a commit from another repository whose source hashes differ.
- The 32-case suite is a fixed project-authored challenge. Five repeats over these templates are repeated observations, not 160 independent real-world incidents. External annotation and independent validation remain necessary for stronger publication claims.
- The current manuscript has not been revised based on this code-only upgrade. Run a clean, instrumented smoke test and the planned full experiment on this exact upgraded source first; only then update paper tables and claims.

## Live-run procedure

See [`EXPERIMENT_RUN_PROTOCOL_V17.md`](EXPERIMENT_RUN_PROTOCOL_V17.md). First install the pinned optional LLM dependencies, configure the provider locally, set a fresh `SHMLP_LLM_IO_LOG_PATH`, and run `python -u -m benchmarks.repeated_trials --output-dir <new-directory> --preflight-only`. Then run a four-family smoke test in that same directory/capture location. Only promote a run into paper evidence when its status is completed, the raw results have all planned method rows, there are no rate-limit operational failures, and capture timestamps are aligned with the run.

## Credential hygiene

The original uploaded archive contained a `.env` file. This upgraded release intentionally excludes `.env`, `.git` metadata, AppleDouble/macOS metadata, and cache files. The `.env` contents were not inspected or copied. If the uploaded `.env` contained a live key and was shared outside its authorized location, revoke that key and generate a replacement.
