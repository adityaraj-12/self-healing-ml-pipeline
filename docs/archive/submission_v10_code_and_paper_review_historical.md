# Code and manuscript review — Version 10 repository / Version 9 paper

## Release snapshot verified

The repository archive was extracted to a clean directory and the following commands were run successfully:

```bash
python -m pytest -q
python -m benchmarks.failure_family_regression
python -m benchmarks.diagnosis_locked_evaluation
```

- Automated suite: **104 passed** on Python 3.13.5.
- Family detector regression v1: **34/34 expected family labels** (accuracy 1.0, macro-F1 1.0), and the detector implementation hash matched the fixture lock.
- Locked root-cause subcode evaluation: **33/36** (91.67%; descriptive Wilson interval in the emitted report), with source hash matched to lock.

## What changed

- `FailureDetector` now uses explicit patterns for schema, data-quality, configuration, and dependency errors, with an unknown-runtime fallback.
- Generic `KeyError` does not automatically imply schema failure; feature/schema text or a relevant stage is required.
- The detector ignores injection ground truth. A unit test supplies a conflicting `failure_injection.ground_truth` value and verifies that classification follows the exception evidence instead.
- Added a versioned 34-case developer-authored regression fixture and evaluator with JSON output, per-class precision/recall/F1, and SHA-256 source locking.
- README, experiment notes, and the manuscript test paragraph were synchronized.

## Interpretation boundary

The 34-case detector fixture was authored within the project with the current taxonomy and classifier. It is a regression suite only, not an independent/blind accuracy estimate or a production result. The locked 36-case RCA challenge is also developer-authored and tests downstream root-cause subcodes, not end-to-end diagnosis. The separate 40-case external issue packet still requires coordinator review and independent annotations from two people who did not build or tune the rules.

## Still outstanding before a strong submission

1. Obtain independent annotations; do not use assistant- or implementer-assigned labels as a substitute.
2. Re-run the historical LLM methods after recovering and recording the exact provider/model ID, SDK/API version, prompt revision, endpoint, generation settings, and raw outputs.
3. Add variation across data split and fault-generation seeds and report uncertainty at the scenario level.
4. Push and tag one code revision that matches the manuscript and archived experiment outputs.
5. Run the venue's submission checker, confirm page/format/anonymity rules, and use an approved plagiarism/similarity tool. No Turnitin/iThenticate report was run, and no AI detector outcome can be guaranteed.

## Suggested Git operations

After reviewing the archive and merging its contents locally:

```bash
git status --short
git diff --check
git add README.md requirements.txt healing/detector/failure_detector.py benchmarks tests docs research_artifacts
git commit -m "Add family detector regression evaluation"
git tag research-v10
git push origin main --tags
```

Review the diff and ensure no credentials or `.env` files are staged before pushing.
