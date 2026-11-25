from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "scripts" / "run_harness.py"


def _workspace(tmp_path: Path, *, wall_time_seconds: int = 10) -> Path:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    for filename in (
        "AGENT_PROMPT.md",
        "TASK_SPECIFICATION.md",
        "instance.json",
        "protocol.json",
        "agent_client.py",
    ):
        (workspace / filename).write_text(
            "test prompt\n" if filename == "AGENT_PROMPT.md" else "{}\n",
            encoding="utf-8",
        )
    (workspace / ".aipbench-connection.json").write_text(
        json.dumps(
            {
                "api_version": "aip/1",
                "endpoint": "http://127.0.0.1:18765",
                "session_token": "test-session-token",
            }
        ),
        encoding="utf-8",
    )
    (workspace / "harness.json").write_text(
        json.dumps(
            {
                "schema_version": "aip-harness/1",
                "api_version": "aip/1",
                "task": {"id": "t1.example", "version": "1.2.3", "title": "Example"},
                "case": {"id": "c04"},
                "limits": {"wall_time_seconds": wall_time_seconds},
                "files": {
                    "prompt": "AGENT_PROMPT.md",
                    "task_specification": "TASK_SPECIFICATION.md",
                    "instance": "instance.json",
                    "protocol": "protocol.json",
                    "client": "agent_client.py",
                    "connection": ".aipbench-connection.json",
                },
            }
        ),
        encoding="utf-8",
    )
    return workspace


def test_runner_injects_contract_and_only_selected_environment(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    child = tmp_path / "child.py"
    child.write_text(
        """import json
import os
import sys

print(json.dumps({
    "stdin": sys.stdin.read(),
    "cwd": os.getcwd(),
    "task": os.environ["AIP_TASK_ID"],
    "version": os.environ["AIP_TASK_VERSION"],
    "case": os.environ["AIP_CASE_ID"],
    "endpoint": os.environ["AIP_ENDPOINT"],
    "token": os.environ["AIP_SESSION_TOKEN"],
    "provider": os.environ["TEST_PROVIDER_KEY"],
    "unrelated_present": "UNRELATED_SECRET" in os.environ,
}))
""",
        encoding="utf-8",
    )
    environment = dict(os.environ)
    environment["TEST_PROVIDER_KEY"] = "dummy-provider-value"
    environment["UNRELATED_SECRET"] = "must-not-be-copied"
    completed = subprocess.run(
        [
            sys.executable,
            str(RUNNER),
            "--workspace",
            str(workspace),
            "--prompt-mode",
            "stdin",
            "--inherit-env",
            "TEST_PROVIDER_KEY",
            "--",
            sys.executable,
            str(child),
        ],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)
    assert result == {
        "stdin": "test prompt\n",
        "cwd": str(workspace),
        "task": "t1.example",
        "version": "1.2.3",
        "case": "c04",
        "endpoint": "http://127.0.0.1:18765",
        "token": "test-session-token",
        "provider": "dummy-provider-value",
        "unrelated_present": False,
    }


def test_runner_supports_prompt_path_and_propagates_exit_code(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    child = tmp_path / "child.py"
    child.write_text(
        """import pathlib
import sys

assert pathlib.Path(sys.argv[-1]).read_text(encoding="utf-8") == "test prompt\\n"
raise SystemExit(7)
""",
        encoding="utf-8",
    )
    completed = subprocess.run(
        [
            sys.executable,
            str(RUNNER),
            "--workspace",
            str(workspace),
            "--prompt-mode",
            "path-argument",
            "--",
            sys.executable,
            str(child),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert completed.returncode == 7


def test_runner_supports_prompt_text_argument(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    child = tmp_path / "child.py"
    child.write_text(
        """import sys

assert sys.argv[-1] == "test prompt\\n"
""",
        encoding="utf-8",
    )
    completed = subprocess.run(
        [
            sys.executable,
            str(RUNNER),
            "--workspace",
            str(workspace),
            "--prompt-mode",
            "argument",
            "--",
            sys.executable,
            str(child),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert completed.returncode == 0, completed.stderr


def test_runner_times_out_without_exposing_environment_values(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    child = tmp_path / "child.py"
    child.write_text("import time\ntime.sleep(5)\n", encoding="utf-8")
    completed = subprocess.run(
        [
            sys.executable,
            str(RUNNER),
            "--workspace",
            str(workspace),
            "--timeout",
            "0.05",
            "--",
            sys.executable,
            str(child),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert completed.returncode == 124
    assert "exceeded its configured timeout" in completed.stderr


def test_runner_rejects_workspace_file_escape(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    manifest_path = workspace / "harness.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["files"]["prompt"] = "../outside.md"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    completed = subprocess.run(
        [
            sys.executable,
            str(RUNNER),
            "--workspace",
            str(workspace),
            "--",
            sys.executable,
            "-c",
            "raise SystemExit(0)",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert completed.returncode == 2
    assert "must be relative" in completed.stderr


def test_runner_rejects_unsupported_api_version(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    manifest_path = workspace / "harness.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["api_version"] = "future/2"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    completed = subprocess.run(
        [
            sys.executable,
            str(RUNNER),
            "--workspace",
            str(workspace),
            "--",
            sys.executable,
            "-c",
            "raise SystemExit(0)",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert completed.returncode == 2
    assert "unsupported Participant API version" in completed.stderr
