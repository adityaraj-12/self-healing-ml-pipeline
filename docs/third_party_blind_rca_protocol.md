# Protocol for a genuinely independent RCA evaluation

## Why this protocol is separate

The included `rca_public_issue_probe_v1.json` uses externally authored public issue reports, but case selection and labels were curated after the RCA rules already existed. It is an exploratory source-compatibility probe, not an independent or blind evaluation. The 36-case `rca_locked_v1.json` remains developer-authored as well. Do not rename either set “third-party blind.”

## Roles

- **Evaluator:** a person who did not implement or tune `RuleBasedRCA` and is not shown its source or existing expected labels before the case set is sealed.
- **Developer/operator:** freezes the code revision and runs the evaluator only after the external labels are sealed.

## Case-set requirements

1. Freeze the exact RCA source commit and SHA-256 before the evaluator selects cases. Record the commit and hash in the report.
2. Select at least 40 case records from previously unused public issue reports, documented pipeline failures, or anonymized operational incidents. Avoid reusing the issue IDs in `rca_public_issue_probe_v1.json`, `rca_locked_v1.json`, or the development challenge.
3. Include realistic messages from at least five source projects and several different error families. Do not create cases by merely paraphrasing strings from the current rule patterns.
4. Have two evaluators independently label the failure family and root-cause subcode from the incident evidence without viewing the current RCA code or its predictions. Resolve disagreements before unsealing predictions and report raw agreement; if appropriate, report Cohen's kappa.
5. Store raw, minimally redacted evidence, source URL or provenance, label rationale, reviewer IDs/roles, and an explicit unknown/abstain label for insufficient evidence. Remove personal data and secrets.
6. Save the final case file and compute its SHA-256 before running the RCA implementation. Keep the expected labels inaccessible to the developer/operator until the evaluator says the set is frozen.
7. Run both levels separately: (a) family-level classification with no `failure_type` supplied; and (b) subcode mapping conditional on the externally labelled coarse `failure_type`. The current `RuleBasedRCA` accepts a coarse type as input, so the existing evaluation scripts assess only the second level.
8. Report confusion matrices, per-class precision/recall/F1, macro-F1, coverage/abstention rate, and errors with short explanations. Do not report only aggregate accuracy. Compare to simple keyword and majority-class baselines.
9. Never tune on the sealed cases. If rules change after evaluation, preserve the first result and use a new, separately versioned challenge for subsequent evaluation.

## Suggested report fields

- source commit and source SHA-256
- case-set ID, file SHA-256, freeze timestamp
- selection window and inclusion/exclusion criteria
- number of cases by source project and failure family
- labelling guide and adjudication procedure
- inter-rater agreement before adjudication
- per-class and aggregate metrics, confusion matrix, abstention rate
- false-known diagnosis count (unknown cases forced into known categories)
- misclassified examples and safety implication
- limitations on source selection and external validity

## Minimum honest claim

A third-party-labelled public-incident set can provide stronger evidence than developer-authored synthetic cases, but it is not automatically representative of production incidents. Report exactly how the set was collected, labelled, and frozen.
