"""Append-only canonical JSONL transcript with a SHA-256 hash chain."""

from __future__ import annotations

import json
import os
import threading
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from aipbench.core.canonical import canonical_json_text, digest_json
from aipbench.core.errors import AIPBenchError, ErrorCode

GENESIS_HASH = "sha256:" + ("0" * 64)


class EventLog:
    def __init__(self, path: Path) -> None:
        self._lock = threading.RLock()
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.touch()
        records = load_and_validate_event_log(self.path)
        self._next_index = len(records)
        self._previous_hash = records[-1]["event_hash"] if records else GENESIS_HASH

    @property
    def transcript_root(self) -> str:
        return self._previous_hash

    @property
    def event_count(self) -> int:
        return self._next_index

    def append(
        self,
        *,
        direction: str,
        sequence: int,
        kind: str,
        payload: Mapping[str, Any],
        artifact_refs: Iterable[str] = (),
    ) -> Mapping[str, Any]:
        with self._lock:
            return self._append_locked(
                direction=direction,
                sequence=sequence,
                kind=kind,
                payload=payload,
                artifact_refs=artifact_refs,
            )

    def _append_locked(
        self,
        *,
        direction: str,
        sequence: int,
        kind: str,
        payload: Mapping[str, Any],
        artifact_refs: Iterable[str] = (),
    ) -> Mapping[str, Any]:
        base: dict[str, Any] = {
            "api_version": "aip/1",
            "artifact_refs": list(artifact_refs),
            "direction": direction,
            "event_index": self._next_index,
            "kind": kind,
            "payload": dict(payload),
            "payload_digest": digest_json(payload),
            "previous_event_hash": self._previous_hash,
            "sequence": sequence,
        }
        record = {**base, "event_hash": digest_json(base)}
        with self.path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(canonical_json_text(record))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        self._next_index += 1
        self._previous_hash = record["event_hash"]
        return record


def load_and_validate_event_log(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise AIPBenchError(ErrorCode.EVENT_CHAIN_INVALID, "transcript is missing")
    previous = GENESIS_HASH
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for index, line in enumerate(handle):
            if not line.strip():
                raise AIPBenchError(
                    ErrorCode.EVENT_CHAIN_INVALID, f"blank transcript line at index {index}"
                )
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise AIPBenchError(
                    ErrorCode.EVENT_CHAIN_INVALID, f"invalid JSON at transcript line {index + 1}"
                ) from exc
            if not isinstance(record, dict):
                raise AIPBenchError(ErrorCode.EVENT_CHAIN_INVALID, "event must be an object")
            claimed_hash = record.pop("event_hash", None)
            if record.get("event_index") != index:
                raise AIPBenchError(ErrorCode.EVENT_CHAIN_INVALID, "event index mismatch")
            if record.get("previous_event_hash") != previous:
                raise AIPBenchError(ErrorCode.EVENT_CHAIN_INVALID, "previous event hash mismatch")
            if record.get("payload_digest") != digest_json(record.get("payload")):
                raise AIPBenchError(ErrorCode.EVENT_CHAIN_INVALID, "payload digest mismatch")
            actual_hash = digest_json(record)
            if claimed_hash != actual_hash:
                raise AIPBenchError(ErrorCode.EVENT_CHAIN_INVALID, "event hash mismatch")
            full_record = {**record, "event_hash": claimed_hash}
            records.append(full_record)
            previous = claimed_hash
    return records
