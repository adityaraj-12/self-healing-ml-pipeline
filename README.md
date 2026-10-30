# Policy-Gated Self-Healing Machine Learning Pipeline

Repository: https://github.com/adityaraj-12/self-healing-ml-pipeline

This research prototype connects ML-pipeline failure detection, incident capture, rule-based root-cause analysis (RCA), structured repair-proposal generation, action restrictions, isolated validation, controlled recovery, and post-recovery artifact checks.

> **Research scope.** The benchmark uses synthetic, injected faults and a single scikit-learn classification pipeline. Results below support feasibility on the tested cases; they do not establish general safety, performance on production incidents, or accuracy on genuinely unseen fault distributions.

## Features

- Four injected fault classes: schema change, data quality, model configuration, and simulated dependency error.
- Incident context and rule-based RCA.
- Deterministic repair planning and optional LLM-generated repair candidates.
- Explicit action/failure compatibility policy and parameter checks.
- Sandbox validation for supported automatic repairs.
- Human-review routing for dependency changes rather than automatic package installation.
- Recovery, model reload, and prediction/metric consistency checks.
- Automated unit/integration tests and separate benchmark scripts.

## Architecture

```text
ML pipeline -> failure detection -> incident context -> rule-based RCA
     -> repair candidate (deterministic planner or LLM)
     -> action policy -> isolated validation -> controlled recovery
     -> saved-artifact reload and consistency checks

Dependency changes -> human approval; no automatic package installation
```

The LLM proposes a structured candidate; it does not independently authorize arbitrary code or shell execution. `llm_direct_isolated` bypasses the separate preflight validator but retains isolation and executor-side constraints. It is **not** a fully policy-free LLM executor.

## Environment and installation

The offline core checks were run with Python 3.13.5. Core and tested-environment dependencies are pinned in `requirements.txt`.

```bash
git clone https://github.com/adityaraj-12/self-healing-ml-pipeline.git
cd self-healing-ml-pipeline
python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pytest -q
```

LLM-backed modules additionally require `openai` and provider credentials. Install `requirements-llm.txt` and copy `.env.example` to `.env`, then set the exact provider-supported model identifier and credentials locally:

```bash
python -m pip install -r requirements-llm.txt
cp .env.example .env
# Edit .env locally; never commit it.
```

The `openai==3.20.0` extra is pinned, but a live API/provider integration could not be tested in the environment that generated the offline results in `research_artifacts/`. API-compatible endpoints may differ in their support for JSON response formats.

## Commands

### Automated tests

```bash
python -m pytest -q
```

`pytest.ini` confines automated test discovery to `tests/`. Files under `scripts/` named `test_*.py` are manual demos that may call external services and are not pytest test modules. The current offline test run for this upgraded base snapshot completed with **129 passed** in Python 3.13.5. The suite includes a contract check for the active 32-case/four-family fixture, the 34-case family-classification regression fixture, quota/retry/capture-accounting tests, checks against ground-truth leakage and ambiguous `KeyError` handling, and LLM-run manifest/endpoint-redaction tests. It does not exercise live LLM API calls.

### Re-run the deterministic gated baseline (no API call)

```bash
python -m benchmarks.rule_based_trials --repeats 5
```

### No-healing and retry-once controls (no API call)

```bash
python -m benchmarks.baseline_controls --repeats 5
```

This command reports persistent configured faults separately from a synthetic one-shot transient load timeout; do not combine those two fault regimes into one rate.

### Expanded targeted validator regression cases (no API call)

```bash
python -m benchmarks.safety_evaluation
```

The targeted suite runs 205 predeclared cases: 50 valid controls, 130 unsafe/mutated proposals, and 25 dependency-review controls. The v17 upgrade rerun met all expectations: 50/50 valid cases passed, 130/130 unsafe proposals were blocked, and 25/25 dependency proposals were escalated. Its output is `research_artifacts/v17_upgrade_verification/safety_evaluation_v17.json`. These selected regression fixtures do not estimate real-world attack rates.

### Hand-authored synthetic RCA challenge (no API call)

