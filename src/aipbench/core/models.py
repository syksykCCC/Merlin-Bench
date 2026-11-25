"""Immutable transport-independent runtime models."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class SessionMode(StrEnum):
    DEV = "dev"
    EVAL = "eval"


class SessionLifecycle(StrEnum):
    CREATED = "CREATED"
    PREPARED = "PREPARED"
    ACTIVE = "ACTIVE"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    TIMEOUT = "TIMEOUT"
    SYSTEM_ERROR = "SYSTEM_ERROR"


class TerminalStatus(StrEnum):
    ACCEPT = "ACCEPT"
    REJECT = "REJECT"
    TIMEOUT = "TIMEOUT"
    SYSTEM_ERROR = "SYSTEM_ERROR"


@dataclass(frozen=True)
class GeneratedCase:
    task_id: str
    task_version: str
    case_id: str
    public_instance: Mapping[str, Any]
    private_instance: Mapping[str, Any]
    generation_metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ParticipantEvent:
    sequence: int
    kind: str
    payload: Mapping[str, Any]
    artifact_refs: tuple[str, ...] = ()


@dataclass(frozen=True)
class ProtocolReply:
    kind: str
    payload: Mapping[str, Any]


@dataclass(frozen=True)
class Transition:
    new_state: Any
    reply: ProtocolReply | None = None
    terminal_status: TerminalStatus | None = None
    reason_code: str | None = None
    milestones: Mapping[str, int | float | str] = field(default_factory=dict)
    public_state: Mapping[str, Any] = field(default_factory=dict)
