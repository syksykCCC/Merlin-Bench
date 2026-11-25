"""Interfaces implemented by task plugins and participant adapters."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any, Protocol

from aipbench.core.models import GeneratedCase, ParticipantEvent, SessionMode, Transition


class InstanceGenerator(Protocol):
    def generate(
        self,
        *,
        instance_seed: bytes,
        case_id: str,
        case_parameters: Mapping[str, Any],
    ) -> GeneratedCase: ...


class ArthurContext(Protocol):
    @property
    def mode(self) -> SessionMode: ...

    def random_bytes(self, *, tag: str, length: int) -> bytes: ...

    def random_int(self, *, tag: str, lower_inclusive: int, upper_exclusive: int) -> int: ...

    def random_field_element(self, *, tag: str, modulus: int) -> int: ...

    def get_artifact_path(self, artifact_id: str) -> Path: ...


class ArthurProtocol(Protocol):
    task_id: str
    task_version: str

    def initialize(self, *, generated_case: GeneratedCase, context: ArthurContext) -> Any: ...

    def public_protocol_description(
        self, *, generated_case: GeneratedCase
    ) -> Mapping[str, Any]: ...

    def handle_event(
        self,
        *,
        state: Any,
        event: ParticipantEvent,
        generated_case: GeneratedCase,
        context: ArthurContext,
    ) -> Transition: ...

    def terminal_metrics(self, *, state: Any) -> Mapping[str, int | float | str]: ...


class TaskPlugin(Protocol):
    manifest: Mapping[str, Any]
    case_parameters: Mapping[str, Mapping[str, Any]]
    generator: InstanceGenerator
    protocol: ArthurProtocol


class ParticipantClient(Protocol):
    def get_session(self) -> Mapping[str, Any]: ...

    def get_protocol(self) -> Mapping[str, Any]: ...

    def get_instance(self) -> Mapping[str, Any]: ...

    def upload_artifact(self, *, content: bytes, media_type: str) -> Mapping[str, Any]: ...

    def submit_event(
        self,
        *,
        sequence: int,
        kind: str,
        payload: Mapping[str, Any],
        artifact_refs: tuple[str, ...] = (),
    ) -> Mapping[str, Any]: ...


class VirtualAgent(Protocol):
    agent_id: str

    def run(self, *, client: ParticipantClient, workspace: Path) -> None: ...
