#!/usr/bin/env python3
"""Offline-capable release preflight for the self-healing ML pipeline.

Checks source hygiene, pinned dependencies, and the archived 2026-10-24 repeated
trial summary against its raw JSONL. Optionally runs the repository test suite.
It never reads or writes API-key values.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata as md
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from collections import defaultdict
from statistics import mean
from datetime import datetime, timezone

RUN_REL = Path("research_artifacts/2026-10-24/llm_run_20261024_171821")
METHODS = {"rule_based_gated", "llm_direct_isolated", "llm_validated"}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def git_info(root: Path) -> dict:
    def run(args: list[str]) -> str | None:
        try:
            return subprocess.check_output(args, cwd=root, stderr=subprocess.DEVNULL, text=True).strip()
        except (OSError, subprocess.CalledProcessError):
            return None
    return {
        "commit": run(["git", "rev-parse", "HEAD"]),
        "branch": run(["git", "branch", "--show-current"]),
        "status_porcelain": run(["git", "status", "--porcelain"]),
        "origin_url": run(["git", "config", "--get", "remote.origin.url"]),
    }


def pinned_requirements(path: Path) -> dict:
    bad: list[str] = []
    checked: list[str] = []
    if not path.exists():
        return {"exists": False, "checked": [], "unpinned": [str(path)]}
    for i, line in enumerate(path.read_text(errors="replace").splitlines(), 1):
        s = line.strip()
        if not s or s.startswith("#") or s.startswith("-"):
            continue
        if "==" not in s:
            bad.append(f"{path}:{i}:{s}")
        else:
            checked.append(s)
    return {"exists": True, "checked": checked, "unpinned": bad}


def artifact_audit(root: Path) -> dict:
    base = root / RUN_REL
    raw = base / "raw/repeated_trials_20261024_171821.jsonl"
    summary_path = base / "summary/repeated_trials_summary_20261024_171821.json"
    manifest_path = base / "manifest/llm_run_manifest_20261024_171821.json"
    required = [raw, summary_path, manifest_path]
    if not all(p.exists() for p in required):
        return {"status": "missing_artifacts", "missing": [str(p.relative_to(root)) for p in required if not p.exists()]}

    rows, malformed = [], []
    for n, line in enumerate(raw.read_text(errors="replace").splitlines(), 1):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as e:
            malformed.append({"line": n, "error": str(e)})

    summary = json.loads(summary_path.read_text())
    manifest = json.loads(manifest_path.read_text())
    by_method = defaultdict(list)
    for row in rows:
        by_method[row.get("method")].append(row)

    method_checks = {}
    for method in sorted(METHODS):
        rs = by_method.get(method, [])
        recovered = sum(1 for r in rs if r.get("result", {}).get("status") == "recovered")
        review = sum(1 for r in rs if r.get("result", {}).get("status") in {"needs_human_approval", "human_review_required"} or r.get("result", {}).get("human_review_required"))
        summary_method = summary.get("methods", {}).get(method, {})
        method_checks[method] = {
            "rows": len(rs),
            "recovered": recovered,
            "summary_rows": summary_method.get("cases"),
            "summary_recovered": summary_method.get("recovered"),
            "mean_method_duration_seconds_recomputed": mean([float(r["result"]["method_duration_seconds"]) for r in rs if r.get("result", {}).get("method_duration_seconds") is not None]) if any(r.get("result", {}).get("method_duration_seconds") is not None for r in rs) else None,
        }
        method_checks[method]["counts_match"] = (len(rs) == summary_method.get("cases") and recovered == summary_method.get("recovered"))

    # Paired LLM trial checks: same case/repeat keys, candidate IDs, and generation duration.
    lmap = {}
    for method in ("llm_direct_isolated", "llm_validated"):
        lmap[method] = {(r.get("case_id"), r.get("repeat_index")): r for r in by_method.get(method, [])}
    shared_keys = set(lmap["llm_direct_isolated"]) & set(lmap["llm_validated"])
    paired = 0
    pair_mismatch = []
    for key in shared_keys:
        a = lmap["llm_direct_isolated"][key]
        b = lmap["llm_validated"][key]
        if a.get("candidate_id") == b.get("candidate_id") and a.get("llm_generation_seconds") == b.get("llm_generation_seconds"):
            paired += 1
        else:
            pair_mismatch.append({"case_id": key[0], "repeat_index": key[1]})

    diagnosis_keys = {}
    for r in rows:
        key = (r.get("case_id"), r.get("repeat_index"))
        diagnosis_keys.setdefault(key, r.get("diagnosis_correct"))
    result = {
        "status": "ok" if not malformed else "malformed_jsonl",
        "raw_rows": len(rows),
        "malformed_rows": malformed,
        "methods": method_checks,
        "all_method_counts_match_summary": all(v["counts_match"] for v in method_checks.values()),
        "paired_llm_trials": len(shared_keys),
        "paired_llm_candidate_and_generation_matches": paired,
        "paired_llm_mismatches": pair_mismatch,
        "unique_case_repeat_keys_for_diagnosis": len(diagnosis_keys),
        "diagnosis_correct_unique_keys": sum(v is True for v in diagnosis_keys.values()),
        "diagnosis_summary": summary.get("diagnosis_evaluation", {}),
        "manifest": {
            "captured_at_utc": manifest.get("captured_at_utc"),
            "git_commit": manifest.get("git_commit"),
            "model_identifier": manifest.get("model_identifier"),
            "endpoint_sanitized": manifest.get("endpoint_sanitized"),
            "python_version": manifest.get("python_version"),
            "sdk": manifest.get("sdk"),
            "source_sha256": manifest.get("source_sha256"),
        },
        "artifact_sha256": {str(p.relative_to(root)): sha256(p) for p in required},
    }
    result["overall_consistency_pass"] = (
        not malformed and len(rows) == 180 and result["all_method_counts_match_summary"]
        and all(method_checks[m]["rows"] == 60 for m in METHODS)
        and len(shared_keys) == 60 and paired == 60 and not pair_mismatch
    )
    return result


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".", help="Repository root (default: current directory)")
    ap.add_argument("--output", default="research_artifacts/release_preflight_current.json")
    ap.add_argument("--skip-tests", action="store_true", help="Do not run pytest")
    args = ap.parse_args()
    root = Path(args.root).resolve()

    hygiene = []
    forbidden_dirs = {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".venv", "venv"}
    forbidden_files = {".DS_Store"}
    for p in root.rglob("*"):
        if any(part in forbidden_dirs for part in p.parts):
            hygiene.append(str(p.relative_to(root)))
        elif p.is_file() and (p.name in forbidden_files or p.name.startswith("._") or p.suffix in {".pyc", ".pyo"}):
            hygiene.append(str(p.relative_to(root)))
    active_env = (root / ".env").exists()
    # Do not read .env; only report the presence of this file.
    req_core = pinned_requirements(root / "requirements.txt")
    req_llm = pinned_requirements(root / "requirements-llm.txt")
    required_paths = ["README.md", "pytest.ini", "tests", "pipeline/runner.py", "healing/rca/rule_based_rca.py", "requirements.txt", "requirements-llm.txt"]
    missing_paths = [p for p in required_paths if not (root / p).exists()]

    test_result = {"skipped": True}
    if not args.skip_tests:
        # Avoid creating release-noise caches as a side effect of the preflight.
        env = os.environ.copy()
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        p = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"],
            cwd=root, capture_output=True, text=True, env=env,
        )
        test_result = {"skipped": False, "returncode": p.returncode, "stdout": p.stdout[-5000:], "stderr": p.stderr[-2000:]}

    report = {
        "schema": "self-healing-ml-pipeline-release-preflight-v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "root": str(root),
        "python": sys.version,
        "git": git_info(root),
        "checks": {
            "missing_required_paths": missing_paths,
            "release_cache_or_os_metadata_files": sorted(set(hygiene)),
            "active_dot_env_present_do_not_publish": active_env,
            "requirements_core": req_core,
            "requirements_llm": req_llm,
            "archived_run": artifact_audit(root),
            "test_run": test_result,
        },
    }
    out = (root / args.output).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({
        "output": str(out),
        "git_commit": report["git"]["commit"],
        "missing_required_paths": missing_paths,
        "release_cache_or_os_metadata_count": len(set(hygiene)),
        "active_dot_env_present": active_env,
        "core_unpinned_requirements": len(req_core["unpinned"]),
        "llm_unpinned_requirements": len(req_llm["unpinned"]),
        "archived_run_status": report["checks"]["archived_run"].get("status"),
        "archived_run_consistency_pass": report["checks"]["archived_run"].get("overall_consistency_pass"),
        "tests_returncode": test_result.get("returncode"),
    }, indent=2))
    failed = bool(missing_paths or hygiene or active_env or req_core["unpinned"] or req_llm["unpinned"])
    if report["checks"]["archived_run"].get("status") not in {"ok"} or not report["checks"]["archived_run"].get("overall_consistency_pass", False):
        failed = True
    if not args.skip_tests and test_result.get("returncode") != 0:
        failed = True
    return 1 if failed else 0

if __name__ == "__main__":
    raise SystemExit(main())