```bash
python -m benchmarks.diagnosis_holdout_challenge
```

The challenge is manually specified and was used while developing the classification rules. It is **not blinded** and should be treated as a regression challenge, not independent or production RCA accuracy.

### Failure-family detector regression set (no API call)

```bash
python -m benchmarks.failure_family_regression
```

This separately tests the top-level `FailureDetector` using 34 developer-authored exception-message cases across schema, data-quality, configuration, dependency, and unknown families. The v17 upgrade rerun matched 34/34 expected labels; its output is `research_artifacts/v17_upgrade_verification/failure_family_regression_v1.json`. The fixture is locked to the detector source hash and is used as a regression test only: the cases were authored with the implementation and **are not an independent, blind, or production evaluation**. The detector deliberately ignores injected ground-truth metadata and returns `unknown_runtime_failure` when the available text does not support a known family.

### Alternate-signature detector stress challenge (no API call)

```bash
python -m benchmarks.failure_stress_challenge
```

The 40-case project-authored stress fixture varied exception wording, ambiguous import-state messages and unknown-runtime cases. The frozen detector result was 32/40 family classifications correct (80.0%; descriptive Wilson 95% interval 65.2%-89.5%; macro-F1 0.8167). This is a synthetic diagnostic stress test, not an independently sampled or externally annotated benchmark. The script now writes a unique timestamped result by default and refuses to overwrite an existing result path. The conditional root-cause subcode mapper receives the expected failure family and must not be reported as end-to-end RCA accuracy.

### Split-seed sensitivity (no API call)

```bash
python -m benchmarks.seed_sensitivity --seeds 20
```

The current script evaluates the **24 active schema/data-quality/configuration templates** across 20 train/test split seeds, for 480 validation checks. It also varies the missingness injection seed for data-quality cases. The output is saved under a dated `research_artifacts/YYYY-MM-DD/` directory with a unique timestamp and explicitly names its expanded template set. Existing result files are never overwritten. This is a source-code-driven expanded run, not a reconstruction of the older nine-template/180-check sensitivity result described in prior research notes. It reuses templates and one data-generating setup, so repeated seed checks are not independent real-world failures; it does not compare the LLM arms or establish generalization to other datasets. Report the exact output file, template IDs, seed count, and pass denominator for each run.

### Locked synthetic RCA evaluation (no API call)

```bash
python -m benchmarks.diagnosis_locked_evaluation
```

The evaluator checks the SHA-256 hash of `healing/rca/rule_based_rca.py` against a locked 36-case JSON fixture before running. The frozen implementation matched 33/36 expected root-cause codes (91.7%; descriptive Wilson 95% interval 78.2%-97.1%). The three errors were (1) `Object dtype` wording, (2) a `warm_start` setting phrased without `parameter` or `argument`, and (3) an unquoted module name. The case set is developer-authored, not third-party blind, and is not a production accuracy estimate. Do not tune the rules against this set and continue to report it as the current locked result. If the RCA code is intentionally changed, preserve this result and create a new versioned evaluation set.

### Policy-gate decision-only ablation (no action executed)

```bash
python -m benchmarks.policy_gate_ablation
```

The harness applies the actual action/failure allowlist and approval policy to 36 hand-crafted proposal records, then compares those decisions with a counterfactual dispatcher that would send every structurally complete proposal to a simulator. The v17 rerun permitted three candidates to proceed to validation, escalated five proposals, and rejected 28 mismatched or unsupported proposals. The bypass simulation would dispatch all 36, including 33 proposals that the gate rejects or escalates. Its output is `research_artifacts/v17_upgrade_verification/policy_gate_ablation_v17.json`. **No candidate action is executed**; this is a decision-logic ablation, not evidence of end-to-end recovery improvement or general safety.

### Three-path LLM comparison (requires valid provider config and credentials)

The upgraded runner now requires a **fresh opt-in capture path** by default, prints timestamped stage-by-stage progress with flushing, stops on daily-quota exhaustion, and writes explicit run completeness and failure counts. Use a unique directory for every run:

