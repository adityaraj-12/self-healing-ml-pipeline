# Research notes and open questions

## Current evidence

The five-run V17 live benchmark evaluated 32 fixed templates using three methods, giving 480 rows overall and 160 per method. Each method recorded 120 recoveries and 40 human-review outcomes. The three methods had identical outcomes in all 160 paired case-run units: 120 joint recoveries and 40 joint human-review outcomes, with zero discordant outcomes. The direct and validated LLM arms used the same generated candidate within each paired unit. This is an observed tie on a repeated, project-authored test set; it does not demonstrate a recovery advantage for the validator or statistical equivalence between methods. The five runs reuse the same 32 templates and are not independent operational incidents.

The deterministic V16 expanded stress comparison separately recorded 120/160 recoveries (75%) across 32 fixed templates. The persistent-fault no-healing and retry-once controls each recorded 0/160. These results concern the deterministic repair path and must not be conflated with the V17 three-method live comparison.

The expanded validator regression suite contains 205 targeted cases: 50/50 valid controls passed, 130/130 deliberately unsafe or mutated proposals were blocked, and 25/25 dependency proposals were routed to human review. The earlier 85-case suite remains historical evidence. These constructed cases are regression fixtures, not a representative sample of operational attacks.

The split-seed sensitivity experiment covered 24 fixed templates over 20 split seeds: 480/480 validation checks passed, with 160 checks per fault family. These are repeated template/seed checks, not 480 independent incidents or evidence of generalization to new fault mechanisms.

The 36-proposal policy-gate simulation rejected 28 proposals, escalated five, and permitted three to proceed to validation. Four forged dependency-approval fields were overridden. No actions were executed, so this is evidence about decision behavior only, not end-to-end recovery causality.

The 36-case locked RCA synthetic set scored 33/36. It was frozen against the hash of `healing/rca/rule_based_rca.py`, but was authored within the project, not by an independent third party. It must be described as a locked synthetic challenge rather than a blind external benchmark. Three messages exposed unhandled variants: `Object dtype`, a `warm_start` setting without a recognized parameter/argument pattern, and an unquoted module name.

## What is still missing

1. A genuinely independent or third-party blind RCA benchmark, with evidence excerpts and labels frozen before evaluation.
2. A true end-to-end policy-gate ablation linked to actual proposal generation and controlled repair execution. V2 adds a matched comparison using the real validator on 36 fixed proposals, but it does not call `RecoveryEngine.recover()` or execute repairs; end-to-end recovery effects remain unmeasured.
3. Full-pipeline evaluation across additional datasets, model families, and realistic or mixed fault mechanisms. Existing helper-level multi-dataset checks do not establish full-pipeline generalization.
4. A clean installation in a fresh isolated environment using `pip install --require-hashes --only-binary=:all: -r requirements-llm.lock.txt`, followed by `pip check` and the test suite.
5. Additional independently authored fault templates and fault-generation variation. The current split-seed experiment varies split seeds over fixed templates; it does not establish robustness to new fault mechanisms.
6. A versioned repository commit and release archive with reproducible commit-level provenance. The historical V17 manifests do not contain Git commit IDs; source-file hashes were checked instead.

## Research integrity boundaries

The copied-workspace repair sandbox is not OS-level or container-level security isolation. Do not describe it as a security boundary.

Do not tune the RCA implementation against `benchmarks/data/rca_locked_v1.json` and continue calling that same set held out. If the rules are changed in response to its three misses, create a new versioned test set or obtain an independently authored evaluation set. Similarly, the policy-gate bypass in the current script never executes actions and must not be described as a real unrestricted executor.


## Public-source RCA probe (2026-10-23)

The frozen rule implementation matched 15/15 manually labelled codes in the new public-issue-source probe. This was a post-hoc curated set based on public reports and official source text, not a blind benchmark. Do not call it an independent test or production-accuracy estimate. It is useful only as a compatibility smoke test across publicly observed wording. The next rigorous step remains a third-party-labelled set or a sealed dataset chosen without inspecting the rule implementation.

## Policy-gate ablation V2 evidence (2026-10-31)

V2 advances the earlier decision-only simulation by comparing matched proposals through the real validator. Across 36 fixed proposals, the gated arm rejected 28 before validation and invoked the validator eight times (three passed, five required review). Without the initial gate, all 36 reached the same validator (three passed, 22 rejected, 11 required review). Terminal decisions agreed on 30 proposals and differed on six invalid dependency actions, which were blocked by the gate but routed to human review without it. Four forged dependency-approval flags were overridden in the gated arm.

No recovery execution occurred. The no-policy arm bypasses only the initial policy gate; validator safeguards remain active. This is evidence about proposal filtering and validator routing, not end-to-end recovery effectiveness or general safety. A matched experiment that executes controlled recovery in both arms remains future work.
