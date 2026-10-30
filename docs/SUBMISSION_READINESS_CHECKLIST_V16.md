# Submission-readiness checklist — V16 comparative evidence candidate

## New evidence recorded

- Active `benchmarks/scenarios/trial_cases.yaml` now contains 32 fixed templates: original 12 plus 20 additional column/parameter/missingness/dependency-name variants (eight per family).
- Expanded gated recovery: 120/160 overall (75.0%; descriptive Wilson 95% CI 67.8%-81.1%); 120/120 automatically eligible trials recovered; 40/40 dependency trials escalated to human review.
- Matched persistent controls: no-healing 0/160 and retry-once 0/160. On the same 120 automatic-repair-eligible trials, each control recovered 0/120; template-level view is 24/24 auto-eligible templates with 5/5 gated successes and 0/5 successes under each persistent control.
- Same 40-case detector fixture: message-and-stage detector 32/40 (80%, Wilson 95% interval 65.2%-89.5%, macro-F1 0.8167); exception-class-only baseline 12/40 (30%, interval 18.1%-45.4%, macro-F1 0.2400). Challenge is project-authored, not independent.
- Historical three-path repair comparison analyzed as paired data: 45/60 recoveries per method, identical recovered sets, zero discordant outcomes for every pair. This does not establish equivalence.
- Timing cluster-bootstrap analysis over 12 original scenario templates (20,000 resamples, seed 20261025) added to `comparative_evidence_v2_result.json`.
- Fresh 205-case validator evaluation: 50/50 valid accepted, 130/130 unsafe/mutated blocked, 25/25 dependency review routed.
- Fresh 36-proposal policy-gate decision simulation: 3 permitted to validator, 5 human review, 28 rejected; 0 actions executed.
- Offline test suite: **115 passed** on Python 3.13.5.

## Critical interpretation boundaries

- The expanded recovery result compares deterministic gated repair to no-healing/retry only. No live LLM requests were made on the 32-template challenge because provider credentials were not configured. The historical three-way tie remains unresolved for additional faults.
- New variants remain within four injected families, one dataset, and one model family. They do not substitute for real/independently selected faults.
- The exception-class baseline is deliberately simple and was specified within the current analysis rather than externally preregistered; detector comparison is on a single fixed project-authored challenge, and no p-value is treated as population-level inference.
- The policy-gate bypass test is a non-executing decision simulation, not a causal end-to-end recovery ablation.
- External RCA source selection and independent annotation/adjudication remain pending.

## Required before venue submission or public release

1. Choose a journal or conference and apply its exact template, page limits, anonymous-review rules, reference format, and declaration requirements.
2. Obtain author approval and verify all author names, affiliations, email addresses, ordering, and contribution statements.
3. Conduct a new paired live-LLM comparison on the expanded predeclared fixture, retaining complete sanitized prompts/requests/candidates, provider/model identifier and revision where available, SDK version, source commit, run settings, timestamps, seeds, and raw results. Do not call this a reproduction of the historical run.
4. Complete independent coordinator source screening, two independent RCA labels, adjudication, packet and label hashes, then run the existing evaluator once.
5. Generate and verify a clean dependency lock and install in a network-enabled environment; rerun tests and release preflight.
6. Inspect artifacts for secrets/private information, commit and tag the exact source in a Git clone, push and verify the tag. The current source ZIP has no Git history and is not a tagged release.

**Status:** V16 is a stronger evidence candidate and is more informative about deterministic recovery versus no-healing/retry. It is not a completed three-way hard-fault comparison and should not claim that the policy gate causes improved recovery or establishes production safety.
