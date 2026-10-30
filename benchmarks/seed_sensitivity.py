"""Split-seed sensitivity of the deterministic repair validator.

The active fixture currently contributes 24 schema/data-quality/configuration
repair templates. Repeated split seeds reuse these templates; this is a
sensitivity experiment, not an independent sample of operational failures and
not an LLM method comparison. Output paths are timestamped by default to avoid
overwriting historical artifacts.
"""
import argparse
import json
import math
import statistics
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import yaml
from healing.validation.repair_validator import RepairValidator

ROOT = Path(__file__).resolve().parents[1]
CASES_PATH = ROOT / "benchmarks" / "scenarios" / "trial_cases.yaml"


def wilson(k, n, z=1.959963984540054):
    if n == 0:
        return None
    p = k/n
    z2 = z*z
    den = 1 + z2/n
    center = (p + z2/(2*n))/den
    half = z*math.sqrt(p*(1-p)/n + z2/(4*n*n))/den
    return [round(max(0, center-half), 4), round(min(1, center+half), 4)]


def build_incident(case, seed):
    params = dict(case["parameters"])
    if case["failure_type"] == "data_quality":
        params["random_seed"] = 10000 + seed * 13 + int(case["case_id"].split("_")[-1])
    family = case["failure_type"]
    if family == "schema_change":
        msg = f"Schema mismatch | missing={[params['original_column']]} | unexpected={[params['replacement_column']]}"
    elif family == "data_quality":
        msg = f"Input X contains NaN in feature {params['column']!r}."
    else:
        msg = f"The '{params['parameter']}' parameter must have a valid value."
    return SimpleNamespace(
        incident_id=f"SEED-{case['case_id']}-{seed:02d}",
        failure_type=family,
        error_message=msg,
        stage="seed_sensitivity",
        exception_type="ValueError",
        pipeline_config={},
        context={"failure_injection": {"parameters": params, "ground_truth": case.get("ground_truth", {})}},
    )


def build_candidate(case, incident):
    family = case["failure_type"]
    p = incident.context["failure_injection"]["parameters"]
    if family == "schema_change":
        action = "rename_column"
        params = {
            "column_mapping": {p["replacement_column"]: p["original_column"]},
            "semantic_equivalence_required": True,
        }
        target = "input_data"
    elif family == "data_quality":
        action = "impute_missing_values"
        params = {
            "column_scope": "columns_with_missing_values",
            "numeric_strategy": "median",
            "categorical_strategy": "most_frequent",
            "exclude_target_column": True,
        }
        target = "input_data"
    else:
        action = "restore_configuration"
        params = {"changes": [{
            "parameter": p["parameter"],
            "observed_value": p["invalid_value"],
            "proposed_value": 1.0 if p["parameter"] == "C" else 1000,
        }]}
        target = "model_configuration"
    return {
        "candidate_id": f"SEED-CAND-{case['case_id']}-{incident.incident_id.split('-')[-1]}",
        "incident_id": incident.incident_id,
        "failure_type": family,
        "action": action,
        "target": target,
        "parameters": params,
        "rationale": "Pre-specified supported repair for split sensitivity.",
        "evidence": [incident.error_message],
        "validation_checks": [],
        "risks": [],
        "requires_human_approval": False,
        "status": "proposed",
        "generator": "rule_based",
    }


def extract_metrics(report):
    for check in report.get("checks", []):
        if check.get("check") == "finite_evaluation_metrics":
            try:
                return json.loads(check.get("details", "{}"))
            except json.JSONDecodeError:
                return {}
    return {}


def _resolve_output_path(output_path=None):
    if output_path is None:
        now = datetime.now(timezone.utc)
        stamp = now.strftime("%Y%m%dT%H%M%S_%fZ")
        day = now.strftime("%Y-%m-%d")
        path = ROOT / "research_artifacts" / day / f"seed_sensitivity_v2_expanded_{stamp}.json"
    else:
        path = Path(output_path)
        if not path.is_absolute():
            path = ROOT / path
    if path.exists():
        raise FileExistsError(
            f"Refusing to overwrite existing result: {path}. "
            "Choose a new output path to preserve historical evidence."
        )
    return path


