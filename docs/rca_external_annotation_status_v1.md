# External RCA candidate packet — status report

Date prepared: 2026-10-24 UTC

## Prepared
- 40 unique public issue-source candidates across scikit-learn, pandas, MLflow, LightGBM, Apache Airflow, Keras/TensorFlow, PyTorch, and XGBoost.
- No URL overlaps the repository's previous 15-case `rca_public_issue_probe_v1.json` set.
- Blind annotation CSV omits source title, URL, and any model prediction. A separate source register preserves provenance.
- Annotation instructions define allowed labels, a two-annotator/adjudication workflow, freeze hashes, and limitations.
- Evaluation script scores conditional root-cause subcode mapping only after all 40 external labels are completed and frozen. It refuses to score incomplete annotations and checks the frozen RCA source hash.

## Frozen identifiers
- RCA source SHA-256: `00a0dc340102408c5a2dc0ff430c25691795f9b551197eefee49caf3131a6164`
- Blank annotation packet SHA-256: `c44f0b6cbdda9bffcab04be298d3d260b76a56c8cdd02c51ab46d70b1f17b5de`
- Source register SHA-256: `b39a3b512c9f7f846d70bd1d35e22db226013f4466a584485c048993e712095b`

## Critical caveat
This is **not yet an independent benchmark**: the candidate URLs and excerpts were assembled with assistant assistance after the implementation existed. For a claim of independent evaluation, an external reviewer must independently review the sampling criteria, ideally replace/add cases from a predeclared search protocol, label the cases without seeing code/predictions, and freeze/adjudicate the labels before scoring. No accuracy result was generated from the blank labels.

## Next human handoff
1. Give a reviewer the annotation CSV and instructions, not the model source or existing result files.
2. Obtain two independent label passes, then adjudicate disagreements.
3. Save the completed annotations as a new file (do not overwrite the blank packet), compute its SHA-256, and run the evaluator against this frozen repository snapshot.
4. Update the manuscript only after the resulting JSON has been reviewed.
