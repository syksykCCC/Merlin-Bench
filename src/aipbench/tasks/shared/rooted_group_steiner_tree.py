"""Shared primitives used by the current Merlin-Bench tasks."""

from __future__ import annotations

from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, TypeGuard

from aipbench.core.errors import ErrorCode
from aipbench.core.models import GeneratedCase, ParticipantEvent, TerminalStatus, Transition
from aipbench.core.protocol import ArthurContext, ParticipantClient, VirtualAgent

TASK_ID: Final = "t1.new_rooted_group_steiner_tree"

TASK_VERSION: Final = "0.1.0"

EDGE_SET_EVENT_KIND: Final = "group_steiner.edge_set"

MAX_SAFE_INTEGER: Final = 9_007_199_254_740_991

_INSTANCE_FIELDS: Final = frozenset(
    {"format_version", "num_vertices", "edges", "root", "groups", "budget"}
)

_EDGE_FIELDS: Final = frozenset({"edge_id", "u", "v", "weight"})

_GROUP_FIELDS: Final = frozenset({"group_id", "vertices"})

_EDGE_SET_FIELDS: Final = frozenset({"edge_ids"})


class GroupSteinerReason:
    """Stable participant-visible rejection codes."""

    EDGE_ID_INVALID = "GROUP_STEINER_EDGE_ID_INVALID"
    EDGE_ID_DUPLICATE = "GROUP_STEINER_EDGE_ID_DUPLICATE"
    BUDGET_EXCEEDED = "GROUP_STEINER_BUDGET_EXCEEDED"
    DISCONNECTED = "GROUP_STEINER_DISCONNECTED"
    GROUP_UNHIT = "GROUP_STEINER_GROUP_UNHIT"


@dataclass(frozen=True)
class GroupSteinerProtocolState:
    phase: str = "awaiting_edge_set"
    terminal_status: TerminalStatus | None = None
    reason_code: str | None = None
    events_processed: int = 0


@dataclass(frozen=True)
class _Edge:
    first: int
    second: int
    weight: int


@dataclass(frozen=True)
class _Instance:
    num_vertices: int
    edges_by_id: Mapping[int, _Edge]
    root: int
    groups: tuple[frozenset[int], ...]
    budget: int


@dataclass(frozen=True)
class EdgeSetEvaluation:
    cost: int
    connected: bool
    groups_hit: bool


class _SubmissionRejected(Exception):
    def __init__(self, reason_code: str) -> None:
        super().__init__(reason_code)
        self.reason_code = reason_code


def _is_integer(value: object) -> TypeGuard[int]:
    return isinstance(value, int) and not isinstance(value, bool)


def _parse_instance(public_instance: Mapping[str, Any]) -> _Instance:
    if set(public_instance) != _INSTANCE_FIELDS:
        raise ValueError("malformed generated Rooted Group Steiner Tree instance")
    if public_instance.get("format_version") != "aip-rooted-group-steiner-tree-instance/1":
        raise ValueError("unsupported Rooted Group Steiner Tree instance format")
    num_vertices = public_instance.get("num_vertices")
    root = public_instance.get("root")
    budget = public_instance.get("budget")
    raw_edges = public_instance.get("edges")
    raw_groups = public_instance.get("groups")
    if (
        not _is_integer(num_vertices)
        or not _is_integer(root)
        or not _is_integer(budget)
        or not isinstance(raw_edges, list)
        or not isinstance(raw_groups, list)
    ):
        raise ValueError("malformed generated Rooted Group Steiner Tree fields")
    assert isinstance(num_vertices, int)
    assert isinstance(root, int)
    assert isinstance(budget, int)
    if num_vertices < 2 or not 1 <= root <= num_vertices or not 1 <= budget <= MAX_SAFE_INTEGER:
        raise ValueError("generated graph order, root, or budget is invalid")

    edges_by_id: dict[int, _Edge] = {}
    pairs: set[tuple[int, int]] = set()
    graph_adjacency: list[list[int]] = [[] for _ in range(num_vertices + 1)]
    for raw_edge in raw_edges:
        if not isinstance(raw_edge, Mapping) or set(raw_edge) != _EDGE_FIELDS:
            raise ValueError("generated weighted edge is malformed")
        edge_id = raw_edge.get("edge_id")
        first = raw_edge.get("u")
        second = raw_edge.get("v")
        weight = raw_edge.get("weight")
        if not all(_is_integer(value) for value in (edge_id, first, second, weight)):
            raise ValueError("generated weighted edge fields must be JSON integers")
        assert isinstance(edge_id, int)
        assert isinstance(first, int)
        assert isinstance(second, int)
        assert isinstance(weight, int)
        if (
            not 1 <= edge_id <= MAX_SAFE_INTEGER
            or not 1 <= first < second <= num_vertices
            or not 1 <= weight <= MAX_SAFE_INTEGER
            or edge_id in edges_by_id
            or (first, second) in pairs
        ):
            raise ValueError("generated weighted edge table is invalid")
        edges_by_id[edge_id] = _Edge(first, second, weight)
        pairs.add((first, second))
        graph_adjacency[first].append(second)
        graph_adjacency[second].append(first)
    if not edges_by_id:
        raise ValueError("generated graph must contain an edge")
    reached = {root}
    queue = deque([root])
    while queue:
        vertex = queue.popleft()
        for neighbor in graph_adjacency[vertex]:
            if neighbor not in reached:
                reached.add(neighbor)
                queue.append(neighbor)
    if len(reached) != num_vertices:
        raise ValueError("generated graph must be connected")

    group_ids: set[int] = set()
    groups: list[frozenset[int]] = []
    for raw_group in raw_groups:
        if not isinstance(raw_group, Mapping) or set(raw_group) != _GROUP_FIELDS:
            raise ValueError("generated vertex group is malformed")
        group_id = raw_group.get("group_id")
        raw_vertices = raw_group.get("vertices")
        if not _is_integer(group_id) or not isinstance(raw_vertices, list) or not raw_vertices:
            raise ValueError("generated vertex group fields are invalid")
        assert isinstance(group_id, int)
        if not 1 <= group_id <= MAX_SAFE_INTEGER or group_id in group_ids:
            raise ValueError("generated group ID is invalid or repeated")
        vertices: set[int] = set()
        for vertex in raw_vertices:
            if not _is_integer(vertex):
                raise ValueError("generated vertex group contains a non-integer")
            assert isinstance(vertex, int)
            if not 1 <= vertex <= num_vertices or vertex in vertices:
                raise ValueError("generated vertex group contains an invalid or repeated vertex")
            vertices.add(vertex)
        group_ids.add(group_id)
        groups.append(frozenset(vertices))
    if not groups:
        raise ValueError("generated instance must contain at least one group")
    return _Instance(num_vertices, edges_by_id, root, tuple(groups), budget)