```bash
RUN_DIR="research_artifacts/live_llm_v17/pilot_01"
mkdir -p "$RUN_DIR"
export SHMLP_LLM_IO_LOG_PATH="$PWD/$RUN_DIR/llm_io.jsonl"

# No API request; validate settings and capture setup first.
python -u -m benchmarks.repeated_trials --output-dir "$RUN_DIR" --preflight-only

# Smoke test: one scenario from each of the four fault families.
set -o pipefail
python -u -m benchmarks.repeated_trials \
  --case-ids schema_01 data_01 config_01 dependency_01 \
  --repeats 1 --output-dir "$RUN_DIR" \
  2>&1 | tee "$RUN_DIR/console.log"
```

After a clean smoke test, create a new output directory and capture file for the full 32-scenario run; omit `--case-ids`. Read [the v17 run protocol](docs/EXPERIMENT_RUN_PROTOCOL_V17.md) before running five repeats. Older notes describe a Groq-compatible model configuration, but its dated manifest/capture bundle is missing from the supplied base archive; see the archive-completeness warning below. The upgraded manifests hash the key behavior-defining source files and report Git metadata when available.

### CLI recovery example

```bash
python -m pipeline.runner --failure data_quality --auto-heal
```

Check module and flag behavior against the current branch before reusing these commands in other scripts.


### Runtime visibility and failure accounting (v17 base upgrade)

The live runner emits explicit progress for failure injection/incident creation, RCA, deterministic planning, LLM candidate generation, each repair arm, and result persistence. It writes partial summaries when provider quota is exhausted and distinguishes operational/generation failures from the denominator used for conditional automatic recovery. These controls do not themselves improve a repair method's accuracy; they improve observability and experimental validity. See [`docs/EXPERIMENT_RUN_PROTOCOL_V17.md`](docs/EXPERIMENT_RUN_PROTOCOL_V17.md).

A concise code-change and validation report is available in [`docs/BASE_REPOSITORY_UPGRADE_V17.md`](docs/BASE_REPOSITORY_UPGRADE_V17.md). This base-repository upgrade is a new implementation-validation checkpoint, not a new live-LLM result or a manuscript revision.

## Current experimental evidence

**Archive completeness warning:** the original README and research notes reference dated `research_artifacts/2026-10-23/`, `2026-10-24/`, and `2026-10-25/` outputs, but those dated directories were not present in the user-provided base ZIP. The archive contains older selected outputs under `benchmarks/results/`, but not every raw artifact cited in the historical notes. Restore the missing run folders from their original protected locations before claiming those specific historical records are included or independently reconcilable. The new `research_artifacts/v17_upgrade_verification/` files are fresh offline verification outputs from this upgrade and are clearly labelled separately.

### Historical deterministic gated pathway (12-template design)

The historical three-path comparison used twelve configured scenario variants repeated five times (60 trials per method). The deterministic gated arm recovered **45/60 (75%)** overall. All **45/45** automatically eligible cases recovered; the remaining **15/15** dependency cases were routed to human review. The Wilson 95% interval for 45/60 is 62.8%-84.2%; for 45/45 it is 92.1%-100%. These intervals are descriptive because trials reuse scenario templates and are not independent real-world failures. The active fixture now has 32 templates for the separate V16 extension below; it must not be confused with the historical run.

### Baseline controls

| Control experiment | Trials | Pipeline successes | Observed rate |
|---|---:|---:|---:|
| No healing, persistent injected faults | 60 | 0 | 0% |
| Retry once, same persistent injected faults | 60 | 0 | 0% |
| No healing, separate one-shot transient load timeout | 5 | 0 | 0% |
| Retry once, separate one-shot transient load timeout | 5 | 5 | 100% |

The persistent controls intentionally leave each deterministic fault active, so retrying unchanged input/configuration does not resolve it. The transient test is a separate small synthetic control showing the expected benefit of retry for a one-shot load exception. The two regimes must not be pooled.

### Validator regression suite

The expanded, programmatically generated suite covered 205 targeted cases:

