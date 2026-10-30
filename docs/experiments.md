> **Archive note (base upgrade v17):** The original ZIP does not contain all dated `research_artifacts/2026-10-23/`, `2026-10-24/`, or `2026-10-25/` files referenced by this historical notes document. These paths must be restored from the original run archive or the relevant experiment rerun before those outputs can be treated as bundled/reproducible evidence.

# Experiment commands and current results

Run commands from the repository root in the pinned Python environment. The offline runs below do not call the LLM API.

## Commands

```bash
python -m pytest -q
python -m benchmarks.rule_based_trials --repeats 5
python -m benchmarks.baseline_controls --repeats 5
python -m benchmarks.safety_evaluation
python -m benchmarks.diagnosis_locked_evaluation
python -m benchmarks.policy_gate_ablation
```

A live three-path LLM comparison uses `python -m benchmarks.repeated_trials --repeats 5` and requires valid provider settings and credentials. Before a live request, the runner writes a timestamped sanitized manifest next to the trial output. To inspect the current configuration without making a request, run `python -m benchmarks.llm_run_manifest --output research_artifacts/llm_run_manifest_current.json`. Record the model/version, SDK/API version, endpoint, prompt revision/hash, generation options, raw candidates, and trial-level outputs. The older LLM comparison is not fully reproducible from the supplied archive.

## Verified offline results for this release candidate

- **Earlier V15 tests:** 109 passed using Python 3.13.5; this was superseded by the V16 offline verification: 115 passed. Live LLM calls were not exercised.
- **Deterministic gated baseline:** 45/60 persistent-fault trials recovered (75%); 45/45 automatically eligible trials recovered; 15/15 dependency cases were routed to human review.
- **No healing / retry once:** each recovered 0/60 when the same persistent fault remained active.
- **Transient retry control:** in a separate one-shot transient load-timeout simulation, no healing recovered 0/5 and retry-once 5/5. Do not combine these five-trial results with the persistent-fault experiment.
- **Validator suite:** 30/30 valid controls passed, 50/50 deliberately unsafe proposals were blocked, and 5/5 dependency candidates were escalated (85/85 expected statuses).
- **Locked RCA synthetic set:** 33/36 expected codes matched (91.7%; descriptive Wilson interval 78.2%-97.1%). Three errors relate to `Object dtype` wording, `warm_start` phrasing, and an unquoted module name. This is developer-authored, not third-party blind.
- **Policy-gate decision simulation:** 3 proposals were permitted to proceed to validation, 5 were routed for human review, and 28 were rejected. The bypass arm would dispatch all 36 to a simulator, but no actions were executed.

Raw case/trial outputs, including the public-source RCA probe case file and result, are stored under `research_artifacts/2026-10-23/`. Read `research_artifacts/README.md` before interpreting the numbers.


## Public-issue-source RCA probe

A supplementary 15-case probe uses short error excerpts from public PyCaret, napari-feature-classifier, LightGBM, scikit-learn, PyBroker, and MLflow issue reports, plus one official scikit-learn validation source excerpt. With the coarse `failure_type` provided, the frozen mapper matched 15/15 expected subcodes. The fixture and raw output are `benchmarks/data/rca_public_issue_probe_v1.json` and `research_artifacts/2026-10-23/rca_public_issue_probe_v1_result.json`.

This is an exploratory post-hoc check. The cases were selected and labelled after the rule implementation existed, are not independent/blind, and are not a representative sample. It measures conditional subcode mapping, not end-to-end detector accuracy. The score must not be treated as evidence of production accuracy or generalization.


## Failure-family detector regression (2026-10-24)

The top-level `FailureDetector` is separately exercised by `benchmarks/failure_family_regression.py` using 34 developer-authored cases. The recorded result is 34/34 matches (accuracy 1.0; macro-F1 1.0), with the implementation source hash checked against the versioned fixture. The cases were written within the same project and are a regression fixture, not independent, blinded, or production evidence. This is a separate task from the downstream root-cause subcode mapping in `RuleBasedRCA`.

## LLM configuration capture

Before any live LLM benchmark, the repeated-trials runner writes a sanitized `llm_run_manifest_<timestamp>.json` next to the raw trial output. The manifest records the configured `OPENAI_MODEL`, whether a key is present (never the key value), a sanitized optional endpoint, the installed and declared OpenAI SDK version, Python/platform, source SHA-256 hashes, and request options observable in the source. Credential-like endpoint path segments are redacted as well as user-info/query/fragment values. The current code sets `temperature=0` and `response_format={"type":"json_object"}` for both repair generation and LLM-RCA calls. Repair generation can make up to two candidate attempts when structural validation fails; LLM RCA makes one request per analysis. `top_p` and token limits are not explicitly set, so provider defaults apply.

The manifest captures the environment at the time it is generated; it does not retroactively recover the model ID or settings used by historical runs. If the model configuration is incomplete, the manifest records the missing fields. Do not commit the local `.env` file.

## V16 expanded paired stress comparison (offline; no LLM API calls)

The current `benchmarks/scenarios/trial_cases.yaml` now contains 32 fixed templates (eight per fault family), including 20 additions to the historical twelve-template design. Run:

```bash
python -m benchmarks.rule_based_trials --repeats 5
python -m benchmarks.baseline_controls --repeats 5
python -m benchmarks.safety_evaluation
python -m benchmarks.policy_gate_ablation --output research_artifacts/2026-10-25/policy_gate_ablation_v2_result.json
python -m benchmarks.comparative_evidence_v2
```

The most recent offline comparison produced 120/160 gated recoveries overall, comprising 120/120 successful automatically eligible trials across 24 templates and 40/40 dependency cases routed to human review. No-healing and retry-once each produced 0/160 successes on persistent injected faults (and 0/120 on the automatic-repair-eligible subset). The separate one-shot transient control remains no-healing 0/5 versus retry-once 5/5. All intervals remain descriptive because the benchmark repeats a fixed, project-authored set of templates.

On the frozen 40-case alternate-signature fixture, the full message-and-stage failure detector scored 32/40 (80%, macro-F1 0.8167), compared with 12/40 (30%, macro-F1 0.2400) for a deliberately minimal exception-class-only baseline. This comparison is a diagnostic stress result, not external or production validation. The archived 2026-10-24 repair-path comparison remains tied: 45/60 for each of the three methods, with zero paired outcome discordance.

The final comparison JSON and raw inputs are stored under `research_artifacts/2026-10-25/`. For exact per-run details, hashes, confidence intervals, and limitations, see `docs/COMPARATIVE_EVIDENCE_V2.md`. A live LLM comparison on the expanded fixture has not been run; do not infer LLM performance from the deterministic pathway's result.
