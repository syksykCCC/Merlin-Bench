from __future__ import annotations

import hashlib
import json
from pathlib import Path

from fastapi.testclient import TestClient

from aipbench.audit import audit_run
from aipbench.core.models import SessionMode
from aipbench.core.runtime import ArthurRuntime
from aipbench.registry import default_registry
from aipbench.tasks.shared.maxflow import solve_maxflow
from aipbench.transport.http import create_app
from aipbench.transport.http.observer import CASE_TITLES, MAX_INTERACTIONS, ArthurObserver

PARTICIPANT_TOKEN = "participant-contract-secret"
OBSERVER_TOKEN = "observer-contract-secret"
PARTICIPANT_HEADERS = {"Authorization": f"Bearer {PARTICIPANT_TOKEN}"}
OBSERVER_HEADERS = {"X-AIP-Observer-Token": OBSERVER_TOKEN}


def _runtime(tmp_path: Path, task_id: str, case_id: str = "c01") -> ArthurRuntime:
    return ArthurRuntime.create(
        plugin=default_registry().get(task_id),
        case_id=case_id,
        run_dir=tmp_path / task_id.replace(".", "-"),
        mode=SessionMode.EVAL,
        instance_seed=hashlib.sha256(f"observer/{task_id}".encode()).digest(),
        coin_seed=hashlib.sha256(f"observer-coins/{task_id}".encode()).digest(),
        session_token=PARTICIPANT_TOKEN,
    )


def test_observer_auth_is_separate_from_participant_auth(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path, "t1.new_maxflow_min_cut")
    with TestClient(create_app(runtime)) as disabled:
        assert disabled.get("/observer/api/summary").status_code == 404
    with TestClient(create_app(runtime, observer_token=OBSERVER_TOKEN)) as client:
        assert client.get("/observer/api/summary").status_code == 401
        assert client.get("/observer/api/summary", headers=OBSERVER_HEADERS).status_code == 200
        assert client.get("/v1/session", headers=OBSERVER_HEADERS).status_code == 401
        assert client.get("/v1/session", headers=PARTICIPANT_HEADERS).status_code == 200


def test_current_maxflow_summary_is_bounded_and_tracks_audit(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path, "t1.new_maxflow_min_cut")
    certificate = dict(solve_maxflow(runtime.get_instance()))
    with TestClient(create_app(runtime, observer_token=OBSERVER_TOKEN)) as client:
        response = client.post(
            "/v1/events",
            headers=PARTICIPANT_HEADERS,
            json={
                "api_version": "aip/1",
                "artifact_refs": [],
                "kind": "maxflow.certificate",
                "payload": certificate,
                "sequence": 0,
                "session_id": runtime.session_id,
            },
        )
        assert response.status_code == 200
        assert response.json()["status"] == "ACCEPT"
        assert audit_run(runtime.run_dir)["official_result"] == "PASS"
        raw = client.get("/observer/api/summary", headers=OBSERVER_HEADERS)
        summary = raw.json()
    assert summary["task"]["id"] == "t1.new_maxflow_min_cut"
    assert summary["task"]["case_title"] == "C01"
    assert summary["result"]["state"] == "PASS"
    assert summary["conversation"]["total"] == 1
    assert summary["conversation"]["limit"] == MAX_INTERACTIONS
    assert len(raw.content) < 64 * 1024
    assert b'"edge_flows"' not in raw.content


def test_every_current_case_has_an_observer_title_and_bounded_summary(tmp_path: Path) -> None:
    registry = default_registry()
    for task_id in registry.ids():
        plugin = registry.get(task_id)
        for case_id in plugin.case_parameters:
            assert (task_id, case_id) in CASE_TITLES
        runtime = _runtime(tmp_path, task_id)
        summary = ArthurObserver(runtime).summary()
        assert summary["task"]["id"] == task_id
        assert 1 <= len(summary["instance"]["features"]) <= 2
        assert len(json.dumps(summary, ensure_ascii=False).encode()) < 64 * 1024