- **50/50 valid controls passed**; observed valid false-rejection rate 0/50, Wilson 95% interval 0%-7.1%.
- **130/130 deliberately unsafe/mutated proposals were blocked**; observed block rate 100%, Wilson 95% interval 97.1%-100%.
- **25/25 dependency proposals were routed to human review.** An initial mutation run found three accepted proposals with extra fields (`fill_target`, `execute_code`, and `allow_train_test_leakage`). Unknown plan/parameter fields are now rejected and regression tests cover the defect. All 205 cases met their expected statuses after the fix.

These are targeted regression fixtures, not representative samples from an operational attack distribution. The rates do not establish general safety; the cases were deliberately constructed to target known guardrails and are not random samples of production proposals.

### Public-issue-source RCA probe (exploratory; no API call)

Run:

```bash
python -m benchmarks.external_issue_rca_probe
```

This probe evaluates 15 short error excerpts from public project issue reports and one official scikit-learn source file. On the frozen RCA implementation, the mapper returned the manually assigned expected subcode for **15/15** cases. The `failure_type` is supplied to the mapper, so this tests subcode mapping rather than end-to-end failure-family detection. Case-level source URLs and expected labels are stored in `benchmarks/data/rca_public_issue_probe_v1.json`. The prior raw predictions path (`research_artifacts/2026-10-23/rca_public_issue_probe_v1_result.json`) is not included in the uploaded base archive; rerun the evaluator to regenerate a current output before relying on this result as a bundled artifact.

**Interpretation limit:** the public-source probe was curated after the rule implementation existed and labels were manually assigned within this project. It is external-source-derived but not independently labelled or blind; the cases are selected, correlated, and not representative of production faults. Do not claim that 15/15 is production or generalization accuracy. Preserve this probe as an exploratory compatibility check; a genuinely independent evaluation still requires a third party to select and label cases while the frozen implementation and labels remain hidden from the developer.

### RCA challenge sets

The 15-case synthetic challenge was created and refined during development; it produced 15/15 expected codes after rule updates and is only regression coverage. A second, hash-locked 36-case synthetic set was frozen before evaluation against the recorded RCA implementation and scored 33/36 (91.7%; descriptive Wilson interval 78.2%-97.1%). It is separate from `trial_cases.yaml` and the earlier challenge, but it remains developer-authored rather than third-party blind. The three misses involved a data-type wording variant, a parameter-name wording variant, and an unquoted module name. The locked score must not be portrayed as production RCA accuracy.

### Earlier three-method comparison

The paper's previously recorded three-path comparison reports 45/60 recoveries (75%) for each of `rule_based_gated`, `llm_direct_isolated`, and `llm_validated`. The two LLM pathways shared a generated candidate within each trial. The equality of outcomes does not show that LLM repair improves recovery or that preflight validation is necessary. The historical LLM run is not fully independently reproducible: the near-time manifest records `openai/gpt-oss-20b`, the Groq-compatible endpoint, `openai==3.20.0`, temperature 0 and JSON-object output, but historical prompts/completions and a Git commit were not retained. See `docs/LLM_PROMPT_SPECIFICATION_V16.md` for the current prompt template and source hashes; they do not reconstruct the old per-trial requests.

### V16 expanded paired recovery and detector comparison (offline)

The active `benchmarks/scenarios/trial_cases.yaml` includes **32 fixed templates** (eight per fault family), comprising the historical 12 plus 20 variants of column names, missingness levels, invalid model-parameter values/types, and simulated dependency names. Five repeats produced 160 persistent-fault trials. The gated deterministic pathway recovered **120/160 (75.0%; descriptive Wilson 95% interval 67.8%-81.1%)**; all **120/120** automatic-repair-eligible trials recovered across 24 templates, and all **40/40** dependency trials were escalated. The no-healing and retry-once controls recovered **0/160** persistent faults each and **0/120** on the matched automatically eligible subset. At the template level, 24/24 eligible templates had five successful gated repairs, versus 0/24 successful templates for each persistent-fault control. Repeats reuse a fixed synthetic template, so trial-level intervals are descriptive and should not be read as 120 independent faults.

