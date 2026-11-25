from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from aipbench.audit import audit_run
from aipbench.core.errors import AIPBenchError, SessionTerminalError
from aipbench.core.models import SessionMode
from aipbench.core.runtime import ArthurRuntime
from aipbench.registry import default_registry
from aipbench.tasks.shared.graph_non_isomorphism import VIRTUAL_AGENTS as GNI_AGENTS
from aipbench.tasks.shared.maxflow import VIRTUAL_AGENTS as MAXFLOW_AGENTS
from aipbench.tasks.shared.maxflow import solve_maxflow
from aipbench.transport.inprocess import InProcessParticipantClient


def _run(
    tmp_path: Path, *, task_id: str, case_id: str, agent_id: str, agents: dict
) -> tuple[ArthurRuntime, dict]:
    plugin = default_registry().get(task_id)
    runtime = ArthurRuntime.create(
        plugin=plugin,
        case_id=case_id,
        run_dir=tmp_path / agent_id,
        mode=SessionMode.DEV,
        instance_seed=hashlib.sha256(f"instance/{task_id}".encode()).digest(),
        coin_seed=hashlib.sha256(f"coin/{task_id}".encode()).digest(),
        run_id=f"test-{task_id}-{agent_id}",
        session_token="test-token",
    )
    workspace = runtime.run_dir / "workspace"
    workspace.mkdir()
    agents[agent_id].run(
        client=InProcessParticipantClient(runtime),
        workspace=workspace,
    )
    assert runtime.terminal_result is not None
    return runtime, audit_run(runtime.run_dir, registry=default_registry())


@pytest.mark.parametrize(
    ("agent_id", "expected_status", "expected_reason"),
    [
        ("virtual-honest", "ACCEPT", "PROTOCOL_ACCEPT"),
        ("virtual-wrong-flow", "REJECT", "MAXFLOW_CAPACITY_VIOLATION"),
        ("virtual-wrong-cut", "REJECT", "MAXFLOW_CUT_INVALID"),
    ],
)
def test_maxflow_runtime_and_independent_audit(
    tmp_path: Path, agent_id: str, expected_status: str, expected_reason: str
) -> None:
    runtime, report = _run(
        tmp_path,
        task_id="t1.new_maxflow_min_cut",
        case_id="c01",
        agent_id=agent_id,
        agents=dict(MAXFLOW_AGENTS),
    )
    assert runtime.terminal_result["terminal_status"] == expected_status
    assert runtime.terminal_result["reason_code"] == expected_reason
    assert report["audit_passed"] is True
    assert report["official_result"] == ("PASS" if expected_status == "ACCEPT" else "FAIL")


@pytest.mark.parametrize(
    ("agent_id", "expected_status", "expected_reason"),
    [
        ("virtual-honest", "ACCEPT", "PROTOCOL_ACCEPT"),
        ("virtual-wrong-source-bit", "REJECT", "GNI_SOURCE_BITS_INCORRECT"),
    ],
)
def test_graph_non_isomorphism_runtime_and_independent_audit(
    tmp_path: Path, agent_id: str, expected_status: str, expected_reason: str
) -> None:
    runtime, report = _run(
        tmp_path,
        task_id="t2.new_graph_non_isomorphism",
        case_id="c01",
        agent_id=agent_id,
        agents=dict(GNI_AGENTS),
    )
    assert runtime.terminal_result["terminal_status"] == expected_status
    assert runtime.terminal_result["reason_code"] == expected_reason
    assert report["audit_passed"] is True
    assert report["official_result"] == ("PASS" if expected_status == "ACCEPT" else "FAIL")


def test_eval_session_is_one_shot_and_post_terminal_messages_do_not_mutate_result(
    tmp_path: Path,
) -> None:
    runtime, _report = _run(
        tmp_path,
        task_id="t1.new_maxflow_min_cut",
        case_id="c01",
        agent_id="virtual-honest",
        agents=dict(MAXFLOW_AGENTS),
    )
    result_before = (runtime.run_dir / "official" / "result.json").read_bytes()
    client = InProcessParticipantClient(runtime)
    with pytest.raises(SessionTerminalError):
        client.submit_event(sequence=1, kind="maxflow.certificate", payload={})
    assert (runtime.run_dir / "official" / "result.json").read_bytes() == result_before
    assert not hasattr(runtime, "reset")


