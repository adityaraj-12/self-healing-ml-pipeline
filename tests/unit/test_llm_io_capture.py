import json
from pathlib import Path

from healing.repair.llm_io_capture import capture_success, capture_failure


class FakeResponse:
    def model_dump(self, mode="python"):
        return {
            "id": "resp-123",
            "model": "test-model",
            "choices": [{"message": {"content": '{"action":"test"}'}}],
        }


def test_capture_success_records_request_hash_and_response_without_key(tmp_path, monkeypatch):
    target = tmp_path / "private" / "io.jsonl"
    monkeypatch.setenv("SHMLP_LLM_IO_LOG_PATH", str(target))
    fake_key = "sk-" + ("A" * 30)
    monkeypatch.setenv("OPENAI_API_KEY", fake_key)
    request = {"model": "test-model", "temperature": 0, "messages": [{"role": "user", "content": "synthetic case"}]}

    capture_success(request, FakeResponse(), 1)

    row = json.loads(target.read_text(encoding="utf-8"))
    assert row["schema"] == "shmlp-llm-io-v1"
    assert row["status"] == "response_received"
    assert len(row["request_sha256"]) == 64
    assert row["response"]["id"] == "resp-123"
    assert "OPENAI_API_KEY" not in json.dumps(row)
    assert fake_key not in json.dumps(row)


def test_capture_failure_redacts_key_like_strings(tmp_path, monkeypatch):
    target = tmp_path / "io.jsonl"
    monkeypatch.setenv("SHMLP_LLM_IO_LOG_PATH", str(target))
    request = {"model": "test-model", "messages": []}

    fake_key = "sk-" + ("B" * 32)
    capture_failure(request, RuntimeError(f"request failed with {fake_key} and Bearer tokensecret"), 2)

    row = json.loads(target.read_text(encoding="utf-8"))
    assert row["status"] == "request_failed"
    assert fake_key not in json.dumps(row)
    assert "Bearer tokensecret" not in json.dumps(row)
    assert "<redacted-secret>" in row["error"]["message_redacted"]
