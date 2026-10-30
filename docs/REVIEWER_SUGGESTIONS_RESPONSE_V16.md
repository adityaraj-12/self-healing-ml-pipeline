# Response to seven requested research improvements — V16 candidate

This response separates actual new measurements from unresolved work. The manuscript remains a venue-neutral candidate. No new live LLM requests were made in the current environment.

| Requested improvement | V16 action/evidence | Status and remaining limitation |
|---|---|---|
| 1. Make the comparison meaningful using harder/unseen faults | Ran a new paired deterministic recovery extension on 32 fixed scenario templates (eight per family, five repeats): gated recovery 120/160 overall; 120/120 automatically eligible trials; 40/40 dependency cases escalated. The same matched auto-eligible cases yielded 0/120 success for no-healing and 0/120 for retry-once. On the frozen 40-case detector fixture, the message-and-stage detector scored 32/40 versus 12/40 for an exception-class-only baseline defined in the current analysis script (not externally preregistered). | **Partially addressed.** This strengthens deterministic-vs-control and detector-vs-baseline comparisons on project-authored synthetic fixtures. The three historical repair paths remain tied at 45/60. No live LLM arm ran on the expanded challenge, so method superiority on hard faults remains unresolved. The expanded templates vary parameters/columns within four known families rather than representing unseen real-world mechanisms. |
| 2. Add no-healing/retry and LLM without policy gate baselines | Re-ran paired no-healing/retry controls across 32 templates (160 trials each), alongside the gated path. Persistent controls each recovered 0/160; separate transient timeout remains no-healing 0/5 versus retry-once 5/5. The policy gate simulation still rejects 28, escalates 5, and allows 3/36 to continue to validation; its bypass would dispatch all 36. | **Partially addressed.** The bypass arm remains decision-only, with no action execution. `llm_direct_isolated` is not fully policy-free; it retains isolation and executor restrictions. No causal end-to-end gate ablation or unrestricted LLM executor was tested. |
| 3. Fix circular 100% RCA accuracy claim | The paper describes 60/60 configured labels as scenario-label agreement, not held-out accuracy. A locked conditional RCA challenge scored 33/36; the 40-case top-level detector challenge scored 32/40 and was compared with the exception-class-only baseline. | **Improved; independent annotation pending.** All challenge fixtures are project-authored and not blinded/independently labelled. The external candidate pool has not been independently source-reviewed, annotated, and adjudicated. |
| 4. Strengthen safety and test valid-repair false rejection | Fresh 205-case run: 50/50 valid controls accepted (0/50 false rejection; Wilson 95% interval 0%-7.13%), 130/130 unsafe/mutated proposals blocked (block-rate interval 97.13%-100%), and 25/25 dependency proposals routed to review. Extra-field bypasses discovered in an earlier mutation run were blocked after validator changes. | **Addressed as targeted regression evidence, not general security validation.** Fixtures are intentionally constructed and are not a representative sample of operational adversarial proposals. |
| 5. Report LLM setup, model and prompt | `LLM_PROMPT_SPECIFICATION_V16.md` records current prompt templates, source hashes, near-time historical configuration (`openai/gpt-oss-20b`, Groq-compatible endpoint, `openai==3.20.0`, temperature 0, JSON-object format). | **Partially addressed.** Historical manifest is not full per-trial request provenance. No immutable model revision, complete historical prompt/output log, or historical Git SHA exists; current hashes do not retroactively reconstruct the run. |
| 6. Add uncertainty and seed/data-split variation | Added paired recovery rates with Wilson intervals; template-level interval views to avoid treating five repeats as independent. Added a 20,000-replicate cluster bootstrap over the 12 historical scenario IDs for timing summaries and paired differences. Retained the 20-seed sensitivity result and 205-case safety interval reporting. | **Partially addressed.** These are descriptive analyses over fixed synthetic scenarios and one dataset/model. They do not replace independent fault families, multi-dataset experiments, or a fresh paired live-LLM run. |
| 7. Add repository and pinned dependencies | The manuscript identifies `https://github.com/adityaraj-12/self-healing-ml-pipeline`; pinned core and LLM requirement files remain in the source candidate. | **Partially addressed.** The V16 candidate ZIP is not a tagged Git release. A clean network-enabled install using a generated/verified lockfile and exact commit-to-run mapping remains pending. |

## Reproduction commands

From the project root, using the pinned Python 3.13 core environment:

```bash
python -m pytest -q
python -m benchmarks.rule_based_trials --repeats 5
python -m benchmarks.baseline_controls --repeats 5
python -m benchmarks.safety_evaluation
python -m benchmarks.failure_stress_challenge
python -m benchmarks.comparative_evidence_v2
python -m benchmarks.diagnosis_locked_evaluation
python -m benchmarks.policy_gate_ablation
```

The current offline test suite reports 115 passed. Live LLM reruns require an SDK, valid provider credentials, network access, and per-trial sanitized request/output capture. They were not run here. Do not report new LLM results for the expanded challenge until that run is performed.
