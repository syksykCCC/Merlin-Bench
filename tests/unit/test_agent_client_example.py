from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _load_example_client() -> ModuleType:
    path = ROOT / "examples" / "agent_client.py"
    spec = importlib.util.spec_from_file_location("example_agent_client", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_agent_client_uses_connection_file_with_environment_precedence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _load_example_client()
    connection_file = tmp_path / ".aipbench-connection.json"
    connection_file.write_text(
        json.dumps(
            {
                "endpoint": "http://file.example:8765/",
                "session_token": "file-token",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.delenv("AIP_ENDPOINT", raising=False)
    monkeypatch.delenv("AIP_SESSION_TOKEN", raising=False)
    monkeypatch.delenv("AIP_CONNECTION_FILE", raising=False)
    module.__file__ = str(tmp_path / "agent_client.py")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    client = module.AgentClient.from_environment(timeout_seconds=7)
    assert client.endpoint == "http://file.example:8765"
    assert client.session_token == "file-token"
    assert client.timeout_seconds == 7

    monkeypatch.setenv("AIP_ENDPOINT", "http://environment.example:9000/")
    monkeypatch.setenv("AIP_SESSION_TOKEN", "environment-token")
    client = module.AgentClient.from_environment(
        timeout_seconds=3,
        connection_file=connection_file,
    )
    assert client.endpoint == "http://environment.example:9000"
    assert client.session_token == "environment-token"

    monkeypatch.delenv("AIP_SESSION_TOKEN")
    with pytest.raises(module.ClientError, match="must either both be set or both be unset"):
        module.AgentClient.from_environment(timeout_seconds=3)
