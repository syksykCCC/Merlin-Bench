from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from aipbench.audit import audit_run
from aipbench.core.models import SessionMode
from aipbench.core.runtime import ArthurRuntime
from aipbench.registry import default_registry
from aipbench.tasks.machine_checked_mathematics import (
    PROOF_EVENT_KIND,
    SOLUTION_MEDIA_TYPE,
    TASK_ID,
    find_lean_executable,
    solve_public_instance,
)
from aipbench.transport.inprocess import InProcessParticipantClient


@pytest.mark.skipif(find_lean_executable() is None, reason="pinned Lean toolchain unavailable")
def test_reference_proof_accepts_and_strict_audit_replays(tmp_path: Path) -> None:
    registry = default_registry()
    runtime = ArthurRuntime.create(
        plugin=registry.get(TASK_ID),
        case_id="c03",
        run_dir=tmp_path / "accepted",
        mode=SessionMode.DEV,
        instance_seed=hashlib.sha256(b"t3.1-accepted-instance").digest(),
        coin_seed=hashlib.sha256(b"t3.1-accepted-coin").digest(),
        run_id="test-t3.1-accepted",
        session_token="test-token",
    )
    client = InProcessParticipantClient(runtime)
    source = solve_public_instance(runtime.generated_case.public_instance, "c03").encode()
    artifact = client.upload_artifact(content=source, media_type=SOLUTION_MEDIA_TYPE)
    response = client.submit_event(
        sequence=0,
        kind=PROOF_EVENT_KIND,
        payload={"instance_sha256": runtime.generated_case.public_instance["instance_sha256"]},
        artifact_refs=(artifact["artifact_id"],),
    )
    assert response["status"] == "ACCEPT"
    assert response["reason_code"] == "PROTOCOL_ACCEPT"

    report = audit_run(runtime.run_dir, registry=default_registry())
    assert report["audit_passed"] is True
    assert report["official_result"] == "PASS"
    assert report["signed_terminal_status"] == "ACCEPT"


@pytest.mark.skipif(find_lean_executable() is None, reason="pinned Lean toolchain unavailable")
def test_invalid_proof_rejects_but_transcript_still_audits(tmp_path: Path) -> None:
    registry = default_registry()
    runtime = ArthurRuntime.create(
        plugin=registry.get(TASK_ID),
        case_id="c01",
        run_dir=tmp_path / "rejected",
        mode=SessionMode.DEV,
        instance_seed=hashlib.sha256(b"t3.1-rejected-instance").digest(),
        coin_seed=hashlib.sha256(b"t3.1-rejected-coin").digest(),
        run_id="test-t3.1-rejected",
        session_token="test-token",
    )
    client = InProcessParticipantClient(runtime)
    source = b"""import Challenge

namespace AMBenchSolution
theorem proof : Challenge.Target := by
  exact False.elim (by contradiction)
end AMBenchSolution
"""
    artifact = client.upload_artifact(content=source, media_type=SOLUTION_MEDIA_TYPE)
    response = client.submit_event(
        sequence=0,
        kind=PROOF_EVENT_KIND,
        payload={"instance_sha256": runtime.generated_case.public_instance["instance_sha256"]},
        artifact_refs=(artifact["artifact_id"],),
    )
    assert response["status"] == "REJECT"
    assert response["reason_code"] == "LEAN_ELABORATION_FAILED"

    report = audit_run(runtime.run_dir, registry=default_registry())
    assert report["audit_passed"] is True
    assert report["official_result"] == "FAIL"
    assert report["signed_terminal_status"] == "REJECT"
