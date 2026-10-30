> **Archive note (base upgrade v17):** The historical result path referenced in this note is not present in the supplied ZIP. Re-run `python -m benchmarks.failure_family_regression` to create current output before claiming the raw result is bundled.

# Failure-family detector regression v1

## Purpose

This fixture checks the top-level `healing.detector.failure_detector.FailureDetector` separately from the downstream root-cause subcode mapper in `healing.rca.rule_based_rca.RuleBasedRCA`.

It has 34 developer-authored exception-message cases: 6 schema, 8 data-quality, 6 configuration, 6 dependency, and 8 unknown-runtime cases. Inputs include exception class, message, and a limited runtime stage. The detector is not allowed to read injected-fault metadata or ground-truth labels.

## Reproduction

From the repository root:

```bash
python -m benchmarks.failure_family_regression
python -m pytest -q
```

## Recorded result

- Cases: 34
- Expected family labels matched: 34
- Accuracy: 1.0000
- Macro-F1: 1.0000
- Expected and actual detector SHA-256 match the versioned fixture.
- Raw row-level output: `research_artifacts/2026-10-24/failure_family_regression_v1_result.json`

## Interpretation limit

This fixture was authored within the same project as the detector and is intentionally designed around the implementation's family taxonomy. It is a regression suite, **not an independent, blind, or production evaluation**. Its perfect score must not be used as evidence that the detector generalizes to unseen incidents. The separate RCA-subcode evaluations answer a different question and have their own limitations.

The detector uses exception type, message patterns, and limited runtime stage context. It intentionally does not consult `context.failure_injection.requested_type` or `context.failure_injection.ground_truth`; one regression test explicitly checks this anti-leakage property. Generic `KeyError` exceptions are treated as unknown unless feature/schema evidence is present.

## Versioning

The fixture records the SHA-256 digest of `healing/detector/failure_detector.py`. If that implementation changes intentionally, do not present a subsequent run as the same locked version. Add a new fixture version or use `--allow-source-mismatch` for exploration and clearly identify the modified implementation.
