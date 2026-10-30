# Implemented architecture

## Runtime flow

1. **Pipeline execution:** load the dataset, check its feature contract, preprocess data, fit the configured classifier, evaluate it, and persist artifacts.
2. **Failure detection and incident capture:** when an exception occurs, retain the stage, exception text, coarse failure type, and scenario metadata where available.
3. **Rule-based root-cause analysis:** map the coarse failure type and message to a specific root-cause code. Unknown or unsupported cases should remain unknown/unclassified rather than be forced into a supported repair path.
4. **Candidate generation:** the deterministic planner or optional LLM integration creates a structured proposal. Candidate generation is not authorization.
5. **Action policy:** enforce action/failure-type compatibility. Dependency changes always require human approval; candidate-supplied approval flags are not trusted.
6. **Sandbox validation:** recreate the injected fault in an isolated workspace and verify supported data/configuration invariants. No package installation is performed by the validator.
7. **Controlled recovery:** reapply the permitted action in a clean recovery run, execute the relevant pipeline stages, save the model, reload it, and check prediction/metric consistency.

## Trust boundaries

The language model is an untrusted proposal generator. A candidate is not allowed to run arbitrary Python or shell commands. The implemented allowlist restricts action names by coarse fault type, while validators inspect supported action parameters and data/configuration invariants. Dependency modifications are escalated rather than performed automatically.

The policy-gate ablation in `benchmarks/policy_gate_ablation.py` is decision-only. Its bypass is a simulated dispatcher and never executes a proposed action. Do not interpret it as a live unrestricted executor or as a measurement of end-to-end recovery performance.

## Main code locations

- `pipeline/`: data loading, schema checks, preprocessing, training, evaluation, runner.
- `failures/`: controlled fault classes and injection.
- `healing/rca/`: rule-based RCA and optional LLM RCA.
- `healing/repair/`: candidate representation, planners/generators, and action policy.
- `healing/validation/`: sandbox and repair validator.
- `healing/recovery/`: allowlisted execution and recovery orchestration.
- `benchmarks/`: repeated trials, no-healing/retry controls, validator suite, locked RCA evaluation, and policy-decision simulation.

## Limits

The implementation is a controlled research prototype, not a production recovery agent. The benchmark uses one dataset/model family and synthetic faults. The historical live LLM comparison is not fully reproducible until its exact model and request record are restored.
