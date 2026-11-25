from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from aipbench.audit import audit_run
from aipbench.core.errors import SessionTerminalError
from aipbench.core.event_log import load_and_validate_event_log
from aipbench.core.models import ParticipantEvent, SessionMode
from aipbench.core.runtime import ArthurRuntime
from aipbench.registry import default_registry
from aipbench.tasks.shared.maxflow import solve_maxflow


def test_concurrent_duplicate_sequence_cannot_corrupt_one_shot_session(tmp_path: Path) -> None:
    runtime = ArthurRuntime.create(
        plugin=default_registry().get("t1.new_maxflow_min_cut"),
        case_id="c01",
        run_dir=tmp_path / "concurrent",
        mode=SessionMode.EVAL,
        instance_seed=b"i" * 32,
        coin_seed=b"c" * 32,
        session_token="token",
    )
    event = ParticipantEvent(
        sequence=0,
        kind="maxflow.certificate",
        payload=solve_maxflow(runtime.get_instance()),
    )
    barrier = threading.Barrier(2)

    def submit() -> str:
        barrier.wait()
        try:
            return runtime.submit_event(event)["status"]
        except SessionTerminalError:
            return "SESSION_TERMINAL"

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(lambda _index: submit(), range(2)))

    assert sorted(outcomes) == ["ACCEPT", "SESSION_TERMINAL"]
    records = load_and_validate_event_log(runtime.run_dir / "official" / "transcript.jsonl")
    assert len(records) == 2
    assert audit_run(runtime.run_dir)["official_result"] == "PASS"
