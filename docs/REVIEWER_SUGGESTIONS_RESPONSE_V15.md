# Response to seven requested research improvements — V15 candidate

This response distinguishes implemented changes from evidence that remains unavailable. The manuscript is still a venue-neutral candidate, not a fully accepted/released submission.

| Requested improvement | V15 action/evidence | Status and remaining limitation |
|---|---|---|
| 1. Make the method comparison meaningful using harder/unseen faults | Added a 40-case alternate-signature family-detector stress fixture; it classified 32/40 families correctly (80.0%, Wilson 95% interval 65.2%-89.5%, macro-F1 0.8167). | **Partially addressed.** It stresses the detector but does not rerun all three repair pathways on the same harder faults. The historical methods remain tied at 45/60. Independent fault construction and a fresh live-LLM comparison remain needed. |
| 2. Add no-healing/retry and LLM without policy gate baselines | Reconciled no-healing and retry-once controls: 0/60 on persistent faults each; retry once 5/5 on a separate transient-timeout control. Clarified that `llm_direct_isolated` omits the separate preflight validator but retains central policy restrictions. The 36-case gate-bypass arm remains non-executing. | **Partially addressed.** The controls already existed. A genuinely policy-free live LLM repair arm has not been run, and no causal end-to-end gate claim is made. Do not execute unrestricted repairs in a real environment. |
| 3. Fix circular 100% RCA accuracy claim | Manuscript now calls 60/60 on configured scenarios scenario-label agreement, not held-out accuracy. The frozen developer-authored 36-case conditional challenge is 33/36 (91.7%; Wilson 95% interval 78.2%-97.1%). A separate 40-case end-to-end failure-family detector stress fixture is 32/40. | **Improved but independent validation pending.** Both new/previous challenge fixtures are project-authored. The V2 public-issue annotation candidate pool is not independently source-reviewed, annotated, and adjudicated, so no external score is reported. |
| 4. Strengthen safety and test valid-repair false rejection | Expanded targeted suite to 205 cases: 50 valid, 130 unsafe/mutation, 25 dependency review. Initial run detected three extra-field proposals erroneously passing. Validator and candidate validation were tightened to reject unknown fields; after fix 50/50 valid accepted, 130/130 unsafe blocked, 25/25 dependency cases routed for review. | **Addressed as targeted regression testing, not broad security validation.** False rejection is 0/50 (Wilson 95% interval 0%-7.1%); these constructed fixtures are not a probability estimate of real-world adversarial safety. |
| 5. Report LLM setup, model and prompt | Manuscript and `LLM_PROMPT_SPECIFICATION_V15.md` describe the near-time manifest (`openai/gpt-oss-20b`, Groq-compatible endpoint, `openai==3.20.0`, temperature 0, JSON-object response format), current source-defined prompts, failure-specific contracts, and source hashes. | **Partially addressed.** The historical manifest is not full per-trial request provenance; `top_p`/token limits are unspecified, model revision is not immutably pinned, prompts/completions were not retained, and no historical Git SHA exists. Current prompt hashes do not retroactively bind the old run. |
| 6. Add uncertainty and seed/data-split variation | Added descriptive Wilson intervals and 20-seed sensitivity on nine existing templates (180/180 validation checks); data-quality mean accuracy 0.9804 (SD 0.0110), F1 0.9846 (SD 0.0086); configuration mean accuracy 0.9798 (SD 0.0115), F1 0.9841 (SD 0.0090). | **Partially addressed.** Same dataset and templates are reused, the seed exercise does not rerun LLM arms, and multi-dataset/multimodel external validation remains absent. Do not treat 180 seed repeats as 180 independent faults. |
| 7. Add repository and pinned dependencies | Manuscript points to `https://github.com/adityaraj-12/self-healing-ml-pipeline`; project includes pinned `requirements.txt` and `requirements-llm.txt`, with `openai==3.20.0`. | **Partially addressed.** This local updated candidate has not been pushed as a tagged Git release. Historical source provenance remains incomplete, and a clean network-enabled install from a verified generated lockfile has not been completed. |

## Reproducible commands

From the project root, with the pinned core environment:

```bash
python -m pytest -q
python -m benchmarks.safety_evaluation
python -m benchmarks.failure_stress_challenge
python -m benchmarks.seed_sensitivity
python -m benchmarks.diagnosis_locked_evaluation
python -m benchmarks.policy_gate_ablation
python -m benchmarks.baseline_controls --repeats 5
```

The live-LLM trial command needs provider credentials and network access and was not run during this update. A future fresh live-LLM run should record all sanitized requests and raw candidates, the actual source commit, provider/model revision, SDK, prompt hash, generation settings, and experiment seed information before results are inspected.
