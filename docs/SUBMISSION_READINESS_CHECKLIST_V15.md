# Submission-readiness checklist — V15 research candidate

## Document checks completed

- Manuscript updated with the 40-case alternate-signature family-detection stress result, 20-seed sensitivity run, 205-case validator safety run, and updated discussion/limitations.
- Scenario-coupled 60/60 RCA agreement is explicitly described as injected-label agreement, not held-out accuracy.
- The 36-case conditional RCA challenge is reported as 33/36; the 15/15 public-issue probe is described as conditional and exploratory.
- The historical three-method tie (45/60 each) is retained without claiming superiority.
- No-healing and retry-once persistent controls and the separate transient timeout control are reported separately.
- LLM model/provider, SDK, temperature, response format, current prompt templates, failure-specific action rules and current source hashes are in the manuscript/supplement.
- New data and methods limitations are stated; external RCA annotation has not been counted as a result.
- DOCX rendered and all eight pages visually inspected; PDF rendered separately and inspected; A4 page size; no visible table or figure clipping identified.
- Accessibility audit: zero high/medium/low findings.

## Offline code and safety checks

- `python -m pytest -q`: **115 passed** on Python 3.13.5.
- Release preflight: **0** cache/OS metadata files; no active `.env`; all required paths present; core and LLM requirement pins detected; archived historical 180-row run reconciles; tests return 0.
- Expanded safety suite: 205/205 expected outcomes; 50/50 valid controls accepted; 130/130 deliberately unsafe/mutated proposals blocked; 25/25 dependency proposals routed to human review.
- Strict-field validation now rejects extra fields such as `fill_target`, `execute_code`, and `allow_train_test_leakage`; unit regressions were added.
- Code snapshot contains pinned `requirements.txt` and `requirements-llm.txt` and excludes active `.env` and cache metadata.

## Required before actual external submission or public release

1. Choose a target venue and apply its exact template, page limit, citation/reference rules, anonymity policy, and declaration requirements.
2. Obtain author approval and verify author names, affiliations, emails, and order.
3. Run a live LLM reproduction with credentials in a clean network-enabled environment. Record the actual source commit, immutable model/provider revision where available, SDK, complete sanitized prompts/requests/candidates, endpoint, generation options, timestamps, seeds and raw trial outputs. Do not claim this has been done in V15.
4. Re-run all three repair pathways on a predeclared harder-fault challenge so the recovery-method comparison—not only family detection—is evaluated on the same faults. The current three historical arms remain tied at 45/60.
5. Complete independent source selection, two independent RCA annotators and adjudication for the external candidate pool. No external RCA accuracy score is available yet.
6. If testing policy-gate causality, use a disposable isolated simulator. The current bypass experiment is a decision-only simulation; no fully policy-free LLM repair arm was run.
7. Generate and verify a clean lockfile/install from a network-enabled environment, inspect public artifacts for sensitive data, then use an existing Git clone to commit/tag/push the exact source. The current ZIP has no Git history and is not a tagged release.

## Status

**V15 is a stronger, auditable, venue-neutral submission candidate, but it is not ready to claim that all reviewer requests are fully resolved.** Specifically, the harder-fault recovery comparison, fully policy-free LLM baseline, independent RCA annotation, exact historical prompt/output provenance, and clean install/public Git tag remain outstanding.
