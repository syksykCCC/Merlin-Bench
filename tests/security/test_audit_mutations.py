from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from aipbench.audit import audit_run
from aipbench.core.models import SessionMode
from aipbench.core.runtime import ArthurRuntime
from aipbench.registry import default_registry
from aipbench.tasks.shared.graph_non_isomorphism import VIRTUAL_AGENTS as GNI_AGENTS
from aipbench.tasks.shared.maxflow import solve_maxflow
from aipbench.transport.inprocess import InProcessParticipantClient


@pytest.fixture
def accepted_run(tmp_path: Path) -> Path:
    runtime = ArthurRuntime.create(
        plugin=default_registry().get("t1.new_maxflow_min_cut"),
        case_id="c01",
        run_dir=tmp_path / "accepted",
        mode=SessionMode.EVAL,
        instance_seed=b"i" * 32,
        coin_seed=b"c" * 32,
        run_id="mutation-source",
        session_token="token",
    )
    client = InProcessParticipantClient(runtime)
    artifact = client.upload_artifact(
        content=b"artifact-bytes", media_type="application/octet-stream"
    )
    assert artifact["artifact_id"].startswith("sha256:")
    client.submit_event(
        sequence=0,
        kind="maxflow.certificate",
        payload=solve_maxflow(client.get_instance()),
    )
    assert audit_run(runtime.run_dir)["official_result"] == "PASS"
    return runtime.run_dir


def _copy(accepted_run: Path, name: str) -> Path:
    destination = accepted_run.parent / name
    shutil.copytree(accepted_run, destination)
    return destination


def _mutate_json(path: Path, update: callable) -> None:
    value = json.loads(path.read_text(encoding="utf-8"))
    update(value)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


@pytest.mark.parametrize(
    "mutation",
    [
        "result",
        "signature",
        "seed",
        "transcript",
        "instance",
        "private-instance",
        "generation-metadata",
        "protocol",
        "session",
        "manifest",
        "artifact",
        "artifact-index",
        "artifact-directory",
        "coin-algorithm",
        "key-algorithm",
    ],
)
def test_offline_audit_rejects_mutations(accepted_run: Path, mutation: str) -> None:
    run_dir = _copy(accepted_run, f"mutated-{mutation}")
    if mutation == "result":
        _mutate_json(
            run_dir / "official" / "result.json",
            lambda value: value.__setitem__("terminal_status", "REJECT"),
        )
    elif mutation == "signature":
        (run_dir / "official" / "result.sig").write_text("AAAA\n", encoding="ascii")
    elif mutation == "seed":
        _mutate_json(
            run_dir / "official" / "seed_reveal.json",
            lambda value: value.__setitem__("seed_hex", "00" * 32),
        )
    elif mutation == "transcript":
        transcript = run_dir / "official" / "transcript.jsonl"
        lines = transcript.read_text(encoding="utf-8").splitlines()
        first = json.loads(lines[0])
        first["payload"]["flow_value"] += 1
        lines[0] = json.dumps(first)
        transcript.write_text("\n".join(lines) + "\n", encoding="utf-8")
    elif mutation == "instance":
        _mutate_json(
            run_dir / "public" / "instance.json",
            lambda value: value.__setitem__("source", value["sink"]),
        )
    elif mutation == "private-instance":
        _mutate_json(
            run_dir / "private" / "instance.private.json",
            lambda value: value.__setitem__("reference_flow_value", 999_999_999),
        )
    elif mutation == "generation-metadata":
        _mutate_json(
            run_dir / "private" / "generation.metadata.json",
            lambda value: value.__setitem__("tampered", True),
        )
    elif mutation == "protocol":
        _mutate_json(
            run_dir / "public" / "protocol.json",
            lambda value: value.__setitem__("initial_event_kinds", ["tampered.event"]),
        )
    elif mutation == "session":
        _mutate_json(
            run_dir / "official" / "session.json",
            lambda value: value.__setitem__("task_id", "t1.tampered"),
        )
    elif mutation == "manifest":
        _mutate_json(
            run_dir / "official" / "task_manifest.json",
            lambda value: value.__setitem__("title", "tampered"),
        )
    elif mutation == "artifact":
        artifact_files = [
            path
            for path in (run_dir / "official" / "artifacts" / "sha256").glob("*/*")
            if path.is_file()
        ]
        assert len(artifact_files) == 1
        artifact_files[0].write_bytes(b"tampered")
    elif mutation == "artifact-index":
        (run_dir / "official" / "artifacts" / "index.jsonl").write_text("", encoding="utf-8")
    elif mutation == "artifact-directory":
        shutil.rmtree(run_dir / "official" / "artifacts")
    elif mutation == "coin-algorithm":
        _mutate_json(
            run_dir / "official" / "seed_commitment.json",
            lambda value: value.__setitem__("algorithm", "tampered"),
        )
    elif mutation == "key-algorithm":
        _mutate_json(
            run_dir / "official" / "signing_public_key.json",
            lambda value: value.__setitem__("algorithm", "tampered"),
        )
    report = audit_run(run_dir)
    assert report["audit_passed"] is False
    assert report["official_result"] == "FAIL"


