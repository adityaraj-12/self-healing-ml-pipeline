# RCA evaluation data

`rca_locked_v1.json` contains the locked 36-case synthetic RCA challenge. The file records the SHA-256 hash of the tested `healing/rca/rule_based_rca.py` implementation. Run it with:

```bash
python -m benchmarks.diagnosis_locked_evaluation
```

The runner fails closed if the implementation hash differs, unless an explicit exploratory override is passed. Do not use the override to report a score for the wrong implementation. The challenge is developer-authored, not third-party blind, and not a production accuracy estimate. Keep its current 33/36 result; if code is changed, create a new versioned challenge for subsequent evaluation.

`rca_external_annotation_packet_v1.csv` is a blank 40-case candidate pool based on public issue reports. It is not an evaluated independent benchmark. The separate `rca_external_source_register_v1.csv` records provenance. Review the case pool under a predeclared protocol, have two people who did not write or tune RCA rules annotate independently, and adjudicate labels before scoring. Instructions: `docs/rca_external_annotation_instructions_v1.md`.

After producing a frozen, fully adjudicated label CSV, run `python -m benchmarks.evaluate_external_rca_annotations --packet PATH_TO_FROZEN_PACKET --annotations PATH_TO_ADJUDICATED_LABELS`. The evaluator checks the rule implementation hash and rejects missing labels or cases without an `agreed` / `adjudicated` status. It measures subcode mapping conditional on the provided family; it does not test end-to-end family detection.
