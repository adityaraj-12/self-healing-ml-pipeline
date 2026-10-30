"""Opt-in JSONL capture for newly executed LLM repair calls.

Set SHMLP_LLM_IO_LOG_PATH to a private output path before a live experiment.
The log contains prompts and complete provider responses but never the API key.
Enable only for synthetic/research fixtures and protect the resulting file.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


def _canonical_sha256(value: Mapping[str, Any]) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _response_payload(response: Any) -> Any:
    if hasattr(response, "model_dump"):
        try:
            return response.model_dump(mode="json")
        except TypeError:
            return response.model_dump()
    if hasattr(response, "model_dump_json"):
        return json.loads(response.model_dump_json())
    if isinstance(response, Mapping):
        return dict(response)
    return {"repr": repr(response)}


def _redact_error(message: str) -> str:
    """Avoid storing obvious credential-shaped strings from exception text."""
    message = re.sub(r"(?i)\bsk-[A-Za-z0-9_-]{16,}\b", "<redacted-secret>", message)
    message = re.sub(r"(?i)\bBearer\s+\S+", "Bearer <redacted>", message)
    message = re.sub(
        r"(?i)(api[_-]?key|access[_-]?token|password|passwd|secret|authorization)(\s*[=:]\s*)[^\s,;]+",
        r"\1\2<redacted>", message,
    )
    return message[:1500]


def _append_record(record: dict[str, Any]) -> None:
    raw_path = os.getenv("SHMLP_LLM_IO_LOG_PATH", "").strip()
    if not raw_path:
        return

    path = Path(raw_path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    # Restrict file permissions on POSIX platforms where chmod is available.
    try:
        if not path.exists():
            fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
            os.close(fd)
        path.chmod(0o600)
    except OSError:
        # Continue with the OS defaults; caller is informed by ordinary file errors below.
        pass

    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")


def capture_success(request: dict[str, Any], response: Any, attempt: int) -> None:
    """Append the exact request fields and complete response body, when enabled."""
    _append_record({
        "schema": "shmlp-llm-io-v1",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "status": "response_received",
        "attempt": attempt,
        "request_sha256": _canonical_sha256(request),
        "request": request,
        "response": _response_payload(response),
        "security_note": "API key values are not part of the request payload recorded here.",
    })


def capture_failure(request: dict[str, Any], error: BaseException, attempt: int) -> None:
    """Append the request metadata and a credential-scrubbed exception on call failure."""
    _append_record({
        "schema": "shmlp-llm-io-v1",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "status": "request_failed",
        "attempt": attempt,
        "request_sha256": _canonical_sha256(request),
        "request": request,
        "error": {
            "type": type(error).__name__,
            "message_redacted": _redact_error(str(error)),
        },
        "security_note": "API key values are not part of the request payload recorded here.",
    })
