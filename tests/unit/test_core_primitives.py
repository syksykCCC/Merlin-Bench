from __future__ import annotations

import json
from pathlib import Path

import pytest

from aipbench.core.artifacts import ArtifactStore
from aipbench.core.canonical import canonical_json_bytes, digest_json
from aipbench.core.errors import AIPBenchError
from aipbench.core.event_log import EventLog, load_and_validate_event_log
from aipbench.core.randomness import CommittedPRG, seed_commitment
from aipbench.core.signing import ResultSigner, verify_signature


def test_canonical_json_is_stable_and_preserves_large_integers() -> None:
    left = {"z": 2**80, "a": [3, {"b": True}]}
    right = {"a": [3, {"b": True}], "z": 2**80}
    assert canonical_json_bytes(left) == canonical_json_bytes(right)
    assert digest_json(left) == digest_json(right)
    assert b"1208925819614629174706176" in canonical_json_bytes(left)


def test_committed_prg_is_replayable_bound_to_event_and_rejects_duplicate_tags() -> None:
    seed = bytes(range(32))
    first = CommittedPRG(seed=seed, run_id="run", task_digest="sha256:" + "1" * 64)
    replay = CommittedPRG(seed=seed, run_id="run", task_digest="sha256:" + "1" * 64)
    value = first.random_int(
        tag="task/case/phase/0/challenge",
        lower_inclusive=0,
        upper_exclusive=97,
        event_hash="sha256:" + "2" * 64,
    )
    assert value == replay.random_int(
        tag="task/case/phase/0/challenge",
        lower_inclusive=0,
        upper_exclusive=97,
        event_hash="sha256:" + "2" * 64,
    )
    with pytest.raises(AIPBenchError, match="duplicate"):
        first.random_bytes(tag="task/case/phase/0/challenge", length=1, event_hash="x")
    changed = CommittedPRG(seed=seed, run_id="run", task_digest="sha256:" + "1" * 64)
    changed_value = changed.random_bytes(
        tag="task/case/phase/0/bytes", length=32, event_hash="sha256:" + "3" * 64
    )
    original = CommittedPRG(seed=seed, run_id="run", task_digest="sha256:" + "1" * 64)
    original_value = original.random_bytes(
        tag="task/case/phase/0/bytes", length=32, event_hash="sha256:" + "2" * 64
    )
    assert changed_value != original_value
    assert first.commitment == seed_commitment(
        seed=seed, run_id="run", task_digest="sha256:" + "1" * 64
    )
    wide = CommittedPRG(seed=seed, run_id="wide", task_digest="sha256:" + "4" * 64)
    wide_value = wide.random_int(
        tag="task/case/wide/0/challenge",
        lower_inclusive=0,
        upper_exclusive=1 << 520,
        event_hash="sha256:" + "5" * 64,
    )
    assert 0 <= wide_value < 1 << 520


def test_ed25519_signature_detects_mutation() -> None:
    signer = ResultSigner.generate()
    data = canonical_json_bytes({"terminal_status": "ACCEPT"})
    signature = signer.sign(data)
    assert verify_signature(
        public_key_base64=signer.public_base64,
        data=data,
        signature_base64=signature,
    )
    assert not verify_signature(
        public_key_base64=signer.public_base64,
        data=data + b"!",
        signature_base64=signature,
    )


def test_event_log_round_trip_and_mutation_detection(tmp_path: Path) -> None:
    path = tmp_path / "transcript.jsonl"
    log = EventLog(path)
    first = log.append(direction="MERLIN_TO_ARTHUR", sequence=0, kind="claim", payload={"x": 1})
    second = log.append(
        direction="ARTHUR_TO_MERLIN",
        sequence=0,
        kind="runtime.response",
        payload={"status": "ACCEPT"},
    )
    records = load_and_validate_event_log(path)
    assert [record["event_hash"] for record in records] == [
        first["event_hash"],
        second["event_hash"],
    ]
    lines = path.read_text(encoding="utf-8").splitlines()
    tampered = json.loads(lines[0])
    tampered["payload"]["x"] = 2
    lines[0] = json.dumps(tampered)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    with pytest.raises(AIPBenchError) as caught:
        load_and_validate_event_log(path)
    assert caught.value.code == "EVENT_CHAIN_INVALID"


def test_content_addressed_artifacts_enforce_hash_and_budget(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path / "artifacts", max_total_bytes=10)
    metadata = store.put(content=b"proof", media_type="application/octet-stream")
    assert store.resolve(metadata["artifact_id"]).read_bytes() == b"proof"
    assert (
        store.put(content=b"proof", media_type="application/octet-stream")["artifact_id"]
        == metadata["artifact_id"]
    )
    with pytest.raises(AIPBenchError) as caught:
        store.put(content=b"proof", media_type="text/plain")
    assert caught.value.code == "ARTIFACT_METADATA_CONFLICT"
    with pytest.raises(AIPBenchError):
        store.resolve("../../private/instance.private.json")
    with pytest.raises(AIPBenchError) as caught:
        store.put(content=b"01234567890", media_type="text/plain")
    assert caught.value.code == "BUDGET_EXCEEDED"
    store.resolve(metadata["artifact_id"]).write_bytes(b"other")
    with pytest.raises(AIPBenchError) as caught:
        store.resolve(metadata["artifact_id"])
    assert caught.value.code == "ARTIFACT_HASH_MISMATCH"