def main(n_seeds=20, output_path=None):
    if n_seeds < 1:
        raise ValueError("n_seeds must be at least 1")
    output_path = _resolve_output_path(output_path)
    cases_doc = yaml.safe_load(CASES_PATH.read_text(encoding="utf-8"))
    cases = [c for c in cases_doc["cases"] if c["failure_type"] in {"schema_change", "data_quality", "configuration_error"}]
    rows = []
    for seed in range(n_seeds):
        for case in cases:
            incident = build_incident(case, seed)
            candidate = build_candidate(case, incident)
            validator = RepairValidator()
            validator.pipeline_config["split"]["random_state"] = seed
            report = validator.validate(candidate, incident)
            rows.append({
                "case_id": case["case_id"],
                "failure_type": case["failure_type"],
                "split_seed": seed,
                "data_fault_seed": incident.context["failure_injection"]["parameters"].get("random_seed"),
                "validation_status": report.get("status"),
                "passed": report.get("status") == "passed",
                "reason": report.get("reason", ""),
                "metrics": extract_metrics(report),
                "validation_seconds": report.get("duration_seconds"),
            })
        if (seed + 1) % 5 == 0:
            print(f"Completed split seed {seed + 1}/{n_seeds}")

    pass_count = sum(r["passed"] for r in rows)
    by_family = {}
    for family in sorted({r["failure_type"] for r in rows}):
        group = [r for r in rows if r["failure_type"] == family]
        by_family[family] = {
            "trials": len(group),
            "validation_passes": sum(r["passed"] for r in group),
            "validation_pass_rate": round(sum(r["passed"] for r in group)/len(group), 4),
        }

    metric_summary = {}
    for family in sorted({r["failure_type"] for r in rows}):
        group = [r for r in rows if r["failure_type"] == family]
        all_metrics = defaultdict(list)
        for r in group:
            for key, value in r["metrics"].items():
                if isinstance(value, (int, float)) and math.isfinite(value):
                    all_metrics[key].append(float(value))
        metric_summary[family] = {
            k: {
                "n": len(vals), "mean": round(statistics.mean(vals), 6),
                "population_sd": round(statistics.pstdev(vals), 6),
                "min": round(min(vals), 6), "max": round(max(vals), 6),
            }
            for k, vals in sorted(all_metrics.items()) if vals
        }

    out = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "experiment_id": "deterministic-repair-split-sensitivity-v2-expanded",
        "fault_template_count": len(cases),
        "fault_template_ids": [case["case_id"] for case in cases],
        "split_seed_count": n_seeds,
        "split_seeds": list(range(n_seeds)),
        "trials": len(rows),
        "validation_passes": pass_count,
        "validation_pass_rate": round(pass_count/len(rows), 4) if rows else None,
        "wilson_95_descriptive": wilson(pass_count, len(rows)),
        "by_failure_type": by_family,
        "post-repair_metric_summary": metric_summary,
        "interpretation": (
            f"Descriptive sensitivity analysis of the deterministic validator on {len(cases)} "
            "active project-authored schema/data-quality/configuration templates across "
            f"{n_seeds} split seeds; data-quality injection seeds also vary. Repeated seeds "
            "reuse the same templates and must not be treated as independent operational "
            "failures. This experiment does not run the LLM arms, establish between-method "
            "superiority, or establish generalization to other datasets."
        ),
        "results": rows,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k:v for k,v in out.items() if k != "results"}, indent=2))
    print(f"Output: {output_path}")
    return out

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds", type=int, default=20, help="Number of split seeds to evaluate (default: 20).")
    parser.add_argument("--output", type=Path, default=None, help="Optional output path; existing files are never overwritten.")
    args = parser.parse_args()
    try:
        main(n_seeds=args.seeds, output_path=args.output)
    except (ValueError, FileExistsError) as exc:
        parser.error(str(exc))
