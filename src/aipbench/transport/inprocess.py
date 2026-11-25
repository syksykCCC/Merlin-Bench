"""Deterministic in-process participant adapter used by tests and virtual agents."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from aipbench.core.models import ParticipantEvent
from aipbench.core.runtime import ArthurRuntime


class InProcessParticipantClient:
    def __init__(self, runtime: ArthurRuntime) -> None:
        self.runtime = runtime

    def get_session(self) -> Mapping[str, Any]:
        return self.runtime.get_session()

    def get_protocol(self) -> Mapping[str, Any]:
        return self.runtime.get_protocol()

    def get_instance(self) -> Mapping[str, Any]:
        return self.runtime.get_instance()

    def get_status(self) -> Mapping[str, Any]:
        return self.runtime.get_status()

    def upload_artifact(self, *, content: bytes, media_type: str) -> Mapping[str, Any]:
        return self.runtime.upload_artifact(content=content, media_type=media_type)

    def submit_event(
        self,
        *,
        sequence: int,
        kind: str,
        payload: Mapping[str, Any],
        artifact_refs: tuple[str, ...] = (),
    ) -> Mapping[str, Any]:
        return self.runtime.submit_event(
            ParticipantEvent(
                sequence=sequence,
                kind=kind,
                payload=payload,
                artifact_refs=artifact_refs,
            )
        )


InProcessArthur = InProcessParticipantClient

__all__ = ["InProcessArthur", "InProcessParticipantClient"]
