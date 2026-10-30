import json
from pathlib import Path

from benchmarks.llm_run_manifest import collect_manifest, write_manifest


def test_manifest_reports_settings_and_does_not_expose_secrets(tmp_path):
    root = tmp_path
    (root / "healing/repair").mkdir(parents=True)
    (root / "healing/rca").mkdir(parents=True)
    (root / "healing/repair/llm_repair_generator.py").write_text("temperature=0")
    (root / "healing/rca/llm_rca.py").write_text("temperature=0")
    (root / "requirements-llm.txt").write_text("openai==3.20.0\n")
    secret = "api-key-value-must-not-leak"
    env = {
        "OPENAI_API_KEY": secret,
        "OPENAI_MODEL": "test-model-v1",
        "OPENAI_BASE_URL": "https://user:pass@example.test/v1?token=secret#frag",
    }
    manifest = collect_manifest(root=root, environ=env)
    encoded = json.dumps(manifest)
    assert secret not in encoded
    assert "user" not in manifest["endpoint_sanitized"]
    assert "pass" not in manifest["endpoint_sanitized"]
    assert "token" not in manifest["endpoint_sanitized"]
    assert "frag" not in manifest["endpoint_sanitized"]
    assert manifest["model_identifier"] == "test-model-v1"
    assert manifest["api_key_present"] is True
    assert manifest["llm_io_capture_enabled"] is False
    assert manifest["request_settings_from_source"]["repair_generation"]["temperature"] == 0
    assert manifest["request_settings_from_source"]["llm_rca"]["request_attempts"] == 1
    assert "critical_source_set_sha256" in manifest
    assert "source_tree_sha256" not in manifest


def test_manifest_explicitly_marks_missing_model_configuration(tmp_path):
    root = tmp_path
    (root / "healing/repair").mkdir(parents=True)
    (root / "healing/rca").mkdir(parents=True)
    (root / "healing/repair/llm_repair_generator.py").write_text("repair")
    (root / "healing/rca/llm_rca.py").write_text("rca")
    (root / "requirements-llm.txt").write_text("openai==3.20.0\n")
    manifest = collect_manifest(root=root, environ={})
    assert manifest["status"] == "incomplete_configuration"
    assert "OPENAI_MODEL" in manifest["missing_items"]
    assert "OPENAI_API_KEY" in manifest["missing_items"]
    assert manifest["api_key_present"] is False


def test_write_manifest_creates_json_file(tmp_path):
    root = tmp_path / "project"
    (root / "healing/repair").mkdir(parents=True)
    (root / "healing/rca").mkdir(parents=True)
    (root / "healing/repair/llm_repair_generator.py").write_text("repair")
    (root / "healing/rca/llm_rca.py").write_text("rca")
    (root / "requirements-llm.txt").write_text("openai==3.20.0\n")
    output = tmp_path / "out" / "manifest.json"
    write_manifest(output, root=root, environ={})
    decoded = json.loads(output.read_text())
    assert decoded["manifest_schema"] == "llm-run-manifest-v1"


def test_manifest_flags_sdk_pin_mismatch(monkeypatch, tmp_path):
    import benchmarks.llm_run_manifest as module
    root = tmp_path
    (root / "healing/repair").mkdir(parents=True)
    (root / "healing/rca").mkdir(parents=True)
    (root / "healing/repair/llm_repair_generator.py").write_text("repair")
    (root / "healing/rca/llm_rca.py").write_text("rca")
    (root / "requirements-llm.txt").write_text("openai==3.20.0\n")
    monkeypatch.setattr(module.importlib.metadata, "version", lambda name: "3.19.0")
    env = {"OPENAI_MODEL": "test-model", "OPENAI_API_KEY": "dummy"}
    manifest = module.collect_manifest(root=root, environ=env)
    assert manifest["sdk"]["matches_declared_pin"] is False
    assert any("matches declared pin" in item for item in manifest["missing_items"])


def test_manifest_redacts_credential_like_endpoint_path(tmp_path):
    root = tmp_path
    (root / "healing/repair").mkdir(parents=True)
    (root / "healing/rca").mkdir(parents=True)
    (root / "healing/repair/llm_repair_generator.py").write_text("repair")
    (root / "healing/rca/llm_rca.py").write_text("rca")
    (root / "requirements-llm.txt").write_text("openai==3.20.0\n")
    manifest = collect_manifest(
        root=root,
        environ={
            "OPENAI_MODEL": "test-model",
            "OPENAI_API_KEY": "dummy",
            "OPENAI_BASE_URL": "https://host.example/api/secret-token-endpoint",
            "SHMLP_LLM_IO_LOG_PATH": "research_artifacts/private_llm_io.jsonl",
        },
    )
    assert manifest["llm_io_capture_enabled"] is True
    assert manifest["endpoint_sanitized"] == "https://host.example/<redacted-path>"
    assert "secret-token" not in json.dumps(manifest)
