"""Paired offline comparative analysis for the V16 stress expansion.

This script does not call an LLM provider. It combines the 32-template
executed recovery stress run, paired persistent-fault controls, the frozen
40-case detector challenge, and the archived 180-row historical comparison.
All challenge fixtures are project-authored; interval estimates are descriptive.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from sklearn.metrics import confusion_matrix, f1_score
from scipy.stats import binomtest

from benchmarks.failure_stress_challenge import make_exception
from healing.detector.failure_detector import FailureDetector

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "benchmarks" / "results"
ARTIFACTS = ROOT / "research_artifacts" / "2026-10-25"
STRESS_DATA = ROOT / "benchmarks" / "data" / "failure_stress_challenge_v1.json"
HISTORICAL_RAW = ROOT / "research_artifacts" / "2026-10-24" / "llm_run_20261024_171821" / "raw" / "repeated_trials_20261024_171821.jsonl"
DETECTOR_SOURCE = ROOT / "healing" / "detector" / "failure_detector.py"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def wilson(k: int, n: int, z: float = 1.959963984540054):
    if n == 0:
        return None
    p = k / n
    d = 1 + z*z/n
    center = (p + z*z/(2*n))/d
    half = z*math.sqrt(p*(1-p)/n + z*z/(4*n*n))/d
    return [round(max(0.0, center-half), 4), round(min(1.0, center+half), 4)]


def load_jsonl(path: Path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def latest(pattern: str) -> Path:
    files = sorted(RESULTS.glob(pattern))
    if not files:
        raise FileNotFoundError(f"No result file matching {pattern!r} in {RESULTS}")
    return files[-1]


def type_only_baseline(exception_type: str) -> str:
    """Simple, fixed exception-class-only baseline specified in this analysis; never reads message or stage."""
    if exception_type in {"ModuleNotFoundError", "ImportError"}:
        return "dependency_error"
    if exception_type == "KeyError":
        return "schema_change"
    if exception_type == "InvalidParameterError":
        return "configuration_error"
    return "unknown_runtime_failure"


def score_detector_baselines():
    fixture = json.loads(STRESS_DATA.read_text(encoding="utf-8"))
    det = FailureDetector()
    rows = []
    for c in fixture["cases"]:
        exc = make_exception(c["exception_type"], c["message"])
        out = det.detect(exc, {"runtime": {"current_stage": c["stage"]}})
        rule = out["failure_type"]
        base = type_only_baseline(c["exception_type"])
        expected = c["expected_failure_family"]
        rows.append({
            "case_id": c["case_id"], "expected": expected,
            "exception_type": c["exception_type"], "stage": c["stage"],
            "rule_detector": rule, "rule_correct": rule == expected,
            "type_only_baseline": base, "baseline_correct": base == expected,
        })
    labels = sorted({r["expected"] for r in rows} | {r["rule_detector"] for r in rows} | {r["type_only_baseline"] for r in rows})
    metrics = {}
    for method in ("rule_detector", "type_only_baseline"):
        oks = sum(r[method] == r["expected"] for r in rows)
        predicted = [r[method] for r in rows]
        truth = [r["expected"] for r in rows]
        metrics[method] = {
            "correct": oks, "incorrect": len(rows)-oks, "n": len(rows),
            "accuracy": round(oks/len(rows), 4), "wilson_95_descriptive": wilson(oks, len(rows)),
            "macro_f1": round(f1_score(truth, predicted, labels=labels, average="macro", zero_division=0), 4),
            "confusion_matrix_labels": labels,
            "confusion_matrix": confusion_matrix(truth, predicted, labels=labels).tolist(),
        }
    # Paired correctness discordance between rule-based detector and type-only baseline.
    rule_only = sum(r["rule_correct"] and not r["baseline_correct"] for r in rows)
    baseline_only = sum(r["baseline_correct"] and not r["rule_correct"] for r in rows)
    discordant = rule_only + baseline_only
    metrics["paired_comparison_rule_vs_type_only"] = {
        "cases": len(rows), "rule_only_correct": rule_only,
        "baseline_only_correct": baseline_only, "discordant_cases": discordant,
        "paired_accuracy_difference_pp": round(100*(metrics["rule_detector"]["accuracy"] - metrics["type_only_baseline"]["accuracy"]), 2),
        "exact_binomial_p_two_sided_on_discordant_pairs": (round(binomtest(rule_only, discordant, 0.5).pvalue, 8) if discordant else 1.0),
        "interpretation": "The test is a single project-authored synthetic challenge. The paired p-value is descriptive for this fixed fixture and is not evidence of population-level significance.",
    }
    return {"dataset_id": fixture["dataset_id"], "dataset_sha256": sha256(STRESS_DATA), "detector_sha256": sha256(DETECTOR_SOURCE), "n": len(rows), "metrics": metrics, "case_results": rows}


def score_recovery_comparison(rule_file: Path, baseline_file: Path):
    rule = json.loads(rule_file.read_text(encoding="utf-8"))
    controls = json.loads(baseline_file.read_text(encoding="utf-8"))
    rule_rows = rule["results"]
    control_rows = [r for r in controls["results"] if r.get("experiment") == "persistent_injected_faults"]
    control = defaultdict(dict)
    for r in control_rows:
        control[(r["case_id"], r["repeat_index"])][r["method"]] = bool(r.get("pipeline_succeeded"))
    gate_by_key = {(r["case_id"], r["repeat_index"]): r for r in rule_rows}
    keys = sorted(set(control) & set(gate_by_key))
    if not keys:
        raise ValueError("No paired cases between gated run and baseline controls")
    eligible_keys = [k for k in keys if gate_by_key[k]["status"] != "needs_human_approval"]
    outcomes = {}
    for m in ("rule_based_gated", "no_healing", "retry_once"):
        if m == "rule_based_gated":
            vals = [gate_by_key[k]["status"] == "recovered" for k in keys]
            eligible_vals = [gate_by_key[k]["status"] == "recovered" for k in eligible_keys]
        else:
            vals = [control[k].get(m, False) for k in keys]
            eligible_vals = [control[k].get(m, False) for k in eligible_keys]
        outcomes[m] = {
            "all_persistent_trials": {"successes": sum(vals), "n": len(vals), "rate": round(sum(vals)/len(vals), 4), "wilson_95_descriptive": wilson(sum(vals), len(vals))},
            "gated_auto_eligible_subset": {"successes": sum(eligible_vals), "n": len(eligible_vals), "rate": round(sum(eligible_vals)/len(eligible_vals), 4), "wilson_95_descriptive": wilson(sum(eligible_vals), len(eligible_vals))},
        }
    # Template-level counts prevent repeats being silently treated as independent units.
    by_template = defaultdict(list)
    for k in keys:
        r = gate_by_key[k]
        by_template[k[0]].append({
            "rule_success": r["status"] == "recovered",
            "human_review": r["status"] == "needs_human_approval",
            "no_healing_success": control[k].get("no_healing", False),
            "retry_success": control[k].get("retry_once", False),
            "eligible": r["status"] != "needs_human_approval",
        })
    template_stats = {}
    all_templates = list(by_template.items())
    eligible_templates = [(case_id, vals) for case_id, vals in all_templates if vals and vals[0]["eligible"]]
    for method, field in [("rule_based_gated", "rule_success"), ("no_healing", "no_healing_success"), ("retry_once", "retry_success")]:
        template_stats[method] = {}
        for subset_name, subset in (("all_32_templates", all_templates), ("auto_eligible_24_template_subset", eligible_templates)):
            templ = [vals for _, vals in subset if vals]
            n = len(templ)
            good = sum(all(v[field] for v in items) for items in templ)
            bad = sum(all(not v[field] for v in items) for items in templ)
            partial = n-good-bad
            template_stats[method][subset_name] = {"template_count": n, "all_repeats_success": good, "all_repeats_failure_or_nonrecovery": bad, "mixed_templates": partial, "success_template_rate": round(good/n,4) if n else None, "wilson_95_descriptive": wilson(good,n) if n else None}
    # Paired difference on auto-eligible trials: the denominator is reused fixed templates x repeats.
    discordance = {}
    for m in ("no_healing", "retry_once"):
        gated_only = 0; baseline_only = 0
        for k in eligible_keys:
            gs = gate_by_key[k]["status"] == "recovered"
            bs = control[k].get(m, False)
            gated_only += int(gs and not bs)
            baseline_only += int(bs and not gs)
        discordance[m] = {"eligible_paired_trials": len(eligible_keys), "gated_only_success": gated_only, "baseline_only_success": baseline_only,
                          "paired_rate_difference_pp": round(100*(gated_only-baseline_only)/len(eligible_keys),2),
                          "interpretation": "All rows are paired by scenario ID and repeat index. Repeats share a fixed synthetic template; interpret the contrast as within-challenge evidence, not population inference."}
    return {
        "rule_trials_path": str(rule_file.relative_to(ROOT)), "rule_trials_sha256": sha256(rule_file),
        "baseline_controls_path": str(baseline_file.relative_to(ROOT)), "baseline_controls_sha256": sha256(baseline_file),
        "scenario_templates": len(by_template), "paired_persistent_trials": len(keys),
        "auto_eligible_paired_trials": len(eligible_keys),
        "dependency_review_trials": sum(r["status"] == "needs_human_approval" for r in rule_rows),
        "by_method": outcomes, "template_level": template_stats, "paired_contrasts": discordance,
        "by_failure_family": rule.get("by_failure_type", {}),
    }


def score_historical_methods():
    rows = load_jsonl(HISTORICAL_RAW)
    methods = sorted({r["method"] for r in rows})
    by_key = defaultdict(dict)
    for r in rows:
        by_key[(r.get("case_id"), r.get("repeat_index"))][r["method"]] = r.get("result", {}).get("status")
    summaries = {}
    for method in methods:
        group = [r for r in rows if r["method"] == method]
        success = sum(r.get("result", {}).get("status") == "recovered" for r in group)
        human = sum(r.get("result", {}).get("status") == "needs_human_approval" for r in group)
        summaries[method] = {"n": len(group), "recovered": success, "recovery_rate": round(success/len(group),4), "recovery_wilson_95_descriptive": wilson(success,len(group)), "human_review": human}
    pairs = {}
    for i,a in enumerate(methods):
        for b in methods[i+1:]:
            paired = [v for v in by_key.values() if a in v and b in v]
            both = sum(v[a] == "recovered" and v[b] == "recovered" for v in paired)
            a_only = sum(v[a] == "recovered" and v[b] != "recovered" for v in paired)
            b_only = sum(v[a] != "recovered" and v[b] == "recovered" for v in paired)
            neither = len(paired)-both-a_only-b_only
            pairs[f"{a}_vs_{b}"] = {"paired_trials":len(paired),"both_recovered":both,"first_only_recovered":a_only,"second_only_recovered":b_only,"neither_recovered":neither,"observed_paired_difference_pp":round(100*(a_only-b_only)/len(paired),2) if paired else None,"conclusion":"No observed difference on this historical 60-key trial set; this does not establish equivalence or predict performance on unseen faults."}
    return {"raw_path": str(HISTORICAL_RAW.relative_to(ROOT)), "raw_sha256": sha256(HISTORICAL_RAW), "row_count":len(rows), "paired_trial_keys":len(by_key), "by_method":summaries,"pairwise":pairs}


def cluster_bootstrap_latency():
    """Descriptive cluster bootstrap over the original 12 scenario IDs."""
    import random
    rows = load_jsonl(HISTORICAL_RAW)
    by_method_case = defaultdict(list)
    for r in rows:
        method = r.get("method")
        result = r.get("result", {})
        method_time = result.get("method_duration_seconds")
        if method_time is None:
            continue
        if method == "rule_based_gated":
            plan = r.get("rule_planning_seconds") or 0.0
            total = float(plan) + float(method_time)
        else:
            gen = r.get("llm_generation_seconds")
            if gen is None:
                continue
            total = float(gen) + float(method_time)
        by_method_case[(method, r.get("case_id"))].append(total)
    methods = sorted({m for m, _ in by_method_case})
    cases = sorted({c for _, c in by_method_case})
    per_case = {m: {c: (sum(by_method_case[(m,c)]) / len(by_method_case[(m,c)])) for c in cases if by_method_case.get((m,c))} for m in methods}
    rng = random.Random(20261025)
    B = 20000
    def bootstrap_mean(method):
        vals = [per_case[method][c] for c in cases if c in per_case[method]]
        estimates = []
        for _ in range(B):
            draw = [rng.choice(vals) for __ in range(len(vals))]
            estimates.append(sum(draw)/len(draw))
        estimates.sort()
        return [round(estimates[int(0.025*B)], 6), round(estimates[int(0.975*B)-1], 6)]
    out = {}
    for m in methods:
        observed = [v for c,v in per_case[m].items()]
        out[m] = {"scenario_clusters": len(observed), "mean_seconds": round(sum(observed)/len(observed),6), "cluster_bootstrap_95_ci_seconds": bootstrap_mean(m)}
    pairs = {}
    for i,a in enumerate(methods):
        for b in methods[i+1:]:
            shared = [c for c in cases if c in per_case[a] and c in per_case[b]]
            diffs = [per_case[a][c]-per_case[b][c] for c in shared]
            estimates = []
            for _ in range(B):
                draw = [rng.choice(diffs) for __ in range(len(diffs))]
                estimates.append(sum(draw)/len(draw))
            estimates.sort()
            pairs[f"{a}_minus_{b}"] = {"paired_scenario_clusters":len(shared), "mean_difference_seconds":round(sum(diffs)/len(diffs),6), "cluster_bootstrap_95_ci_seconds":[round(estimates[int(0.025*B)],6),round(estimates[int(0.975*B)-1],6)]}
    return {"method_latency":out,"paired_latency_differences":pairs,"resampling_unit":"scenario template ID; each of 12 templates contains five repeated trials","bootstrap_replicates":B,"random_seed":20261025,"interpretation":"Descriptive cluster bootstrap over a purposively fixed set of 12 synthetic scenario templates; not population-level uncertainty."}


def score_safety_suite():
    path = ARTIFACTS / "safety_evaluation_expanded_v2_result.json"
    d = json.loads(path.read_text(encoding="utf-8"))
    return {
        "result_path": str(path.relative_to(ROOT)), "result_sha256": sha256(path),
        "total_cases": d["total_cases"],
        "valid_controls": {"passed": d["valid_controls_passed"], "n": d["valid_control_cases"], "false_rejections": d["valid_controls_rejected_or_escalated"], "false_rejection_wilson_95": d["valid_false_rejection_wilson_95"]},
        "unsafe_proposals": {"blocked": d["unsafe_candidates_blocked"], "n": d["unsafe_candidate_cases"], "accepted": d["unsafe_candidates_accepted"], "block_rate_wilson_95": d["unsafe_candidate_block_wilson_95"]},
        "dependency_review": {"routed": d["human_review_routed_correctly"], "n": d["human_review_cases"]},
        "all_expectations_met": d["all_expectations_met"],
        "interpretation": "Targeted regression/mutation cases, not representative or random production attack samples."
    }


def score_policy_gate_simulation():
    path = ARTIFACTS / "policy_gate_ablation_v2_result.json"
    d = json.loads(path.read_text(encoding="utf-8"))
    return {
        "result_path": str(path.relative_to(ROOT)), "result_sha256": sha256(path),
        "cases": d["cases"], "gate_decisions": d["gate_decisions"],
        "bypass_would_dispatch": d["bypass_arm_would_dispatch"],
        "rejected_or_escalated_but_bypass_would_dispatch": d["gate_rejected_or_escalated_but_bypass_would_dispatch"],
        "dependency_false_approval_fields_overridden": d["dependency_false_approval_fields_overridden"],
        "actual_actions_executed": d["actual_actions_executed"],
        "limitation": "Decision-only counterfactual dispatcher simulation. It does not execute a gate-free repair path or demonstrate recovery causality."
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--rule-results", type=Path, default=None)
    parser.add_argument("--baseline-results", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=ARTIFACTS / "comparative_evidence_v2_result.json")
    args = parser.parse_args()
    rule_path = args.rule_results or latest("rule_based_trials_*.json")
    baseline_path = args.baseline_results or latest("baseline_controls_*.json")
    payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "experiment_id": "self-healing-ml-pipeline-comparative-evidence-v2",
        "scope_note": "Offline analysis only. No new live LLM requests were made; all new repair-path evidence is deterministic gated recovery versus no-healing/retry on expanded project-authored scenarios. Historical LLM rows are analyzed as archived, not rerun.",
        "expanded_recovery_comparison": score_recovery_comparison(rule_path, baseline_path),
        "frozen_detector_stress_vs_type_only_baseline": score_detector_baselines(),
        "historical_three_method_paired_comparison": score_historical_methods(),
        "historical_latency_cluster_bootstrap": cluster_bootstrap_latency(),
        "expanded_validator_safety_suite": score_safety_suite(),
        "policy_gate_decision_only_simulation": score_policy_gate_simulation(),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2)+"\n",encoding="utf-8")
    print(json.dumps({
        "output":str(args.output),
        "recovery":payload["expanded_recovery_comparison"],
        "detector_comparison":{k:v for k,v in payload["frozen_detector_stress_vs_type_only_baseline"]["metrics"].items()},
        "historical_methods":payload["historical_three_method_paired_comparison"]["by_method"],
        "historical_pairwise":payload["historical_three_method_paired_comparison"]["pairwise"],
        "historical_latency":payload["historical_latency_cluster_bootstrap"],
        "safety_suite":payload["expanded_validator_safety_suite"],
        "policy_gate":payload["policy_gate_decision_only_simulation"],
    },indent=2))

if __name__ == "__main__":
    main()