On the frozen 40-case alternate-signature detector fixture, the message-and-stage detector scored **32/40 (80.0%; Wilson 95% interval 65.2%-89.5%; macro-F1 0.8167)**, compared with **12/40 (30.0%; interval 18.1%-45.4%; macro-F1 0.2400)** for a minimal exception-class-only baseline. This is a same-fixture comparative result on project-authored cases, not independent external validation. The historical three-way repair comparison remains tied at 45/60 for each method; a live LLM run on the 32-template extension was not performed because no provider credentials were configured. The historical analysis note is [`docs/COMPARATIVE_EVIDENCE_V2.md`](docs/COMPARATIVE_EVIDENCE_V2.md), but its cited `research_artifacts/2026-10-25/` raw-result folder is absent from the uploaded base archive. Treat those values as historical notes until the original raw artifacts are restored or the experiments are rerun.

## Optional dependency for live LLM experiments

The offline deterministic tests do not require API credentials. To run the LLM-backed comparison, install the separately pinned SDK dependency set:

```bash
python -m pip install -r requirements-llm.txt
cp .env.example .env
# Edit .env locally: set OPENAI_MODEL and OPENAI_API_KEY; set OPENAI_BASE_URL only if needed.

# Preflight and smoke test; run from repository root.
RUN_DIR="research_artifacts/live_llm_v17/pilot_01"
mkdir -p "$RUN_DIR"
export SHMLP_LLM_IO_LOG_PATH="$PWD/$RUN_DIR/llm_io.jsonl"
python -u -m benchmarks.repeated_trials --output-dir "$RUN_DIR" --preflight-only
set -o pipefail
python -u -m benchmarks.repeated_trials \
  --case-ids schema_01 data_01 config_01 dependency_01 \
  --repeats 1 --output-dir "$RUN_DIR" 2>&1 | tee "$RUN_DIR/console.log"

# After the smoke succeeds, use a DIFFERENT new directory and capture file for
# the full study. Check provider quota before choosing repeats=5.
```

The `--preflight-only` command does not make an API request. It returns an incomplete-configuration status if the model, key, installed SDK, pinned SDK version, or required fresh capture setup is unavailable. A nonzero exit code signals incomplete configuration. Never commit `.env` or print the API-key value in logs.

## Model and prompt configuration

The LLM integrations read `OPENAI_MODEL`, `OPENAI_API_KEY`, and optional `OPENAI_BASE_URL` from environment variables. The checked-in source uses temperature 0 and requests JSON-object responses for the repair-generation and LLM-RCA calls. The repeated-trials runner writes a sanitized manifest for each new run; it never records the API-key value. Prompt construction is defined in `healing/repair/llm_repair_generator.py` and `healing/rca/llm_rca.py`. A verbatim prompt/configuration supplement and SHA-256 values for the current source are in `docs/LLM_PROMPT_SPECIFICATION_V16.md`; these current source hashes do not establish the exact code used in the historical run.

Prior research notes describe a run using `openai/gpt-oss-20b` through `https://api.groq.com/openai/v1`, with `openai==3.20.0`, Python 3.13.15, temperature 0, and JSON-object output. However, the referenced `research_artifacts/2026-10-24/llm_run_20261024_171821/` directory and its manifest/capture bundle were not present in the uploaded base ZIP. Those settings and results are historical notes, not provenance independently verified by this package. Restore the actual run artifacts before relying on them for paper tables.

## Repository layout

```text
pipeline/                 Main ML pipeline and runner
failures/                 Fault injection and fault classes
healing/                  RCA, candidate generation, policy, validation, recovery
benchmarks/               Repeated trials, controls, safety, and RCA challenge
benchmarks/scenarios/     Configured injected scenario set
configs/                  Pipeline and repair configuration
tests/                    Unit, integration, and end-to-end tests
research_artifacts/       Versioned v17 offline verification outputs; historical dated bundles may be absent
```

## Reproducibility and limitations