def test_public_api_never_contains_private_instance_fields(tmp_path: Path) -> None:
    plugin = default_registry().get("t2.new_graph_non_isomorphism")
    runtime = ArthurRuntime.create(
        plugin=plugin,
        case_id="c01",
        run_dir=tmp_path / "privacy",
        mode=SessionMode.EVAL,
        instance_seed=b"i" * 32,
        coin_seed=b"c" * 32,
        session_token="token",
    )
    public_text = (
        str(runtime.get_instance()) + str(runtime.get_session()) + str(runtime.get_protocol())
    )
    for forbidden in (
        "source_bits",
        "coin_seed",
        "private_seed",
        "hidden_source",
        "expected_value",
    ):
        assert forbidden not in public_text
    instance_copy = runtime.get_instance()
    original_endpoint = runtime.get_instance()["graphs"][0]["edges"][0][0]
    instance_copy["graphs"][0]["edges"][0][0] = original_endpoint + 1
    assert runtime.get_instance()["graphs"][0]["edges"][0][0] == original_endpoint
    protocol_copy = runtime.get_protocol()
    original_schema = runtime.get_protocol()["event_schemas"]["gni.begin"]["schema_ref"]
    protocol_copy["event_schemas"]["gni.begin"]["schema_ref"] = "tampered"
    assert runtime.get_protocol()["event_schemas"]["gni.begin"]["schema_ref"] == original_schema


def test_runtime_creates_only_host_owned_run_directories(tmp_path: Path) -> None:
    runtime = ArthurRuntime.create(
        plugin=default_registry().get("t1.new_maxflow_min_cut"),
        case_id="c01",
        run_dir=tmp_path / "clean-layout",
        mode=SessionMode.EVAL,
        instance_seed=b"i" * 32,
        coin_seed=b"c" * 32,
        session_token="token",
    )

    assert {path.name for path in runtime.run_dir.iterdir()} == {
        "official",
        "private",
        "public",
    }
    assert not (runtime.run_dir / "agent").exists()
    assert not (runtime.run_dir / "workspace").exists()
    assert not (runtime.run_dir / "public" / "prompt.md").exists()


def test_wall_time_budget_produces_signed_auditable_timeout(tmp_path: Path) -> None:
    runtime = ArthurRuntime.create(
        plugin=default_registry().get("t1.new_maxflow_min_cut"),
        case_id="c01",
        run_dir=tmp_path / "timeout",
        mode=SessionMode.EVAL,
        instance_seed=b"i" * 32,
        coin_seed=b"c" * 32,
        session_token="token",
    )
    calls = 0

    def cross_deadline_during_verification() -> bool:
        nonlocal calls
        calls += 1
        if calls == 2:
            runtime.started_ns -= (runtime.wall_time_seconds + 1) * 1_000_000_000
        return calls >= 2

    runtime._wall_time_exceeded = cross_deadline_during_verification  # type: ignore[method-assign]
    response = InProcessParticipantClient(runtime).submit_event(
        sequence=0,
        kind="maxflow.certificate",
        payload=solve_maxflow(runtime.get_instance()),
    )
    assert response["status"] == "TIMEOUT"
    assert runtime.terminal_result is not None
    assert runtime.terminal_result["reason_code"] == "BUDGET_EXCEEDED"
    assert calls == 2
    report = audit_run(runtime.run_dir)
    assert report["audit_passed"] is True
    assert report["official_result"] == "FAIL"


def test_expired_session_rejects_artifact_upload_until_signed_timeout(tmp_path: Path) -> None:
    runtime = ArthurRuntime.create(
        plugin=default_registry().get("t1.new_maxflow_min_cut"),
        case_id="c01",
        run_dir=tmp_path / "expired-upload",
        mode=SessionMode.EVAL,
        instance_seed=b"i" * 32,
        coin_seed=b"c" * 32,
        session_token="token",
    )
    runtime.started_ns -= (runtime.wall_time_seconds + 1) * 1_000_000_000
    with pytest.raises(AIPBenchError) as caught:
        runtime.upload_artifact(content=b"late", media_type="application/octet-stream")
    assert getattr(caught.value, "code", None) == "BUDGET_EXCEEDED"
