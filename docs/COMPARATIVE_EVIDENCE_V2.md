> **Archive note (base upgrade v17):** The dated `research_artifacts/2026-10-25/` raw-result files referenced in this note were not present in the supplied base ZIP. Treat the narrative/figures below as historical documentation, not as freshly audit-verified evidence in this package. Restore the original output bundle before using these specific numbers in a submission. The v17 offline verification files are separate and do not retroactively validate this older comparison.

# Comparative evidence update — V16 (2026-10-25)

## 1. Expanded paired recovery challenge

**Design.** The active scenario fixture now contains 32 fixed synthetic variants: eight each for schema change, data quality, configuration errors, and dependency errors. The original 12 are retained; 20 additions vary column identities, missingness fractions (0.03–0.40), invalid `C`/`max_iter` values and types, and simulated dependency names. Five repeats per template yield 160 persistent-fault trials. This is an extension of the controlled parameter/column challenge, not 20 new real-world fault families.

| Method | Persistent trials succeeded | Auto-repair-eligible subset | Dependency subset | Interpretation |
|---|---:|---:|---:|---|
| Deterministic policy-gated recovery | 120/160 (75.0%; Wilson 95% CI 67.8–81.1%) | 120/120 (100%; trial-level descriptive CI 96.9–100%) | 40/40 routed to human review | 24 automatic-repair templates each succeeded in all five repeats. |
| No healing | 0/160 (0%; CI 0–2.34%) | 0/120 (0%; CI 0–3.10%) | No repair attempted | Same persistent fault remains active. |
| Retry once | 0/160 (0%; CI 0–2.34%) | 0/120 (0%; CI 0–3.10%) | No repair attempted | Same deterministic fault remains active after retry. |

At the template level, all 24 automatically eligible templates succeeded in every gated repeat (24/24; Wilson interval 86.2–100%), compared with 0/24 successful templates for no healing and 0/24 for retry-once (each 0–13.8%). Trial-level intervals are descriptive and optimistic if interpreted as independent draws because five trials reuse each template. The matched automatic subset is 120 gated successes versus 0 baseline successes, an observed paired difference of 100 percentage points on this fixed challenge.

A separate transient timeout control remains 0/5 for no healing and 5/5 for retry-once. This transient regime is not combined with persistent faults.

## 2. Detector comparison on frozen alternate-signature fixture

The 40-case fixture was scored with the existing detector and a simple exception-class-only baseline implemented in the comparative-analysis script. The baseline mapping was specified as part of this analysis; it was not externally preregistered or independently validated. It makes no use of message text or runtime stage: `ModuleNotFoundError`/`ImportError` -> dependency, `KeyError` -> schema, `InvalidParameterError` -> configuration, and all other exception classes -> unknown.

| Method | Correct | Accuracy (Wilson 95% CI) | Macro-F1 |
|---|---:|---:|---:|
| Message-and-stage `FailureDetector` | 32/40 | 80.0% (65.2–89.5%) | 0.8167 |
| Exception-class-only baseline | 12/40 | 30.0% (18.1–45.4%) | 0.2400 |

There were 20 cases on which the rule detector alone was correct and zero on which only the type baseline was correct. An exact paired sign/McNemar-style calculation on discordant cases is 1.91e-6, but the fixture was project-authored, labels were not independent, and the fixed challenge is not a probability sample. The p-value is not interpreted as population-level evidence. The result is a useful same-fixture diagnostic comparison, not an external test of generalization; because the baseline was defined in the current analysis and the fixture is project-authored, the comparison should be treated as exploratory rather than a confirmatory preregistered test.

## 3. Historical three-method comparison: no observed recovery separation

The archived 180-row raw JSONL still represents 60 trial keys from the **historical 12-template design**. Each of the three methods recovered 45/60 (75%; Wilson 95% interval 62.8–84.2%) and routed the same 15/60 dependency trials to human review. For every pair of methods, 45 cases were recovered by both, 15 by neither, and there were zero discordant outcomes; the observed paired recovery difference was 0.0 percentage points. This does not prove equivalence, but it does mean the original benchmark cannot support a claim that LLM generation or the extra validator improved recovery.

Cluster-bootstrap timing intervals over the 12 original scenario templates (20,000 bootstrap resamples, seed 20261025) were:

| Historical method | Mean combined seconds | Cluster-bootstrap descriptive 95% interval |
|---|---:|---:|
| Rule-based gated | 0.164174 | 0.110138–0.216449 |
| Direct isolated LLM | 12.624264 | 11.133325–14.292181 |
| LLM plus validation | 12.695230 | 11.214279–14.332847 |

The resampling unit is the scenario template, not each repeat. Latency remains dependent on provider/model and the original run's historical provenance gaps.

## 4. Validator and policy-decision comparisons

The fresh 205-case validator regression run met all expected statuses: 50/50 valid controls passed (0/50 false rejections; Wilson upper bound 7.13%), 130/130 unsafe/mutated proposals were blocked (block-rate interval 97.13–100%), and 25/25 dependency proposals were routed to human review. These are purposely constructed cases, not a representative attack population.

The separate 36-proposal policy-gate test permitted 3 proposals to proceed to validation, escalated 5, and rejected 28. A minimal bypass dispatcher would have forwarded all 36, including the 33 rejected/escalated candidates. No actions executed. This is a decision-only ablation; it does not show that removing the gate changes end-to-end recovery.

## 5. What this does and does not resolve

This extension strengthens evidence relative to no-healing and retry-once for the deterministic repair method on a broader set of parameter/column variants, and it compares the message detector with a simple exception-class baseline on one fixed diagnostic challenge. It does **not** provide a new three-way repair-method comparison: no live LLM requests were made because no provider credentials were configured. The original three-way recovery tie remains unresolved on additional faults. External independent RCA annotation, full historical request logs, clean network-enabled installation, and a tagged public source release remain pending.

## Reproduction and artifacts

- `benchmarks/scenarios/trial_cases.yaml` — 32 scenario templates.
- `benchmarks/results/rule_based_trials_20261025_165736.json` — expanded gated trial results.
- `benchmarks/results/baseline_controls_20261025_165235.json` — paired persistent controls and transient control.
- `research_artifacts/2026-10-25/comparative_evidence_v2_result.json` — paired and baseline analyses, metrics and source hashes.
- `research_artifacts/2026-10-25/safety_evaluation_expanded_v2_result.json` — fresh 205-case validator result.
- `research_artifacts/2026-10-25/policy_gate_ablation_v2_result.json` — fresh decision-only policy-gate result.

All rates and intervals should be cited with the fixture design and limitations above.
