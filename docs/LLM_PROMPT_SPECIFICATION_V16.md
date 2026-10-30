# LLM prompt and configuration specification — V16 research candidate

**Purpose.** This document records the current source-defined prompts and model-call settings for review and future reproduction. It is not a reconstruction of every prompt sent in the historical 2026-10-24 run: the historical JSONL does not retain all prompts or raw model completions, and that run did not record a Git commit SHA.

## Historical run configuration recorded in the near-time manifest

- Model identifier: `openai/gpt-oss-20b`
- OpenAI-compatible endpoint: `https://api.groq.com/openai/v1`
- SDK version: `openai==3.20.0`
- Python version recorded in the manifest: `3.13.15`
- Sampling temperature: `0`
- Response format: `{"type":"json_object"}`
- `top_p` and token limits: not explicitly set in the recorded code; provider defaults apply
- Repair generation: up to two candidate attempts after structural rejection
- RCA generation: one request

The provider identifier above is not an immutable provider model revision. These values are near-time manifest evidence; they should not be described as exact historical request-level provenance.

## Current LLM repair generator

Source file: `healing/repair/llm_repair_generator.py`

**System message (verbatim from the current source):**

> You generate evidence-grounded ML pipeline repair proposals. Follow the permitted action contract. Never execute a repair.

**User-message structure:**

The user content is composed from the following template, with incident, RCA, and failure-specific requirements serialized into the request:

```text
Generate one evidence-grounded repair candidate.

INCIDENT:
{incident.to_dict() as indented JSON}

ROOT-CAUSE ANALYSIS:
{rca.to_dict() as indented JSON}

FAILURE-SPECIFIC REQUIREMENTS:
{action_instruction}

Return one valid JSON object with these top-level keys:
- action
- parameters
- rationale
- evidence
- validation_checks
- risks
- requires_human_approval

Requirements:
1. Follow the failure-specific action and parameters format exactly.
2. Do not reuse parameter fields belonging to another failure type.
3. Use only the incident evidence and preserved baseline.
4. Do not generate Python code or shell commands.
5. Do not execute or apply the proposed repair.
6. Evidence, validation_checks and risks must be JSON arrays of strings.
7. Return JSON only.
```

Failure-specific contract, implemented in source:

- **Schema change:** exactly one observed missing column and one unexpected column; `rename_column` with `column_mapping` from unexpected/source column to expected/target column, plus `semantic_equivalence_required: true`. Semantic equivalence is still checked by validation; similar names alone are not proof.
- **Data quality:** `impute_missing_values` using median for numeric columns, most-frequent for categorical columns, scope limited to columns with missing values, and target-column exclusion. The automated path only accepts the `missing_feature_values` root-cause code.
- **Configuration error:** `restore_configuration` may only change parameters present in both current and preserved baseline configurations, and the proposed value must equal the preserved baseline value.
- **Dependency error:** `verify_dependency`, exact observed module name when available, `automatic_install: false`, requirement/import-name checks, and human approval required. Package installation is prohibited.

The generator validates the top-level plan keys, failure-specific parameter keys, schema mapping, imputation contract, configuration-change keys/values, and dependency-installation policy before it returns a candidate. Unknown fields are rejected rather than ignored.

## Current LLM RCA

Source file: `healing/rca/llm_rca.py`

**System message (verbatim from the current source):**

> You are an ML pipeline root-cause analysis system. Analyze only the supplied evidence. Do not invent missing information. Return a concise structured diagnosis. Do not modify or execute code.

**User-message fields:** detected failure type, pipeline stage, exception type, error message, serialized pipeline configuration, and serialized runtime context.

**Requested JSON keys:** `failure_type`, `root_cause`, `evidence`, `repair_target`, `suggested_action`, and `confidence` (0–1).

**Rules stated in the current prompt:** use only supplied evidence; do not invent files, columns, or parameters; do not generate executable code; separate observed evidence from inferred cause; confidence must be between 0 and 1.

## Current source hashes

These hashes are for the source files included in this V16 local candidate, not a claim about the source executed in the historical run:

| File | SHA-256 |
|---|---|
| `healing/repair/llm_repair_generator.py` | `15e873773fc1c9902f241abd3ed325178786fba64696475bec1366caf6688090` |
| `healing/rca/llm_rca.py` | `b4e8815fcaeebbc02f09035bf13f866c71226472fb3f0e337654c262fa2eb7c1` |
| `healing/validation/repair_validator.py` | `f13a2f7a3681b923aafaaeb52401f09dd233a19e9e83e04876e98c2c735912db` |
| `benchmarks/data/failure_stress_challenge_v1.json` | `63055cbc68567c3bfc678a4c3a82348f3bc07f6b9aeddfc3b4c3853890bf87de` |
| `benchmarks/scenarios/trial_cases.yaml` (V16 expanded 32-template fixture) | `45a40b085f160671ac766e5cb27b6c8d9f956a8134478cc8bd27f34d6ebf32a3` |
| `benchmarks/comparative_evidence_v2.py` | `fa3d3fd4d85bf9ac622b2c200c7df923579b521d0190f8921ca4aa18a32b7ebe` |

## Reproduction notes

Install the pinned core and LLM dependencies from `requirements-llm.txt`, configure `OPENAI_MODEL`, `OPENAI_API_KEY`, and optionally `OPENAI_BASE_URL` outside version control, and retain a sanitized manifest plus raw request/response records for each newly conducted run. Do not publish secrets. A new run will provide new-run provenance only; it does not retroactively reconstruct the exact historical prompts or raw model outputs.

The local environment used for this V16 candidate does not have the `openai` package installed and neither `OPENAI_API_KEY` nor `GROQ_API_KEY` is configured. Therefore, no new live LLM trial was run on the expanded 32-template challenge. Offline results in V16 cover the deterministic repair path, no-healing/retry controls, fixed detector stress baseline, policy-decision simulation, and validator regression suite; they do not supply new live-LLM comparative data.