def test_audit_can_pin_an_external_signing_key(accepted_run: Path) -> None:
    key_document = json.loads(
        (accepted_run / "official" / "signing_public_key.json").read_text(encoding="utf-8")
    )
    assert (
        audit_run(accepted_run, trusted_public_key_base64=key_document["public_key"])[
            "signing_key_trust"
        ]
        == "external"
    )
    report = audit_run(accepted_run, trusted_public_key_base64="A" * 44)
    assert report["audit_passed"] is False
    empty_key_report = audit_run(accepted_run, trusted_public_key_base64="")
    assert empty_key_report["audit_passed"] is False


@pytest.mark.parametrize(
    ("relative_path", "replacement"),
    [
        ("official/result.json", []),
        ("official/session.json", None),
        ("official/task_manifest.json", []),
        ("public/instance.json", "invalid"),
        ("public/protocol.json", []),
        ("private/instance.private.json", None),
        ("private/generation.metadata.json", []),
        ("official/seed_commitment.json", []),
        ("official/signing_public_key.json", None),
    ],
)
def test_audit_returns_fail_instead_of_crashing_on_wrong_json_root(
    accepted_run: Path, relative_path: str, replacement: object
) -> None:
    run_dir = _copy(accepted_run, "wrong-root-" + relative_path.replace("/", "-"))
    (run_dir / relative_path).write_text(json.dumps(replacement), encoding="utf-8")
    report = audit_run(run_dir, write_report=False)
    assert report["audit_passed"] is False
    assert report["official_result"] == "FAIL"


@pytest.fixture
def accepted_gni_run(tmp_path: Path) -> Path:
    runtime = ArthurRuntime.create(
        plugin=default_registry().get("t2.new_graph_non_isomorphism"),
        case_id="c01",
        run_dir=tmp_path / "accepted-gni",
        mode=SessionMode.EVAL,
        instance_seed=b"s" * 32,
        coin_seed=b"r" * 32,
        run_id="gni-mutation-source",
        session_token="token",
    )
    GNI_AGENTS["virtual-honest"].run(
        client=InProcessParticipantClient(runtime),
        workspace=runtime.run_dir / "workspace",
    )
    assert audit_run(runtime.run_dir)["official_result"] == "PASS"
    return runtime.run_dir


@pytest.mark.parametrize("mutation", ["challenge", "source-bit", "event-order"])
def test_gni_audit_rejects_protocol_transcript_mutations(
    accepted_gni_run: Path, mutation: str
) -> None:
    run_dir = _copy(accepted_gni_run, f"gni-mutated-{mutation}")
    transcript = run_dir / "official" / "transcript.jsonl"
    records = [json.loads(line) for line in transcript.read_text(encoding="utf-8").splitlines()]
    if mutation == "challenge":
        challenge_record = next(
            record
            for record in records
            if record["direction"] == "ARTHUR_TO_MERLIN"
            and record["payload"].get("reply", {}).get("kind") == "gni.challenge"
        )
        payload = challenge_record["payload"]["reply"]["payload"]
        payload["graphs"][0]["edges"][0].reverse()
    elif mutation == "source-bit":
        response_record = next(
            record
            for record in records
            if record["direction"] == "MERLIN_TO_ARTHUR" and record["kind"] == "gni.response"
        )
        response_record["payload"]["source_bits"][0] ^= 1
    else:
        records[2], records[3] = records[3], records[2]
    transcript.write_text(
        "\n".join(json.dumps(record) for record in records) + "\n", encoding="utf-8"
    )
    report = audit_run(run_dir)
    assert report["audit_passed"] is False
    assert report["official_result"] == "FAIL"