- One dataset and one model family were used in the benchmark.
- The four configured fault classes are controlled injections rather than production traces.
- The 60-trial RCA labels are coupled to the scenarios used to design the rules.
- The 15-case RCA challenge is a development set. The 36-case source-hash-locked set is separate from it, but remains developer-authored and is not a third-party blind test.
- The 36-case policy-gate ablation is decision-only: it confirms allowlist/approval outcomes on hand-crafted proposals but never executes actions. A fully policy-free LLM executor was not evaluated; unsafe actions must only be explored in a disposable simulation with no host access, secrets, network side effects, or package installation.
- Prior notes describe a 2026-10-24 three-method comparison, but its dated 180-row raw JSONL/summary/manifest bundle is not included in the supplied base ZIP. Do not claim that the source archive independently reconciles this run until those original artifacts are restored. Git commit metadata was not recorded for that historical run, and its manifest did not reconstruct per-trial prompts/completions.
- The current v17 expanded sensitivity run covers 24 project-authored eligible templates across 20 split seeds (480 repeated checks); it is not the older nine-template/180-check result and does not replace multi-dataset replication or external fault sampling. The v17 offline environment had no SDK/credentials, so no new live LLM comparison was run.
- Do not commit `.env`, API keys, credentials, private data, or other secrets.

## Safety

Candidate generation is not authorization. Keep validation and recovery experiments isolated. Do not enable automatic package installation for dependency faults. Review proposed changes before applying this prototype to real workloads, and treat the validator as a layer of defense rather than a complete safety guarantee.

## Citation

When citing this work, use the final author list, title, venue, year, and persistent URL after the paper has been accepted or published. The current manuscript is an implementation study with controlled, preliminary evaluations; it should not be described as a validated production-grade self-healing system.
## External RCA annotation candidate packet (not yet evaluated)

The repository includes a 40-case candidate packet built from previously unused public issue reports: `benchmarks/data/rca_external_annotation_packet_v1.csv`. Source URLs are kept separately in `benchmarks/data/rca_external_source_register_v1.csv`. Have a coordinator review the source register and freeze a packet using a predeclared selection rule. Then have two reviewers who did not implement or tune the RCA rules label it independently and adjudicate disagreements. Run `python -m benchmarks.evaluate_external_rca_annotations --packet PATH_TO_FROZEN_PACKET --annotations PATH_TO_ADJUDICATED_LABELS`. The scorer refuses incomplete or unadjudicated labels and checks the frozen RCA SHA-256.

**Do not cite this packet as an independent benchmark until external labels have been adjudicated and the final source selection has been independently reviewed.** The current `RuleBasedRCA` receives `failure_type` as input, so the scorer measures conditional subcode mapping, not end-to-end failure-family detection. See `docs/rca_external_annotation_instructions_v1.md`.


## Audited repeated-trial run (2026-10-24)

Historical note (artifact bundle missing from the uploaded base ZIP): prior documentation reports 180 raw records (60 per method), 45/60 recoveries per method, and 15 dependency cases routed to review. The cited `research_artifacts/2026-10-24/llm_run_20261024_171821/`, `AUDIT_REPORT.md`, and `AUDIT_RESULT.json` were not present in the supplied archive, so this base upgrade has not independently reverified those claims. Do not treat them as audit-ready evidence until the source run artifacts are restored. The new v17 offline verification outputs do not replace that missing live-LLM evidence.

## Public release preparation (V16 candidate)

The archive includes `tools/release_preflight.py` to check core repository files, pinned dependency syntax, cache/OS-metadata hygiene, and consistency of the archived 2026-10-24 repeated-trial JSONL against its summary. Run it from the repository root:

```bash
python tools/release_preflight.py --output research_artifacts/release_preflight_current.json
```

The command also runs the test suite unless `--skip-tests` is specified. Read the emitted JSON and address any nonzero result before tagging. A ZIP archive does not include Git history; follow [`RELEASE_TO_GITHUB_V16.md`](RELEASE_TO_GITHUB_V16.md) from an existing clone to create an actual commit and tag. The original October 24 LLM run has no recorded Git commit SHA, so a newly created release tag does not retroactively prove which commit ran that experiment.
