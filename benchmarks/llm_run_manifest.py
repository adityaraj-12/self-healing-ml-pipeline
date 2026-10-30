"""Capture non-secret LLM configuration metadata for reproducible experiments.

This module records the current environment and source configuration only. It
cannot reconstruct settings used by historical runs unless their environment and
source snapshot are available.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping, Any
from urllib.parse import urlsplit, urlunsplit

ROOT = Path(__file__).resolve().parents[1]
# Hash the core files that can change repair behavior, benchmarking, or scenario
# interpretation. A manifest with these hashes is still a partial source snapshot;
# it is not a substitute for a clean Git commit/release archive.
SOURCE_FILES = (
    "healing/repair/llm_repair_generator.py",
    "healing/rca/llm_rca.py",
    "healing/repair/repair_policy.py",
    "healing/validation/repair_validator.py",
    "benchmarks/repeated_trials.py",
    "benchmarks/experiment_runtime.py",
    "benchmarks/direct_llm_baseline.py",
    "benchmarks/scenarios/trial_cases.yaml",
    "pipeline/runner.py",
)


def _sha256(path: Path) -> str | None:
    try:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(65536), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return None


def _safe_endpoint(raw: str | None) -> str | None:
    """Return an endpoint without credentials, query, or fragment values."""
    if not raw:
        return None
    try:
        parts = urlsplit(raw)
        if not parts.scheme or not parts.hostname:
            return "configured-but-unparseable"
        host = parts.hostname
        try:
            port = parts.port
        except ValueError:
            port = None
        if port is not None:
            host = f"{host}:{port}"
        # Keep a normal API path such as /v1, but redact paths containing
        # credential-like segments that might embed keys or secrets.
        path = re.sub(r"/{2,}", "/", parts.path or "")
        if re.search(r"(?i)(token|secret|api[-_]?key|auth|credential|password|passwd|signature)", path):
            path = "/<redacted-path>" if path else ""
        return urlunsplit((parts.scheme, host, path.rstrip("/"), "", ""))
    except Exception:
        return "configured-but-unparseable"


def _git_metadata(root: Path) -> dict[str, Any]:
    """Collect Git provenance when present without failing outside a repo."""
    metadata: dict[str, Any] = {
        "git_commit": None,
        "git_branch": None,
        "git_worktree_clean": None,
    }
    commands = {
        "git_commit": ["git", "rev-parse", "HEAD"],
        "git_branch": ["git", "branch", "--show-current"],
    }
    try:
        for key, command in commands.items():
            result = subprocess.run(
                command, cwd=root, capture_output=True, text=True,
                timeout=2, check=True,
            )
            value = result.stdout.strip()
            metadata[key] = value or None
        status = subprocess.run(
            ["git", "status", "--porcelain"], cwd=root,
            capture_output=True, text=True, timeout=2, check=True,
        )
        metadata["git_worktree_clean"] = not bool(status.stdout.strip())
    except (OSError, subprocess.SubprocessError):
        # A missing/invalid Git repository is recorded as missing provenance;
        # do not invent a commit or fail manifest generation.
        pass
    return metadata


def _critical_source_set_hash(source_hashes: Mapping[str, str | None]) -> str:
    payload = "".join(
        f"{name}\0{digest or 'MISSING'}\n"
        for name, digest in sorted(source_hashes.items())
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _declared_openai_requirement(root: Path) -> str | None:
    path = root / "requirements-llm.txt"
    if not path.exists():
        return None
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.lower().startswith("openai=="):
            return stripped
    return None


def collect_manifest(root: Path | str | None = None,
                     environ: Mapping[str, str] | None = None) -> dict[str, Any]:
    """Collect sanitized LLM settings without performing an API request."""
    project_root = Path(root).resolve() if root else ROOT
    env = os.environ if environ is None else environ

    try:
        installed_openai_version = importlib.metadata.version("openai")
    except importlib.metadata.PackageNotFoundError:
        installed_openai_version = None

    source_hashes = {
        rel: _sha256(project_root / rel) for rel in SOURCE_FILES
    }
    git_metadata = _git_metadata(project_root)
    model = (env.get("OPENAI_MODEL") or "").strip() or None
    api_key_present = bool((env.get("OPENAI_API_KEY") or "").strip())
    endpoint = _safe_endpoint(env.get("OPENAI_BASE_URL"))

    missing = []
    if not model:
        missing.append("OPENAI_MODEL")
    if not api_key_present:
        missing.append("OPENAI_API_KEY")
    if installed_openai_version is None:
        missing.append("installed openai SDK")
    declared_requirement = _declared_openai_requirement(project_root)
    if declared_requirement and installed_openai_version:
        declared_version = declared_requirement.split("==", 1)[1].strip()
        if installed_openai_version != declared_version:
            missing.append(
                f"installed openai SDK matches declared pin ({declared_version})"
            )
    if any(value is None for value in source_hashes.values()):
        missing.append("required benchmark/source files available for hashing")

    return {
        "manifest_schema": "llm-run-manifest-v1",
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "current environment/source configuration; not a reconstruction of historical runs",
        "status": "ready_to_attempt_live_run" if not missing else "incomplete_configuration",
        "missing_items": missing,
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        **git_metadata,
        "critical_source_set_sha256": _critical_source_set_hash(source_hashes),
        "provider_mode": "openai_compatible_custom_endpoint" if endpoint else "openai_default_endpoint",
        "model_identifier": model,
        "api_key_present": api_key_present,
        "llm_io_capture_enabled": bool((env.get("SHMLP_LLM_IO_LOG_PATH") or "").strip()),
        "endpoint_sanitized": endpoint,
        "sdk": {
            "declared_requirement": declared_requirement,
            "installed_version": installed_openai_version,
            "matches_declared_pin": (
                bool(declared_requirement and installed_openai_version)
                and installed_openai_version == declared_requirement.split("==", 1)[1].strip()
            ),
        },
        "request_settings_from_source": {
            "repair_generation": {
                "api_method": "chat.completions.create",
                "temperature": 0,
                "response_format": {"type": "json_object"},
                "candidate_validation_attempts": 2,
                "top_p": "not explicitly set; provider default",
                "token_limit": "not explicitly set; provider default",
            },
            "llm_rca": {
                "api_method": "chat.completions.create",
                "temperature": 0,
                "response_format": {"type": "json_object"},
                "request_attempts": 1,
                "top_p": "not explicitly set; provider default",
                "token_limit": "not explicitly set; provider default",
            },
        },
        "source_sha256": source_hashes,
        "security": {
            "api_key_value_recorded": False,
            "base_url_user_info_query_fragment_recorded": False,
            "credential_like_path_segments_redacted": True,
        },
        "historical_run_note": (
            "Use this manifest alongside a newly executed run. It cannot identify the model or settings "
            "used in old results when the original environment and request logs were not preserved."
        ),
    }


def write_manifest(path: Path | str, root: Path | str | None = None,
                   environ: Mapping[str, str] | None = None) -> dict[str, Any]:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    manifest = collect_manifest(root=root, environ=environ)
    output.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path,
        default=ROOT / "research_artifacts" / "llm_run_manifest_current.json",
        help="Path for the sanitized JSON manifest (default: research_artifacts/llm_run_manifest_current.json)",
    )
    args = parser.parse_args()

    # Read local .env if python-dotenv is installed; values are not serialized except
    # the model ID and a sanitized endpoint. The API key is only recorded as present/absent.
    try:
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env")
    except ImportError:
        pass

    manifest = write_manifest(args.output, root=ROOT)
    print(json.dumps(manifest, indent=2))
    print(f"\nManifest written to: {args.output}")
    return 0 if manifest["status"] == "ready_to_attempt_live_run" else 2


if __name__ == "__main__":
    raise SystemExit(main())
