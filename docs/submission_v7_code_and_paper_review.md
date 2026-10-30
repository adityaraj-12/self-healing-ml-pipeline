> **Archive note (base upgrade v17):** The supplied ZIP does not include all dated research artifact directories described in this older review. Treat them as prior notes until the specific raw outputs are restored. The current base-upgrade verification report identifies the missing-artifact limitation.

# Code and Paper Submission Review — V7

**Project:** `https://github.com/adityaraj-12/self-healing-ml-pipeline`  
**Verification date:** 23 October 2026  
**Paper:** *A Policy-Gated Framework for Self-Healing Machine Learning Pipelines: Implementation and Controlled Evaluation*

## Summary

This revision advances the paper from development-only RCA examples to a separately frozen, implementation-hash-checked synthetic evaluation, and adds a decision-only policy-gate simulation. It also improves fresh-checkout packaging and removes unused zero-byte placeholders from the release snapshot. The release is a stronger and more reproducible research candidate, not a claim that all evaluation gaps have been closed.

## Verified code changes

- Improved rule-based RCA handling for alternate parameter, missing-value, and data-type wordings before freezing the new RCA evaluation fixture.
- Added `benchmarks/data/rca_locked_v1.json` and `benchmarks/diagnosis_locked_evaluation.py`. The evaluator verifies the SHA-256 of `healing/rca/rule_based_rca.py` and refuses to run if the implementation changes. The locked result must be preserved; code changes should be assessed with a new fixture or an independent external set.
- Added `benchmarks/policy_gate_ablation.py`, a decision-only simulation against the actual `enforce_repair_policy` function. The bypass is a simulated dispatcher only; no actions or candidate code execute.
- Added regression tests to keep the RCA hash lock/score and policy-decision counts reproducible.
- Fixed incident construction for non-injected runtime exceptions when `failure_ground_truth` is absent, ensured model output directories exist before saving, and checked the full imputation-policy contract at the validator boundary.
- Added explicit detection of training feature columns with no observed values before imputation can proceed.
- Added architecture, methodology, experiment, failure-taxonomy, research-notes, and locked-fixture documentation.
- Removed unused zero-byte placeholder scripts/configuration files and empty notebook files from the prepared repository snapshot. Valid empty `__init__.py` package markers were retained.
- Preserved the existing source lock result by not modifying `healing/rca/rule_based_rca.py` after the 36-case set was frozen and evaluated.

## Tests and experiments actually run

Command: `python -m pytest -q`  
Environment: Python 3.13.5  
Result: **67 passed** (about 1 second). No live LLM calls were made by this run.

### Deterministic gated path

- 12 configured variants × 5 repeats = 60 trials.
- 45/60 recovered (75%; descriptive Wilson 95% interval 62.8%–84.2%).
- 45/45 automatically eligible trials recovered (descriptive Wilson 95% interval 92.1%–100%).
- 15/15 dependency cases routed to human review.
- Latest runner-level timing: mean 0.0622 s, median 0.0673 s. This timing boundary differs from the historical plan/generation-plus-execution timing in the paper and must not be compared directly.

### No-healing and retry-once controls

- Persistent configured faults: no-healing 0/60 and retry-once 0/60. The same injected fault remains active; retry does not alter the input or configuration.
- Separate one-shot transient load-timeout check: no-healing 0/5 and retry-once 5/5. These are different fault regimes and must not be pooled.

### Locked synthetic RCA challenge

- 36 cases, source implementation hash matched.
- 33/36 expected root-cause codes matched (91.7%; descriptive Wilson 95% interval 78.2%–97.1%).
- Three errors: `Object dtype` did not map to the expected type-mismatch subcode; `warm_start` wording without “parameter” or “argument” was reduced to generic configuration; and an unquoted `No module named acme.runtime` message was reduced to generic runtime dependency.
- The fixture was separated from the configured trial set and earlier challenges and frozen before evaluation. It is developer-authored, not third-party blind; it is not a production accuracy estimate. The code was not tuned after observing this score.

### Decision-only policy-gate ablation

- 36 structured proposals were tested with the actual action/failure allowlist and approval assignment function.
- Gate-on outcomes: 3 permitted to proceed to the validator, 5 routed to human review, and 28 rejected.
- Four dependency proposals supplied `requires_human_approval=False`; policy overwrote the supplied field and sent them to review.
- A counterfactual dispatcher would have forwarded all 36 structurally complete proposals; 33 that the gate rejects/escalates would therefore have reached the simulator.
- **No action was executed.** This tests allowlist/approval decisions on handcrafted proposal records; it does not demonstrate causal improvement in end-to-end recovery, and it is not a live ungated LLM executor.

### Expanded validator regression suite

- 30/30 valid controls passed.
- 50/50 deliberately unsafe proposals were blocked.
- 5/5 dependency proposals were escalated.
- 85/85 expected outcomes matched. These are purpose-built regression fixtures, not a representative production security sample.

## Remaining gaps before submission

1. Obtain an independently authored or third-party blind RCA test set. Do not tune the RCA rules on `rca_locked_v1.json` and continue to call the same cases held out.
2. Run the LLM arms again with the exact provider/model/version, SDK, endpoint, generation options, prompt revision/hash, raw candidates, and per-trial outputs preserved. The historical LLM numbers remain previously recorded and were not reproduced in this offline run.
3. A policy-gate decision simulation is not an end-to-end ablation. If adding a proposal-generation comparison, keep dangerous actions in a disposable simulated executor with no host access, network side effects, secrets, or package installation.
4. Vary data-split and fault-generation seeds and use paired, scenario-aware analysis. Repeated instances of the same template are not independent real-world failure types.
5. Add additional datasets, models, fault types, and realistic or mixed faults.
6. Push this package to GitHub, record the commit hash, and tag the source revision that matches the paper and archived experiment JSON.
7. Verify the target venue's exact template, page limit, double-anonymous policy, artifact rules, and AI-use disclosure rules.
8. Run the institution-approved plagiarism/similarity checker and review matches and references. No Turnitin/iThenticate report was run here.

## Integrity statement

The manuscript is implementation-specific and explicitly attributes related work. This review does not certify zero plagiarism or guarantee any AI-detector result. Similarity analysis is a separate final check. The defensible contribution is bounded engineering implementation plus transparent controlled evaluation, not production-grade autonomy or general safety.

## Final release-snapshot verification

The prepared ZIP was extracted into a new directory separate from the working tree. From that clean extraction:

- `python -m pytest -q`: **67 passed (about one second in this environment)**.
- `python -m benchmarks.diagnosis_locked_evaluation`: implementation hash matched the fixture; **33/36** predictions matched, with the same three errors and descriptive Wilson interval.
- `python -m benchmarks.policy_gate_ablation`: **36 cases**; 3 permitted to validator, 5 escalated, 28 rejected; **zero actions executed**.
- The release ZIP excludes `.env`, virtual environments, Python caches, and runtime-generated benchmark result directories. Stable evidence outputs are preserved under `research_artifacts/2026-10-23/`.

This verifies the released offline core against the current test environment. It does not verify live LLM provider connectivity, cross-platform installation, or the target venue's formatting and review policy. The ZIP was prepared locally and was not pushed to GitHub.
