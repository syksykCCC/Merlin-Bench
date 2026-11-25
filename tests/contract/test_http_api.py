from __future__ import annotations

import hashlib
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from aipbench.core.errors import AIPBenchError
from aipbench.core.models import ParticipantEvent, SessionMode
from aipbench.core.runtime import ArthurRuntime
from aipbench.registry import default_registry
from aipbench.tasks.shared.graph_non_isomorphism import VIRTUAL_AGENTS
from aipbench.tasks.shared.graph_non_isomorphism_cases.common import parse_public_graph
from aipbench.tasks.shared.maxflow import solve_maxflow
from aipbench.transport.http import create_app


class _TestClientAdapter:
    def __init__(self, client: TestClient, token: str) -> None:
        self.client = client
        self.headers = {"Authorization": f"Bearer {token}"}
        self.session_id = self.get_session()["session_id"]

    def _get(self, path: str) -> Mapping[str, Any]:
        response = self.client.get(path, headers=self.headers)
        response.raise_for_status()
        return response.json()

    def get_session(self) -> Mapping[str, Any]:
        return self._get("/v1/session")

    def get_protocol(self) -> Mapping[str, Any]:
        return self._get("/v1/protocol")

    def get_instance(self) -> Mapping[str, Any]:
        return self._get("/v1/instance")

    def upload_artifact(self, *, content: bytes, media_type: str) -> Mapping[str, Any]:
        response = self.client.post(
            "/v1/artifacts", content=content, headers={**self.headers, "Content-Type": media_type}
        )
        response.raise_for_status()
        return response.json()

    def submit_event(
        self,
        *,
        sequence: int,
        kind: str,
        payload: Mapping[str, Any],
        artifact_refs: tuple[str, ...] = (),
    ) -> Mapping[str, Any]:
        response = self.client.post(
            "/v1/events",
            headers=self.headers,
            json={
                "api_version": "aip/1",
                "artifact_refs": list(artifact_refs),
                "kind": kind,
                "payload": dict(payload),
                "sequence": sequence,
                "session_id": self.session_id,
            },
        )
        response.raise_for_status()
        return response.json()


def _runtime(tmp_path: Path) -> ArthurRuntime:
    return ArthurRuntime.create(
        plugin=default_registry().get("t2.new_graph_non_isomorphism"),
        case_id="c01",
        run_dir=tmp_path / "http",
        mode=SessionMode.EVAL,
        instance_seed=hashlib.sha256(b"http-instance").digest(),
        coin_seed=hashlib.sha256(b"http-coin").digest(),
        run_id="http-contract-run",
        session_token="secret-token",
    )


def test_http_auth_surface_and_honest_protocol(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    with TestClient(create_app(runtime)) as raw_client:
        assert raw_client.get("/v1/session").status_code == 401
        headers = {"Authorization": "Bearer wrong"}
        assert raw_client.get("/v1/session", headers=headers).status_code == 401
        valid_headers = {"Authorization": "Bearer secret-token"}
        assert raw_client.get("/v1/private-instance", headers=valid_headers).status_code == 404
        assert raw_client.post("/reset", headers=valid_headers).status_code == 404
        assert raw_client.get("/docs").status_code == 404
        assert raw_client.get("/openapi.json").status_code == 404
        adapter = _TestClientAdapter(raw_client, "secret-token")
        metadata = adapter.upload_artifact(content=b"proof", media_type="application/octet-stream")
        assert metadata["artifact_id"].startswith("sha256:")
        VIRTUAL_AGENTS["virtual-honest"].run(
            client=adapter, workspace=runtime.run_dir / "workspace"
        )
    assert runtime.terminal_result is not None
    assert runtime.terminal_result["terminal_status"] == "ACCEPT"


def test_http_rejects_session_mismatch(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    with TestClient(create_app(runtime)) as client:
        response = client.post(
            "/v1/events",
            headers={"Authorization": "Bearer secret-token"},
            json={
                "api_version": "aip/1",
                "artifact_refs": [],
                "kind": "gni.begin",
                "payload": {},
                "sequence": 0,
                "session_id": "different-session",
            },
        )
    assert response.status_code == 409
    assert response.json()["reason_code"] == "SESSION_MISMATCH"


def test_http_gni_challenge_has_exact_shape_without_private_source_bits(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    with TestClient(create_app(runtime)) as raw_client:
        adapter = _TestClientAdapter(raw_client, "secret-token")
        response = adapter.submit_event(sequence=0, kind="gni.begin", payload={})

    assert response["status"] == "CONTINUE"
    assert response["reply"]["kind"] == "gni.challenge"
    assert set(response["reply"]["payload"]) == {"graphs"}
    graphs = response["reply"]["payload"]["graphs"]
    assert len(graphs) == 24
    for graph in graphs:
        parsed = parse_public_graph(graph)
        assert list(parsed.edges) == sorted(set(parsed.edges))
    assert "source_bits" not in str(response)


def test_http_and_inprocess_share_strict_envelope_validation(tmp_path: Path) -> None:
    direct_runtime = ArthurRuntime.create(
        plugin=default_registry().get("t2.new_graph_non_isomorphism"),
        case_id="c01",
        run_dir=tmp_path / "direct-invalid",
        mode=SessionMode.EVAL,
        instance_seed=b"i" * 32,
        coin_seed=b"c" * 32,
        session_token="secret-token",
    )
    from aipbench.transport.inprocess import InProcessParticipantClient

    with pytest.raises(AIPBenchError) as caught:
        InProcessParticipantClient(direct_runtime).submit_event(
            sequence=False, kind="gni.begin", payload={}
        )
    assert caught.value.code == "INVALID_SEQUENCE"

    http_runtime = _runtime(tmp_path)
    with TestClient(create_app(http_runtime)) as client:
        response = client.post(
            "/v1/events",
            headers={"Authorization": "Bearer secret-token"},
            json={
                "api_version": "aip/1",
                "artifact_refs": [],
                "kind": "gni.begin",
                "payload": {},
                "sequence": False,
                "session_id": http_runtime.session_id,
            },
        )
    assert response.status_code == 400
    assert response.json()["reason_code"] == "INVALID_SEQUENCE"


def test_inprocess_rejects_non_json_native_payload_before_logging(tmp_path: Path) -> None:
    runtime = ArthurRuntime.create(
        plugin=default_registry().get("t1.new_maxflow_min_cut"),
        case_id="c01",
        run_dir=tmp_path / "tuple-payload",
        mode=SessionMode.DEV,
        instance_seed=b"i" * 32,
        coin_seed=b"c" * 32,
        session_token="token",
    )
    certificate = dict(solve_maxflow(runtime.get_instance()))
    certificate["edge_flows"] = tuple(certificate["edge_flows"])
    with pytest.raises(AIPBenchError) as caught:
        runtime.submit_event(
            ParticipantEvent(sequence=0, kind="maxflow.certificate", payload=certificate)
        )
    assert caught.value.code == "INVALID_PAYLOAD"
    assert (runtime.run_dir / "official" / "transcript.jsonl").read_text() == ""
