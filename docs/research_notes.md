# Research notes and open questions

## Current evidence

The current prototype shows that selected fault injections can be connected to incident capture, rule-based diagnosis, candidate proposals, a bounded action policy, sandbox checks, controlled recovery, and artifact verification. The deterministic path recovered 45/60 configured persistent-fault trials (75%). No-healing and retry-once controls recovered 0/60 on the same persistent faults. A separate transient timeout control behaved as expected for a one-shot error (retry-once 5/5, no-healing 0/5).

The 85-case validator regression suite passed all expected outcomes. A separate 36-proposal decision simulation showed that the actual action/failure allowlist rejected 28 unsupported or mismatched proposals and routed five dependency proposals to human review; the simulated bypass executed no actions.

The 36-case locked RCA synthetic set scored 33/36. It was frozen against the hash of `healing/rca/rule_based_rca.py`, but was authored within the project, not by an independent third party. It must be described as a locked synthetic challenge rather than a blind external benchmark. Three messages exposed unhandled variants: `Object dtype`, a `warm_start` setting without a recognized parameter/argument pattern, and an unquoted module name.

## What is still missing

1. A genuinely independent or third-party blind RCA benchmark, finalized before evaluating the rules.
2. A full policy-gate ablation linked to actual LLM proposal generation, carried out using a simulated executor for dangerous actions. The current policy ablation only tests action/failure allowlist and approval assignment.
3. A fresh live LLM run with exact provider/model/version, SDK, endpoint, prompt revision, generation options, raw candidates, and trial-level outputs.
4. Repeated experiments across data-split and fault-generation seeds; the same scenario template repeated five times is not five different fault types.
5. Additional datasets/model families and realistic or mixed faults.
6. A versioned repository commit matching the artifact archive and the paper.

## Research integrity boundaries

Do not tune the RCA implementation against `benchmarks/data/rca_locked_v1.json` and continue calling that same set held out. If the rules are changed in response to its three misses, create a new versioned test set or obtain an independently authored evaluation set. Similarly, the policy-gate bypass in the current script never executes actions and must not be described as a real unrestricted executor.


## Public-source RCA probe (2026-10-23)

The frozen rule implementation matched 15/15 manually labelled codes in the new public-issue-source probe. This was a post-hoc curated set based on public reports and official source text, not a blind benchmark. Do not call it an independent test or production-accuracy estimate. It is useful only as a compatibility smoke test across publicly observed wording. The next rigorous step remains a third-party-labelled set or a sealed dataset chosen without inspecting the rule implementation.
