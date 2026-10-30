# External RCA annotation candidate packet v1 — protocol

## Status and purpose
This is a **candidate pool**, not a completed independent benchmark. It contains 40 candidate public issue reports not present in the repository's earlier 15-case public-issue probe. The pool and short evidence summaries were assembled with assistant assistance after the RCA implementation already existed. Therefore, do not describe the candidate pool as independently sampled or report a score from the empty template.

The goal is to arrange a model-blind, independently labelled challenge set for the frozen `RuleBasedRCA` implementation. `RuleBasedRCA` receives a coarse `failure_type` as input, so the evaluator measures **root-cause subcode mapping conditional on a human-labelled family**. It does not evaluate end-to-end failure-family detection.

## Before annotation: source-pool review
1. A coordinator who did not implement or tune the rules should inspect the separate `rca_external_source_register_v1.csv` and review the linked issue reports.
2. The coordinator should use a predeclared inclusion rule (for example, a documented incident/error trace from an ML, data-processing, or orchestration project) to replace/add cases where the supplied evidence summary is ambiguous, too stale, not actually a pipeline incident, or duplicates a failure mechanism.
3. Freeze the revised packet and source register, calculate their SHA-256 hashes, and do not alter the packet after labels are collected. Keep the source register available to annotators so they can inspect primary issue context; do not give them rule source code, rule predictions, or prior evaluation outputs.
4. Because the candidate pool was assembled post hoc with assistant help, the final report must disclose that fact even if an external coordinator reviews and refines the selection. Only describe the evaluation as *independently annotated* if annotators and adjudicators did not implement/tune the rules; describe the sampling as independent only if case selection was also independently conducted under a predeclared protocol.

## Annotation procedure
1. Use two annotators who did not implement or tune `RuleBasedRCA`.
2. Each annotator independently copies the CSV and fills `failure_family`, `gold_root_cause_code`, `annotator_confidence_1_to_5`, `rationale`, and `annotator_id`. They should consult original issue pages where the evidence summary is insufficient. They must not view model predictions or rule implementation.
3. Compare the two label files only after both are frozen. Resolve disagreements without seeing predictions. In the final adjudicated CSV, set `adjudication_status` to `agreed` when both original labels matched or `adjudicated` when a resolution was made. Do not overwrite the two independent first-pass files.
4. Make a copy of the final adjudicated labels and record its SHA-256. The evaluator refuses incomplete labels and checks that the frozen RCA source hash matches the expected implementation.
5. Evaluate once the set and labels are frozen. If the RCA implementation changes, create a new versioned evaluation; do not replace the old record.

## Label vocabulary
`failure_family` must be one of:
- `schema_change`
- `data_quality`
- `configuration_error`
- `dependency_error`
- `unknown_runtime_failure`

`gold_root_cause_code` must follow this vocabulary:
- Schema: `schema_mismatch`, or `schema_rename:<unexpected>-><missing>` only when the source evidence supports both column names unambiguously.
- Data quality: `missing_feature_values`, `invalid_feature_values`, `invalid_feature_types`, or `unclassified_data_quality`.
- Configuration: `invalid_parameter:<parameter_name>` when the name is supported by evidence, otherwise `invalid_model_configuration`.
- Dependency: `missing_module:<module_name>` only if an explicit module is named; otherwise `missing_runtime_dependency`.
- Insufficient evidence, unsupported families, or a cause outside the available taxonomy: use family `unknown_runtime_failure` and code `unknown`.

Do not infer missing values from a generic shape error. Do not interpret every `ModuleNotFoundError` as a missing package: the issue may describe package shadowing, import-path/cache state, version conflicts, or process state. Explain uncertainty in `rationale` and assign confidence from 1 (low) to 5 (high).

## Required final metrics
Report exact-match subcode accuracy with a Wilson 95% interval, macro-F1, per-code precision/recall/F1/support, confusion matrix, results grouped by supplied failure family, number of `unknown` cases, and false-known diagnoses when gold is `unknown`. Report the two annotators' agreement before adjudication and the number of adjudicated cases. Since family is supplied to `RuleBasedRCA`, do not report these metrics as end-to-end RCA accuracy.

## Frozen baseline identifiers
- RCA implementation SHA-256: `00a0dc340102408c5a2dc0ff430c25691795f9b551197eefee49caf3131a6164`
- Candidate packet SHA-256: see `benchmarks/data/rca_external_annotation_manifest_v1.json`.
- Source register SHA-256: see the same manifest.

No model accuracy result has been generated from this empty packet. Do not update the paper's results until labels are completed, adjudicated, frozen, and evaluated.