def _parse_edge_ids(value: object, instance: _Instance) -> tuple[int, ...]:
    if not isinstance(value, list):
        raise _SubmissionRejected(ErrorCode.INVALID_PAYLOAD)
    result: list[int] = []
    for edge_id in value:
        if not _is_integer(edge_id) or edge_id not in instance.edges_by_id:
            raise _SubmissionRejected(GroupSteinerReason.EDGE_ID_INVALID)
        assert isinstance(edge_id, int)
        result.append(edge_id)
    if len(set(result)) != len(result):
        raise _SubmissionRejected(GroupSteinerReason.EDGE_ID_DUPLICATE)
    return tuple(result)


def _evaluate(instance: _Instance, edge_ids: tuple[int, ...]) -> EdgeSetEvaluation:
    cost = sum(instance.edges_by_id[edge_id].weight for edge_id in edge_ids)
    adjacency: dict[int, list[int]] = {}
    selected_vertices = {instance.root}
    for edge_id in edge_ids:
        edge = instance.edges_by_id[edge_id]
        selected_vertices.update((edge.first, edge.second))
        adjacency.setdefault(edge.first, []).append(edge.second)
        adjacency.setdefault(edge.second, []).append(edge.first)
    reached = {instance.root}
    queue = deque([instance.root])
    while queue:
        vertex = queue.popleft()
        for neighbor in adjacency.get(vertex, []):
            if neighbor not in reached:
                reached.add(neighbor)
                queue.append(neighbor)
    return EdgeSetEvaluation(
        cost=cost,
        connected=selected_vertices <= reached,
        groups_hit=all(group & reached for group in instance.groups),
    )


def evaluate_edge_set(public_instance: Mapping[str, Any], edge_ids: object) -> EdgeSetEvaluation:
    """Strictly parse and evaluate an edge-set certificate."""

    instance = _parse_instance(public_instance)
    parsed = _parse_edge_ids(edge_ids, instance)
    return _evaluate(instance, parsed)


def _verify_edge_set(payload: Mapping[str, Any], instance: _Instance) -> EdgeSetEvaluation:
    if set(payload) != _EDGE_SET_FIELDS:
        raise _SubmissionRejected(ErrorCode.INVALID_PAYLOAD)
    edge_ids = _parse_edge_ids(payload.get("edge_ids"), instance)
    evaluation = _evaluate(instance, edge_ids)
    if evaluation.cost > instance.budget:
        raise _SubmissionRejected(GroupSteinerReason.BUDGET_EXCEEDED)
    if not evaluation.connected:
        raise _SubmissionRejected(GroupSteinerReason.DISCONNECTED)
    if not evaluation.groups_hit:
        raise _SubmissionRejected(GroupSteinerReason.GROUP_UNHIT)
    return evaluation


