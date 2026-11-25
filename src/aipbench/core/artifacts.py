"""Content-addressed artifact storage with strict identifier validation."""

from __future__ import annotations

import json
import os
import re
import threading
from pathlib import Path
from typing import Any

from aipbench.core.canonical import canonical_json_text, sha256_hex
from aipbench.core.errors import AIPBenchError, ErrorCode

ARTIFACT_ID_RE = re.compile(r"^sha256:([0-9a-f]{64})$")


class ArtifactStore:
    def __init__(
        self,
        root: Path,
        *,
        max_total_bytes: int,
        max_single_bytes: int | None = None,
        read_only: bool = False,
    ) -> None:
        self._lock = threading.RLock()
        self.root = root.resolve()
        self.max_total_bytes = max_total_bytes
        self.max_single_bytes = max_single_bytes or max_total_bytes
        self.read_only = read_only
        self.content_root = self.root / "sha256"
        self.index_path = self.root / "index.jsonl"
        if read_only:
            if not self.content_root.is_dir() or not self.index_path.is_file():
                raise AIPBenchError(
                    ErrorCode.ARTIFACT_NOT_FOUND,
                    "artifact store or append-only index is missing",
                )
        else:
            self.content_root.mkdir(parents=True, exist_ok=True)
            self.index_path.touch(exist_ok=True)

    def _current_total(self) -> int:
        return sum(path.stat().st_size for path in self.content_root.glob("*/*") if path.is_file())

    def _path_for_digest(self, digest: str) -> Path:
        path = (self.content_root / digest[:2] / digest).resolve()
        if self.content_root not in path.parents:
            raise AIPBenchError(ErrorCode.ARTIFACT_HASH_MISMATCH, "invalid artifact path")
        return path

    def put(self, *, content: bytes, media_type: str) -> dict[str, Any]:
        with self._lock:
            return self._put_locked(content=content, media_type=media_type)

    def _put_locked(self, *, content: bytes, media_type: str) -> dict[str, Any]:
        if self.read_only:
            raise AIPBenchError(ErrorCode.ARTIFACT_NOT_FOUND, "artifact store is read-only")
        if type(content) is not bytes:
            raise AIPBenchError(ErrorCode.INVALID_PAYLOAD, "artifact content must be bytes")
        if (
            not isinstance(media_type, str)
            or not media_type
            or media_type.strip() != media_type
            or len(media_type) > 255
        ):
            raise AIPBenchError(ErrorCode.INVALID_PAYLOAD, "invalid artifact media type")
        size = len(content)
        digest = sha256_hex(content)
        artifact_id = f"sha256:{digest}"
        path = self._path_for_digest(digest)
        metadata = {
            "artifact_id": artifact_id,
            "media_type": media_type,
            "size_bytes": size,
        }
        if path.exists():
            if path.read_bytes() != content:
                raise AIPBenchError(
                    ErrorCode.ARTIFACT_HASH_MISMATCH, "stored artifact hash mismatch"
                )
            existing = self._indexed_metadata(artifact_id)
            if existing is None:
                raise AIPBenchError(
                    ErrorCode.ARTIFACT_HASH_MISMATCH,
                    "stored artifact is missing from the append-only index",
                )
            if existing != metadata:
                raise AIPBenchError(
                    "ARTIFACT_METADATA_CONFLICT",
                    "content identifier already has different canonical metadata",
                )
            return existing
        if size > self.max_single_bytes or self._current_total() + size > self.max_total_bytes:
            raise AIPBenchError(
                ErrorCode.BUDGET_EXCEEDED, "artifact byte budget exceeded", http_status=413
            )
        created = False
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with path.open("xb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            created = True
        except FileExistsError:  # concurrent identical upload
            pass
        if path.read_bytes() != content:
            raise AIPBenchError(ErrorCode.ARTIFACT_HASH_MISMATCH, "stored artifact hash mismatch")
        if created:
            with self.index_path.open("a", encoding="utf-8", newline="\n") as handle:
                handle.write(canonical_json_text(metadata) + "\n")
        return metadata

    def _indexed_metadata(self, artifact_id: str) -> dict[str, Any] | None:
        with self.index_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                entry = json.loads(line)
                if isinstance(entry, dict) and entry.get("artifact_id") == artifact_id:
                    return entry
        return None

    def resolve(self, artifact_id: str) -> Path:
        match = ARTIFACT_ID_RE.fullmatch(artifact_id)
        if match is None:
            raise AIPBenchError(ErrorCode.ARTIFACT_NOT_FOUND, "malformed artifact identifier")
        digest = match.group(1)
        path = self._path_for_digest(digest)
        if not path.is_file():
            raise AIPBenchError(ErrorCode.ARTIFACT_NOT_FOUND, "artifact does not exist")
        if sha256_hex(path.read_bytes()) != digest:
            raise AIPBenchError(ErrorCode.ARTIFACT_HASH_MISMATCH, "artifact content hash mismatch")
        return path

    def validate_index(self) -> list[dict[str, Any]]:
        entries: list[dict[str, Any]] = []
        indexed_ids: set[str] = set()
        indexed_digests: set[str] = set()
        total_size = 0
        with self.index_path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    raise AIPBenchError(
                        ErrorCode.ARTIFACT_HASH_MISMATCH,
                        f"blank artifact index line {line_number}",
                    )
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise AIPBenchError(
                        ErrorCode.ARTIFACT_HASH_MISMATCH,
                        f"invalid artifact index JSON at line {line_number}",
                    ) from exc
                if (
                    not isinstance(entry, dict)
                    or set(entry) != {"artifact_id", "media_type", "size_bytes"}
                    or not isinstance(entry.get("artifact_id"), str)
                    or not isinstance(entry.get("media_type"), str)
                    or not entry["media_type"]
                    or not isinstance(entry.get("size_bytes"), int)
                    or isinstance(entry.get("size_bytes"), bool)
                    or entry["size_bytes"] < 0
                ):
                    raise AIPBenchError(
                        ErrorCode.ARTIFACT_HASH_MISMATCH,
                        f"invalid artifact index entry at line {line_number}",
                    )
                if line.rstrip("\r\n") != canonical_json_text(entry):
                    raise AIPBenchError(
                        ErrorCode.ARTIFACT_HASH_MISMATCH,
                        f"non-canonical artifact index entry at line {line_number}",
                    )
                artifact_id = entry["artifact_id"]
                if artifact_id in indexed_ids:
                    raise AIPBenchError(
                        ErrorCode.ARTIFACT_HASH_MISMATCH,
                        f"duplicate artifact index entry: {artifact_id}",
                    )
                path = self.resolve(artifact_id)
                if path.stat().st_size != entry["size_bytes"]:
                    raise AIPBenchError(ErrorCode.ARTIFACT_HASH_MISMATCH, "artifact size mismatch")
                entries.append(entry)
                indexed_ids.add(artifact_id)
                indexed_digests.add(artifact_id.removeprefix("sha256:"))
                total_size += entry["size_bytes"]
        if total_size > self.max_total_bytes:
            raise AIPBenchError(ErrorCode.BUDGET_EXCEEDED, "artifact index exceeds byte budget")
        stored_files = {path for path in self.content_root.rglob("*") if path.is_file()}
        expected_files = {self._path_for_digest(digest) for digest in indexed_digests}
        if stored_files != expected_files:
            raise AIPBenchError(
                ErrorCode.ARTIFACT_HASH_MISMATCH,
                "artifact store contains missing or unindexed content",
            )
        return entries
