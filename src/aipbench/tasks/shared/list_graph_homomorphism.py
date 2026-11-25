"""Shared primitives used by the current Merlin-Bench tasks."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, TypeGuard

from aipbench.core.errors import ErrorCode
from aipbench.core.models import GeneratedCase, ParticipantEvent, TerminalStatus, Transition
from aipbench.core.protocol import ArthurContext, ParticipantClient, VirtualAgent

TASK_ID: Final = "t1.new_list_graph_homomorphism"

TASK_VERSION: Final = "0.1.0"

MAPPING_EVENT_KIND: Final = "homomorphism.assignment"

_INSTANCE_FIELDS: Final = frozenset(
    {
        "format_version",
        "source_num_vertices",
        "source_edges",
        "target_num_vertices",
        "target_edges",
        "lists",
    }
)

_EDGE_FIELDS: Final = frozenset({"edge_id", "u", "v"})

_LIST_FIELDS: Final = frozenset({"source_vertex", "allowed_targets"})

_MAPPING_FIELDS: Final = frozenset({"mapping"})


class HomomorphismReason:
    """Stable participant-visible rejection codes."""

    MAPPING_LENGTH_MISMATCH = "HOMOMORPHISM_MAPPING_LENGTH_MISMATCH"
    TARGET_VERTEX_INVALID = "HOMOMORPHISM_TARGET_VERTEX_INVALID"
    LIST_VIOLATION = "HOMOMORPHISM_LIST_VIOLATION"
    EDGE_VIOLATION = "HOMOMORPHISM_EDGE_VIOLATION"


@dataclass(frozen=True)
class HomomorphismProtocolState:
    phase: str = "awaiting_mapping"
    terminal_status: TerminalStatus | None = None
    reason_code: str | None = None
    events_processed: int = 0


@dataclass(frozen=True)
class _Instance:
    source_num_vertices: int
    source_edges: tuple[tuple[int, int], ...]
    target_num_vertices: int
    target_adjacency: frozenset[tuple[int, int]]
    allowed_targets: tuple[frozenset[int], ...]


class _MappingRejected(Exception):
    def __init__(self, reason_code: str) -> None:
        super().__init__(reason_code)
        self.reason_code = reason_code


def _is_integer(value: object) -> TypeGuard[int]:
    return isinstance(value, int) and not isinstance(value, bool)


def _parse_edge_table(
    value: object,
    *,
    num_vertices: int,
    graph_name: str,
) -> tuple[tuple[int, int], ...]:
    if not isinstance(value, list):
        raise ValueError(f"generated {graph_name} edge table must be an array")
    edge_ids: set[int] = set()
    pairs: set[tuple[int, int]] = set()
    result: list[tuple[int, int]] = []
    for raw_edge in value:
        if not isinstance(raw_edge, Mapping) or set(raw_edge) != _EDGE_FIELDS:
            raise ValueError(f"generated {graph_name} edge is malformed")
        edge_id = raw_edge.get("edge_id")
        u = raw_edge.get("u")
        v = raw_edge.get("v")
        if not _is_integer(edge_id) or not _is_integer(u) or not _is_integer(v):
            raise ValueError(f"generated {graph_name} edge fields must be JSON integers")
        assert isinstance(edge_id, int)
        assert isinstance(u, int)
        assert isinstance(v, int)
        if edge_id < 0 or not 1 <= u < v <= num_vertices:
            raise ValueError(f"generated {graph_name} edge is outside a simple graph")
        if edge_id in edge_ids or (u, v) in pairs:
            raise ValueError(f"generated {graph_name} graph contains duplicate edge data")
        edge_ids.add(edge_id)
        pairs.add((u, v))
        result.append((u, v))
    return tuple(result)


def _parse_instance(public_instance: Mapping[str, Any]) -> _Instance:
    if set(public_instance) != _INSTANCE_FIELDS:
        raise ValueError("malformed generated List Graph Homomorphism instance")
    if public_instance.get("format_version") != "aip-list-graph-homomorphism-instance/1":
        raise ValueError("unsupported List Graph Homomorphism instance format")
    source_num_vertices = public_instance.get("source_num_vertices")
    target_num_vertices = public_instance.get("target_num_vertices")
    raw_lists = public_instance.get("lists")
    if (
        not _is_integer(source_num_vertices)
        or not _is_integer(target_num_vertices)
        or not isinstance(raw_lists, list)
    ):
        raise ValueError("malformed generated List Graph Homomorphism fields")
    assert isinstance(source_num_vertices, int)
    assert isinstance(target_num_vertices, int)
    if source_num_vertices < 1 or target_num_vertices < 1:
        raise ValueError("generated graph orders must be positive")
    source_edges = _parse_edge_table(
        public_instance.get("source_edges"),
        num_vertices=source_num_vertices,
        graph_name="source",
    )
    target_edges = _parse_edge_table(
        public_instance.get("target_edges"),
        num_vertices=target_num_vertices,
        graph_name="target",
    )

    allowed_by_source: dict[int, frozenset[int]] = {}
    for raw_list in raw_lists:
        if not isinstance(raw_list, Mapping) or set(raw_list) != _LIST_FIELDS:
            raise ValueError("generated target list is malformed")
        source_vertex = raw_list.get("source_vertex")
        raw_allowed = raw_list.get("allowed_targets")
        if not _is_integer(source_vertex) or not isinstance(raw_allowed, list):
            raise ValueError("generated target-list fields have invalid types")
        assert isinstance(source_vertex, int)
        if not 1 <= source_vertex <= source_num_vertices or source_vertex in allowed_by_source:
            raise ValueError("generated target lists do not uniquely index source vertices")
        if not raw_allowed:
            raise ValueError("generated target list must be nonempty")
        allowed: set[int] = set()
        for target_vertex in raw_allowed:
            if not _is_integer(target_vertex):
                raise ValueError("generated target list contains a non-integer")
            assert isinstance(target_vertex, int)
            if not 1 <= target_vertex <= target_num_vertices or target_vertex in allowed:
                raise ValueError("generated target list contains invalid or repeated targets")
            allowed.add(target_vertex)
        allowed_by_source[source_vertex] = frozenset(allowed)
    if set(allowed_by_source) != set(range(1, source_num_vertices + 1)):
        raise ValueError("generated target lists must cover every source vertex exactly once")

    return _Instance(
        source_num_vertices=source_num_vertices,
        source_edges=source_edges,
        target_num_vertices=target_num_vertices,
        target_adjacency=frozenset(target_edges),
        allowed_targets=tuple(
            allowed_by_source[source_vertex] for source_vertex in range(1, source_num_vertices + 1)
        ),
    )


def _parse_mapping(mapping: object, instance: _Instance) -> tuple[int, ...]:
    if not isinstance(mapping, list) or len(mapping) != instance.source_num_vertices:
        raise _MappingRejected(HomomorphismReason.MAPPING_LENGTH_MISMATCH)
    result: list[int] = []
    for target_vertex in mapping:
        if not _is_integer(target_vertex) or not 1 <= target_vertex <= instance.target_num_vertices:
            raise _MappingRejected(HomomorphismReason.TARGET_VERTEX_INVALID)
        assert isinstance(target_vertex, int)
        result.append(target_vertex)
    return tuple(result)


def evaluate_mapping(public_instance: Mapping[str, Any], mapping: object) -> tuple[bool, bool]:
    """Return whether a strictly parsed mapping satisfies lists and edges."""

    instance = _parse_instance(public_instance)
    assignment = _parse_mapping(mapping, instance)
    lists_valid = all(
        target in instance.allowed_targets[source] for source, target in enumerate(assignment)
    )
    edges_valid = all(
        tuple(sorted((assignment[first - 1], assignment[second - 1]))) in instance.target_adjacency
        for first, second in instance.source_edges
    )
    return lists_valid, edges_valid


def _verify_mapping(payload: Mapping[str, Any], instance: _Instance) -> None:
    if set(payload) != _MAPPING_FIELDS:
        raise _MappingRejected(ErrorCode.INVALID_PAYLOAD)
    assignment = _parse_mapping(payload.get("mapping"), instance)
    if any(
        target not in instance.allowed_targets[source] for source, target in enumerate(assignment)
    ):
        raise _MappingRejected(HomomorphismReason.LIST_VIOLATION)
    if any(
        tuple(sorted((assignment[first - 1], assignment[second - 1])))
        not in instance.target_adjacency
        for first, second in instance.source_edges
    ):
        raise _MappingRejected(HomomorphismReason.EDGE_VIOLATION)


class ListGraphHomomorphismProtocol:
    """Pure one-shot verifier for a complete public list homomorphism."""

    task_id = TASK_ID
    task_version = TASK_VERSION
    event_schema_ref = "tasks/tier1_np/new_list_graph_homomorphism/schemas/mapping.schema.json"

    def initialize(
        self, *, generated_case: GeneratedCase, context: ArthurContext
    ) -> HomomorphismProtocolState:
        del context
        self._validate_task_identity(generated_case)
        _parse_instance(generated_case.public_instance)
        return HomomorphismProtocolState()

    def public_protocol_description(self, *, generated_case: GeneratedCase) -> Mapping[str, Any]:
        self._validate_task_identity(generated_case)
        instance = _parse_instance(generated_case.public_instance)
        return {
            "api_version": "aip/1",
            "mode": "one_shot",
            "initial_event_kinds": [MAPPING_EVENT_KIND],
            "event_schemas": {MAPPING_EVENT_KIND: {"schema_ref": self.event_schema_ref}},
            "public_parameters": {
                "source_num_vertices": instance.source_num_vertices,
                "source_num_edges": len(instance.source_edges),
                "target_num_vertices": instance.target_num_vertices,
                "target_num_edges": len(instance.target_adjacency),
                "one_shot": True,
            },
        }

    def handle_event(
        self,
        *,
        state: Any,
        event: ParticipantEvent,
        generated_case: GeneratedCase,
        context: ArthurContext,
    ) -> Transition:
        del context
        if not isinstance(state, HomomorphismProtocolState):
            raise TypeError("state is not a HomomorphismProtocolState")
        self._validate_task_identity(generated_case)
        if state.terminal_status is not None:
            return Transition(
                new_state=state,
                terminal_status=TerminalStatus.REJECT,
                reason_code=ErrorCode.SESSION_TERMINAL,
                public_state={"phase": "terminal"},
            )
        if event.kind != MAPPING_EVENT_KIND:
            return self._rejection(ErrorCode.INVALID_EVENT_KIND)
        if event.artifact_refs:
            return self._rejection(ErrorCode.INVALID_PAYLOAD)

        instance = _parse_instance(generated_case.public_instance)
        try:
            _verify_mapping(event.payload, instance)
        except _MappingRejected as rejected:
            return self._rejection(rejected.reason_code)

        accepted = HomomorphismProtocolState(
            phase="terminal",
            terminal_status=TerminalStatus.ACCEPT,
            reason_code=ErrorCode.PROTOCOL_ACCEPT,
            events_processed=1,
        )
        return Transition(
            new_state=accepted,
            terminal_status=TerminalStatus.ACCEPT,
            reason_code=ErrorCode.PROTOCOL_ACCEPT,
            milestones={"mapping_submitted": 1},
            public_state={"phase": "terminal", "mapping_checked": True},
        )

    def terminal_metrics(self, *, state: Any) -> Mapping[str, int | float | str]:
        if not isinstance(state, HomomorphismProtocolState):
            raise TypeError("state is not a HomomorphismProtocolState")
        metrics: dict[str, int | float | str] = {
            "events_processed": state.events_processed,
            "mapping_valid": int(state.terminal_status == TerminalStatus.ACCEPT),
        }
        if state.reason_code is not None:
            metrics["reason_code"] = state.reason_code
        return metrics

    @classmethod
    def _validate_task_identity(cls, generated_case: GeneratedCase) -> None:
        if generated_case.task_id != cls.task_id or generated_case.task_version != cls.task_version:
            raise ValueError("generated case does not belong to this task plugin")

    @staticmethod
    def _rejection(reason_code: str) -> Transition:
        rejected = HomomorphismProtocolState(
            phase="terminal",
            terminal_status=TerminalStatus.REJECT,
            reason_code=reason_code,
            events_processed=1,
        )
        return Transition(
            new_state=rejected,
            terminal_status=TerminalStatus.REJECT,
            reason_code=reason_code,
            milestones={"mapping_submitted": 1},
            public_state={"phase": "terminal", "mapping_checked": False},
        )


def _participant_instance(client: ParticipantClient) -> Mapping[str, Any]:
    response = client.get_instance()
    nested = response.get("public_instance")
    return nested if isinstance(nested, Mapping) else response


class WrongLengthHomomorphismAgent:
    agent_id = "virtual-wrong-length"

    def run(self, *, client: ParticipantClient, workspace: Path) -> None:
        del workspace
        instance = _participant_instance(client)
        source_num_vertices = instance.get("source_num_vertices")
        if not _is_integer(source_num_vertices) or source_num_vertices < 1:
            raise ValueError("participant returned a malformed homomorphism instance")
        assert isinstance(source_num_vertices, int)
        client.submit_event(
            sequence=0,
            kind=MAPPING_EVENT_KIND,
            payload={"mapping": [1] * (source_num_vertices - 1)},
        )


class InvalidTargetHomomorphismAgent:
    agent_id = "virtual-invalid-target"

    def run(self, *, client: ParticipantClient, workspace: Path) -> None:
        del workspace
        instance = _participant_instance(client)
        source_num_vertices = instance.get("source_num_vertices")
        if not _is_integer(source_num_vertices) or source_num_vertices < 1:
            raise ValueError("participant returned a malformed homomorphism instance")
        assert isinstance(source_num_vertices, int)
        mapping = [1] * source_num_vertices
        mapping[0] = 0
        client.submit_event(
            sequence=0,
            kind=MAPPING_EVENT_KIND,
            payload={"mapping": mapping},
        )


_VIRTUAL_AGENT_LIST: Final[tuple[VirtualAgent, ...]] = (
    WrongLengthHomomorphismAgent(),
    InvalidTargetHomomorphismAgent(),
)

VIRTUAL_AGENTS: Final[Mapping[str, VirtualAgent]] = {
    agent.agent_id: agent for agent in _VIRTUAL_AGENT_LIST
}
