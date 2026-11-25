from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from aipbench.audit import audit_run
from aipbench.core.models import SessionMode
from aipbench.core.runtime import ArthurRuntime
from aipbench.registry import TaskRegistry
from aipbench.tasks.image_size_lower_bound import TASK_MANIFEST, VIRTUAL_AGENTS, create_task
from aipbench.transport.inprocess import InProcessParticipantClient

CASE_IDS = ("c01", "c02", "c03", "c04", "c05", "c06")


def _registry() -> TaskRegistry:
    registry = TaskRegistry()
    registry.register(TASK_MANIFEST, create_task)
    return registry


@pytest.mark.parametrize("case_id", CASE_IDS)
def test_all_image_size_cases_accept_and_replay_exactly(tmp_path: Path, case_id: str) -> None:
    plugin = create_task()
    runtime = ArthurRuntime.create(
        plugin=plugin,
        case_id=case_id,
        run_dir=tmp_path / case_id,
        mode=SessionMode.EVAL,
        instance_seed=hashlib.sha256(f"image-instance/{case_id}".encode()).digest(),
        coin_seed=hashlib.sha256(f"image-coins/{case_id}".encode()).digest(),
        run_id=f"test-image-size-{case_id}",
        session_token="test-token",
    )
    workspace = tmp_path / f"workspace-{case_id}"
    workspace.mkdir()
    VIRTUAL_AGENTS["virtual-honest"].run(
        client=InProcessParticipantClient(runtime),
        workspace=workspace,
    )
    assert runtime.terminal_result is not None
    assert runtime.terminal_result["terminal_status"] == "ACCEPT"
    assert runtime.terminal_result["reason_code"] == "PROTOCOL_ACCEPT"
    assert list(workspace.iterdir()) == []

    transcript_path = runtime.run_dir / "official" / "transcript.jsonl"
    records = [
        json.loads(line) for line in transcript_path.read_text(encoding="utf-8").splitlines()
    ]
    assert [(record["direction"], record["kind"], record["sequence"]) for record in records] == [
        ("MERLIN_TO_ARTHUR", "image.begin", 0),
        ("ARTHUR_TO_MERLIN", "runtime.response", 0),
        ("MERLIN_TO_ARTHUR", "image.response", 1),
        ("ARTHUR_TO_MERLIN", "runtime.response", 1),
    ]
    challenge = records[1]["payload"]["reply"]
    assert challenge["kind"] == "image.challenge"
    assert len(challenge["payload"]["hashes"]) == 128
    assert len(records[2]["payload"]["preimages"]) == 128

    report = audit_run(runtime.run_dir, registry=_registry())
    assert report["audit_passed"] is True
    assert report["official_result"] == "PASS"
    assert report["signed_terminal_status"] == "ACCEPT"


def test_empty_image_agent_rejects_and_strict_replay_still_passes(tmp_path: Path) -> None:
    registry = _registry()
    runtime = ArthurRuntime.create(
        plugin=registry.get("t2.image_size_lower_bound"),
        case_id="c01",
        run_dir=tmp_path / "empty-image",
        mode=SessionMode.EVAL,
        instance_seed=hashlib.sha256(b"empty-image-instance").digest(),
        coin_seed=hashlib.sha256(b"empty-image-coins").digest(),
        run_id="test-empty-image",
        session_token="test-token",
    )
    workspace = tmp_path / "empty-image-workspace"
    workspace.mkdir()
    VIRTUAL_AGENTS["virtual-empty-response"].run(
        client=InProcessParticipantClient(runtime), workspace=workspace
    )
    assert runtime.terminal_result is not None
    assert runtime.terminal_result["terminal_status"] == "REJECT"

    report = audit_run(runtime.run_dir, registry=registry)
    assert report["audit_passed"] is True
    assert report["official_result"] == "FAIL"
    assert report["signed_terminal_status"] == "REJECT"