class RootedGroupSteinerProtocol:
    """Pure one-shot verifier for a root-connected group-hitting edge set."""

    task_id = TASK_ID
    task_version = TASK_VERSION

    def initialize(
        self, *, generated_case: GeneratedCase, context: ArthurContext
    ) -> GroupSteinerProtocolState:
        del context
        self._validate_task_identity(generated_case)
        _parse_instance(generated_case.public_instance)
        return GroupSteinerProtocolState()

    def public_protocol_description(self, *, generated_case: GeneratedCase) -> Mapping[str, Any]:
        self._validate_task_identity(generated_case)
        instance = _parse_instance(generated_case.public_instance)
        return {
            "api_version": "aip/1",
            "mode": "one_shot",
            "initial_event_kinds": [EDGE_SET_EVENT_KIND],
            "event_schemas": {
                EDGE_SET_EVENT_KIND: {
                    "schema_ref": (
                        "tasks/tier1_np/new_rooted_group_steiner_tree/schemas/edge_set.schema.json"
                    )
                }
            },
            "public_parameters": {
                "num_vertices": instance.num_vertices,
                "num_edges": len(instance.edges_by_id),
                "num_groups": len(instance.groups),
                "budget": instance.budget,
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
        if not isinstance(state, GroupSteinerProtocolState):
            raise TypeError("state is not a GroupSteinerProtocolState")
        self._validate_task_identity(generated_case)
        if state.terminal_status is not None:
            return Transition(
                new_state=state,
                terminal_status=TerminalStatus.REJECT,
                reason_code=ErrorCode.SESSION_TERMINAL,
                public_state={"phase": "terminal"},
            )
        if event.kind != EDGE_SET_EVENT_KIND:
            return self._rejection(ErrorCode.INVALID_EVENT_KIND)
        if event.artifact_refs:
            return self._rejection(ErrorCode.INVALID_PAYLOAD)

        instance = _parse_instance(generated_case.public_instance)
        try:
            evaluation = _verify_edge_set(event.payload, instance)
        except _SubmissionRejected as rejected:
            return self._rejection(rejected.reason_code)

        accepted = GroupSteinerProtocolState(
            phase="terminal",
            terminal_status=TerminalStatus.ACCEPT,
            reason_code=ErrorCode.PROTOCOL_ACCEPT,
            events_processed=1,
        )
        return Transition(
            new_state=accepted,
            terminal_status=TerminalStatus.ACCEPT,
            reason_code=ErrorCode.PROTOCOL_ACCEPT,
            milestones={"edge_set_submitted": 1},
            public_state={
                "phase": "terminal",
                "edge_set_checked": True,
                "selected_cost": evaluation.cost,
            },
        )

    def terminal_metrics(self, *, state: Any) -> Mapping[str, int | float | str]:
        if not isinstance(state, GroupSteinerProtocolState):
            raise TypeError("state is not a GroupSteinerProtocolState")
        metrics: dict[str, int | float | str] = {
            "events_processed": state.events_processed,
            "edge_set_valid": int(state.terminal_status == TerminalStatus.ACCEPT),
        }
        if state.reason_code is not None:
            metrics["reason_code"] = state.reason_code
        return metrics

    @staticmethod
    def _validate_task_identity(generated_case: GeneratedCase) -> None:
        if generated_case.task_id != TASK_ID or generated_case.task_version != TASK_VERSION:
            raise ValueError("generated case does not belong to this task plugin")

    @staticmethod
    def _rejection(reason_code: str) -> Transition:
        rejected = GroupSteinerProtocolState(
            phase="terminal",
            terminal_status=TerminalStatus.REJECT,
            reason_code=reason_code,
            events_processed=1,
        )
        return Transition(
            new_state=rejected,
            terminal_status=TerminalStatus.REJECT,
            reason_code=reason_code,
            milestones={"edge_set_submitted": 1},
            public_state={"phase": "terminal", "edge_set_checked": False},
        )


def _participant_instance(client: ParticipantClient) -> Mapping[str, Any]:
    response = client.get_instance()
    nested = response.get("public_instance")
    return nested if isinstance(nested, Mapping) else response


class EmptyEdgeSetAgent:
    agent_id = "virtual-empty-edge-set"

    def run(self, *, client: ParticipantClient, workspace: Path) -> None:
        del workspace
        _participant_instance(client)
        client.submit_event(
            sequence=0,
            kind=EDGE_SET_EVENT_KIND,
            payload={"edge_ids": []},
        )


class InvalidEdgeIdAgent:
    agent_id = "virtual-invalid-edge-id"

    def run(self, *, client: ParticipantClient, workspace: Path) -> None:
        del workspace
        _participant_instance(client)
        client.submit_event(
            sequence=0,
            kind=EDGE_SET_EVENT_KIND,
            payload={"edge_ids": [0]},
        )


_VIRTUAL_AGENT_LIST: Final[tuple[VirtualAgent, ...]] = (
    EmptyEdgeSetAgent(),
    InvalidEdgeIdAgent(),
)

VIRTUAL_AGENTS: Final[Mapping[str, VirtualAgent]] = {
    agent.agent_id: agent for agent in _VIRTUAL_AGENT_LIST
}
