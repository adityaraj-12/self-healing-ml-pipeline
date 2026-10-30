> **Archive note (base upgrade v17):** Some dated result paths cited below are not included in the supplied base ZIP. This file preserves prior methodological notes, but the associated raw outputs should be restored and audited before the stated values are used as submission evidence. See `docs/BASE_REPOSITORY_UPGRADE_V17.md` for the archive-completeness audit.

# Experimental methodology

## Main controlled benchmark

The benchmark uses scikit-learn's Breast Cancer Wisconsin diagnostic dataset (569 observations, 30 numeric features, binary target) with `StandardScaler` and `LogisticRegression`. Four injected fault classes are represented by three configured variants each: schema rename, missing feature values, invalid regularization `C`, and simulated missing-module errors. Each of the 12 variants is repeated five times, for 60 trials per method.

## Methods and controls

- `rule_based_gated`: deterministic proposal planning, policy enforcement, sandbox validation, and controlled recovery.
- `llm_direct_isolated` (historical run): LLM proposal with isolation and executor-side restrictions, but without the separate preflight validator.
- `llm_validated` (historical run): the same generated proposal routed through sandbox validation before recovery.
- `no_healing`: one attempt without repairing the persistent injected fault.
- `retry_once`: repeat the stage once without changing its input or configuration.
- **Transient retry control:** a distinct one-shot load timeout that disappears after its first occurrence; this is not pooled with persistent-fault results.

The historical LLM rows are retained as prior recorded results, not presented as a fresh rerun. Their exact model identifier and SDK request record were not found in the uploaded source archive.

## RCA evaluation sets

The configured 60-trial labels are assigned by scenario configuration and share the taxonomy used to create the rules. The earlier 15-case challenge was used while developing the rules and is only regression coverage.

`benchmarks/data/rca_locked_v1.json` contains 36 separately authored synthetic message cases. The fixture records the SHA-256 hash of `healing/rca/rule_based_rca.py`; the runner refuses to evaluate if that hash changes. The frozen implementation matched 33/36 expected root-cause codes. This set was created within the project, is not third-party blind, and is not a production accuracy estimate. Preserve this result rather than tuning on the same locked set; use a new versioned or independently authored set for future code changes.

## Validator safety regression suite

The current suite has 85 targeted cases: 30 valid controls, 50 deliberately unsafe proposals, and 5 dependency proposals that should be escalated. It checks selected known contracts, including action/fault compatibility, schema preservation, imputation parameters, configuration values, and approval routing. It is not a random or representative sample of real attacks.

## Policy-gate decision simulation

`benchmarks/policy_gate_ablation.py` sends 36 fixed proposal records to the actual action/failure allowlist and approval function. Its bypass comparison only records whether a minimal dispatcher would hand a structurally complete proposal to a simulator. The gate permits three candidates to continue to validation, escalates five dependency candidates, and rejects 28 unsupported or mismatched proposals. The bypass would dispatch all 36; 33 are rejected or escalated by the gate. No actions execute in either arm. This tests policy-decision behavior, not end-to-end recovery causality.

## Metrics and uncertainty

Recovery is reported overall and for cases eligible for automatic action. Wilson intervals are descriptive summaries. Repeated trials reuse scenario templates, so their intervals do not account for scenario dependence or variation across new fault families. Future evaluation should vary dataset splits and fault-generation seeds and use paired, scenario-aware analysis.


## Public-issue-source probe (post-hoc)

A 15-case supplementary probe was curated from public issue reports and an official scikit-learn validation source. It covers schema-name mismatch, missing/non-finite values, string-to-float conversion, an invalid estimator parameter, missing import modules, and two unknown runtime categories. The benchmark passes an externally assigned coarse `failure_type` to `RuleBasedRCA` and compares the returned subcode with a manually assigned label. This is therefore conditional subcode mapping, not an evaluation of the detector's coarse-category selection. The frozen implementation matched 15/15 expected codes.

The case selection and labels were produced within the project after the RCA implementation existed. The sources are external, but the test is neither blind nor independently labelled. Several cases share repositories and error families. It should be reported only as an exploratory software-compatibility check; it cannot establish production or generalization accuracy. The case-level source URLs and expected labels are included in `benchmarks/data/rca_public_issue_probe_v1.json`, with the prediction output in `research_artifacts/2026-10-23/rca_public_issue_probe_v1_result.json`.

## V16 expanded paired stress comparison (2026-10-25)

The historical three-path run remains the original 12-template, 60-trial comparison. For a separate offline stress extension, the scenario fixture was expanded to 32 fixed templates (eight per family): the original 12 plus 20 additional variants covering alternate schema columns, missingness fractions from 0.03 to 0.40, additional invalid `C` and `max_iter` values/types, and different simulated missing module names. Each template was repeated five times, giving 160 persistent-fault trials. This remains a project-authored parameter/column variation over the same four injected families, not a sample of new real-world fault mechanisms.

On this extension, deterministic `rule_based_gated` recovery succeeded in 120/160 trials (75.0%; descriptive Wilson 95% interval 67.8%-81.1%). All 120 trials eligible for automatic repair recovered (120/120; trial-level descriptive interval 96.9%-100%); those trials correspond to 24 templates, each succeeding in all five repetitions (template-level descriptive interval 86.2%-100%). The 40 dependency trials (eight templates x five repeats) were escalated to human review. On the same scenario IDs/repeat indices, no-healing and retry-once each succeeded in 0/160 persistent-fault trials and 0/120 trials within the automatic-repair-eligible subset. All 24 eligible templates had 5/5 successful gated repairs and 0/5 success under each persistent-fault control. The repeated trials are nested within purposively authored templates, so the intervals are descriptive, and no claim is made that 120 repetitions represent 120 independent faults.

The frozen 40-case alternate-signature detector fixture was also scored against an a-priori, exception-class-only baseline that maps `ModuleNotFoundError`/`ImportError` to dependency, `KeyError` to schema, `InvalidParameterError` to configuration, and other types to unknown. The current message-and-stage detector scored 32/40 (80.0%; Wilson 95% interval 65.2%-89.5%; macro-F1 0.8167), versus 12/40 (30.0%; interval 18.1%-45.4%; macro-F1 0.2400) for the minimal baseline. Twenty cases were correct only under the current detector, and zero were correct only under the baseline. Because the fixture is synthetic, project-authored, and not independently labelled, this is a fixed-challenge comparison rather than a population-level significance claim.

The 2026-10-24 three-method raw trial set was analyzed as paired case/repeat outcomes. All three methods recovered the same 45/60 cases and shared the same 15/60 human-review outcomes; each pair had zero discordant recovery outcomes and a 0.0 percentage-point observed paired difference. This is evidence that the original experiment cannot distinguish the pathways, not evidence of equivalence. A new live-LLM run on the 32-template fixture was not possible in the current environment because no provider credentials were configured; no new LLM results are claimed.

The supplementary analyzer is `benchmarks/comparative_evidence_v2.py`; its full output is `research_artifacts/2026-10-25/comparative_evidence_v2_result.json`. Raw extended trial and control records are preserved in the neighboring `rule_based_trials_expanded_v2_result.json` and `baseline_controls_expanded_v2_result.json` files. A preliminary `max_iter=0` variant did not raise under the installed environment and was replaced with the invalid non-integer string `not_an_integer` before the final 160-trial run; only the corrected final run is used in the results above.
