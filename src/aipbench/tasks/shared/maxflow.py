"""Shared primitives used by the current Merlin-Bench tasks."""

from __future__ import annotations

from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from aipbench.core.errors import ErrorCode
from aipbench.core.models import GeneratedCase, ParticipantEvent, TerminalStatus, Transition
from aipbench.core.protocol import ArthurContext, ParticipantClient, VirtualAgent

TASK_ID: Final = "t1.new_maxflow_min_cut"

TASK_VERSION: Final = "0.1.0"

CERTIFICATE_EVENT_KIND: Final = "maxflow.certificate"

_CERTIFICATE_FIELDS: Final = frozenset({"flow_value", "edge_flows", "source_side_cut"})

_EDGE_FLOW_FIELDS: Final = frozenset({"edge_id", "flow"})


class MaxFlowReason:
    """Stable, participant-safe reason codes for certificate rejection."""

    EDGE_SET_MISMATCH = "MAXFLOW_EDGE_SET_MISMATCH"
    CAPACITY_VIOLATION = "MAXFLOW_CAPACITY_VIOLATION"
    CONSERVATION_VIOLATION = "MAXFLOW_CONSERVATION_VIOLATION"
    VALUE_MISMATCH = "MAXFLOW_VALUE_MISMATCH"
    CUT_INVALID = "MAXFLOW_CUT_INVALID"
    CUT_CAPACITY_MISMATCH = "MAXFLOW_CUT_CAPACITY_MISMATCH"
    PRIMAL_DUAL_MISMATCH = CUT_CAPACITY_MISMATCH


@dataclass(frozen=True)
class MaxFlowProtocolState:
    phase: str = "awaiting_certificate"
    terminal_status: TerminalStatus | None = None
    reason_code: str | None = None
    flow_value: int | None = None
    events_processed: int = 0


@dataclass(frozen=True)
class _GraphEdge:
    edge_id: int
    tail: int
    head: int
    capacity: int


@dataclass(frozen=True)
class _Graph:
    num_vertices: int
    source: int
    sink: int
    edges: tuple[_GraphEdge, ...]


class _CertificateRejected(Exception):
    def __init__(self, reason_code: str) -> None:
        super().__init__(reason_code)
        self.reason_code = reason_code


def _is_integer(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _parse_graph(public_instance: Mapping[str, Any]) -> _Graph:
    if (
        public_instance.get("format_version") != "aip-maxflow-instance/1"
        or public_instance.get("directed") is not True
    ):
        raise ValueError("unsupported max-flow instance format")
    num_vertices = public_instance.get("num_vertices")
    source = public_instance.get("source")
    sink = public_instance.get("sink")
    raw_edges = public_instance.get("edges")
    if (
        not _is_integer(num_vertices)
        or not _is_integer(source)
        or not _is_integer(sink)
        or not isinstance(raw_edges, list)
    ):
        raise ValueError("malformed generated max-flow instance")
    assert isinstance(num_vertices, int)
    assert isinstance(source, int)
    assert isinstance(sink, int)
    if num_vertices < 2 or source == sink:
        raise ValueError("invalid generated max-flow vertices")
    if source not in range(num_vertices) or sink not in range(num_vertices):
        raise ValueError("source or sink is outside the vertex range")

    edges: list[_GraphEdge] = []
    seen_ids: set[int] = set()
    for raw_edge in raw_edges:
        if not isinstance(raw_edge, Mapping):
            raise ValueError("malformed generated max-flow edge")
        edge_id = raw_edge.get("edge_id")
        tail = raw_edge.get("tail")
        head = raw_edge.get("head")
        capacity = raw_edge.get("capacity")
        if not all(_is_integer(value) for value in (edge_id, tail, head, capacity)):
            raise ValueError("max-flow edge fields must be integers")
        assert isinstance(edge_id, int)
        assert isinstance(tail, int)
        assert isinstance(head, int)
        assert isinstance(capacity, int)
        if (
            edge_id < 0
            or edge_id in seen_ids
            or tail not in range(num_vertices)
            or head not in range(num_vertices)
            or tail == head
            or capacity < 0
        ):
            raise ValueError("invalid generated max-flow edge")
        seen_ids.add(edge_id)
        edges.append(_GraphEdge(edge_id, tail, head, capacity))
    return _Graph(num_vertices, source, sink, tuple(edges))


def _parse_certificate(
    payload: Mapping[str, Any], graph: _Graph
) -> tuple[int, dict[int, int], set[int]]:
    if set(payload) != _CERTIFICATE_FIELDS:
        raise _CertificateRejected(ErrorCode.INVALID_PAYLOAD)
    flow_value = payload.get("flow_value")
    raw_edge_flows = payload.get("edge_flows")
    raw_cut = payload.get("source_side_cut")
    if (
        not _is_integer(flow_value)
        or not isinstance(raw_edge_flows, list)
        or not isinstance(raw_cut, list)
    ):
        raise _CertificateRejected(ErrorCode.INVALID_PAYLOAD)
    assert isinstance(flow_value, int)
    if flow_value < 0:
        raise _CertificateRejected(ErrorCode.INVALID_PAYLOAD)

    edge_flows: dict[int, int] = {}
    for raw_edge_flow in raw_edge_flows:
        if not isinstance(raw_edge_flow, Mapping) or set(raw_edge_flow) != _EDGE_FLOW_FIELDS:
            raise _CertificateRejected(ErrorCode.INVALID_PAYLOAD)
        edge_id = raw_edge_flow.get("edge_id")
        flow = raw_edge_flow.get("flow")
        if not _is_integer(edge_id) or not _is_integer(flow):
            raise _CertificateRejected(ErrorCode.INVALID_PAYLOAD)
        assert isinstance(edge_id, int)
        assert isinstance(flow, int)
        if edge_id in edge_flows:
            raise _CertificateRejected(MaxFlowReason.EDGE_SET_MISMATCH)
        edge_flows[edge_id] = flow

    expected_edge_ids = {edge.edge_id for edge in graph.edges}
    if set(edge_flows) != expected_edge_ids:
        raise _CertificateRejected(MaxFlowReason.EDGE_SET_MISMATCH)

    cut_vertices: set[int] = set()
    for vertex in raw_cut:
        if not _is_integer(vertex):
            raise _CertificateRejected(ErrorCode.INVALID_PAYLOAD)
        assert isinstance(vertex, int)
        if vertex in cut_vertices:
            raise _CertificateRejected(MaxFlowReason.CUT_INVALID)
        cut_vertices.add(vertex)
    if any(vertex not in range(graph.num_vertices) for vertex in cut_vertices):
        raise _CertificateRejected(MaxFlowReason.CUT_INVALID)
    return flow_value, edge_flows, cut_vertices


def _verify_certificate(payload: Mapping[str, Any], graph: _Graph) -> int:
    flow_value, edge_flows, cut_vertices = _parse_certificate(payload, graph)

    balances = [0] * graph.num_vertices
    for edge in graph.edges:
        flow = edge_flows[edge.edge_id]
        if flow < 0 or flow > edge.capacity:
            raise _CertificateRejected(MaxFlowReason.CAPACITY_VIOLATION)
        balances[edge.tail] += flow
        balances[edge.head] -= flow

    for vertex, balance in enumerate(balances):
        if vertex not in (graph.source, graph.sink) and balance != 0:
            raise _CertificateRejected(MaxFlowReason.CONSERVATION_VIOLATION)
    if balances[graph.source] != flow_value or balances[graph.sink] != -flow_value:
        raise _CertificateRejected(MaxFlowReason.VALUE_MISMATCH)

    if graph.source not in cut_vertices or graph.sink in cut_vertices:
        raise _CertificateRejected(MaxFlowReason.CUT_INVALID)
    cut_capacity = sum(
        edge.capacity
        for edge in graph.edges
        if edge.tail in cut_vertices and edge.head not in cut_vertices
    )
    if cut_capacity != flow_value:
        raise _CertificateRejected(MaxFlowReason.CUT_CAPACITY_MISMATCH)
    return flow_value


class MaxFlowProtocol:
    """Pure one-shot verifier for a primal flow and dual source-side cut."""

    task_id = TASK_ID
    task_version = TASK_VERSION

    def initialize(
        self, *, generated_case: GeneratedCase, context: ArthurContext
    ) -> MaxFlowProtocolState:
        del context
        self._validate_task_identity(generated_case)
        _parse_graph(generated_case.public_instance)
        return MaxFlowProtocolState()

    def public_protocol_description(self, *, generated_case: GeneratedCase) -> Mapping[str, Any]:
        self._validate_task_identity(generated_case)
        graph = _parse_graph(generated_case.public_instance)
        return {
            "api_version": "aip/1",
            "mode": "one_shot",
            "initial_event_kinds": [CERTIFICATE_EVENT_KIND],
            "event_schemas": {
                CERTIFICATE_EVENT_KIND: {
                    "schema_ref": (
                        "tasks/tier1_np/new_maxflow_min_cut/schemas/certificate.schema.json"
                    )
                }
            },
            "public_parameters": {
                "directed": True,
                "integral_capacities": True,
                "num_vertices": graph.num_vertices,
                "num_edges": len(graph.edges),
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
        if not isinstance(state, MaxFlowProtocolState):
            raise TypeError("state is not a MaxFlowProtocolState")
        self._validate_task_identity(generated_case)
        if state.terminal_status is not None:
            return Transition(
                new_state=state,
                terminal_status=TerminalStatus.REJECT,
                reason_code=ErrorCode.SESSION_TERMINAL,
                public_state={"phase": "terminal"},
            )
        if event.kind != CERTIFICATE_EVENT_KIND:
            return self._rejection(ErrorCode.INVALID_EVENT_KIND)
        if event.artifact_refs:
            return self._rejection(ErrorCode.INVALID_PAYLOAD)

        graph = _parse_graph(generated_case.public_instance)
        try:
            flow_value = _verify_certificate(event.payload, graph)
        except _CertificateRejected as rejected:
            return self._rejection(rejected.reason_code)

        accepted_state = MaxFlowProtocolState(
            phase="terminal",
            terminal_status=TerminalStatus.ACCEPT,
            reason_code=ErrorCode.PROTOCOL_ACCEPT,
            flow_value=flow_value,
            events_processed=1,
        )
        return Transition(
            new_state=accepted_state,
            terminal_status=TerminalStatus.ACCEPT,
            reason_code=ErrorCode.PROTOCOL_ACCEPT,
            milestones={"certificate_submitted": 1, "flow_value": flow_value},
            public_state={"phase": "terminal", "certificate_checked": True},
        )

    def terminal_metrics(self, *, state: Any) -> Mapping[str, int | float | str]:
        if not isinstance(state, MaxFlowProtocolState):
            raise TypeError("state is not a MaxFlowProtocolState")
        metrics: dict[str, int | float | str] = {
            "events_processed": state.events_processed,
            "certificate_valid": int(state.terminal_status == TerminalStatus.ACCEPT),
        }
        if state.flow_value is not None:
            metrics["flow_value"] = state.flow_value
        if state.reason_code is not None:
            metrics["reason_code"] = state.reason_code
        return metrics

    @staticmethod
    def _validate_task_identity(generated_case: GeneratedCase) -> None:
        if generated_case.task_id != TASK_ID or generated_case.task_version != TASK_VERSION:
            raise ValueError("generated case does not belong to this task plugin")

    @staticmethod
    def _rejection(reason_code: str) -> Transition:
        rejected_state = MaxFlowProtocolState(
            phase="terminal",
            terminal_status=TerminalStatus.REJECT,
            reason_code=reason_code,
            events_processed=1,
        )
        return Transition(
            new_state=rejected_state,
            terminal_status=TerminalStatus.REJECT,
            reason_code=reason_code,
            milestones={"certificate_submitted": 1},
            public_state={"phase": "terminal", "certificate_checked": False},
        )


class _ResidualEdge:
    def __init__(
        self,
        *,
        destination: int,
        reverse_index: int,
        residual_capacity: int,
        original_capacity: int,
        edge_id: int | None,
    ) -> None:
        self.destination = destination
        self.reverse_index = reverse_index
        self.residual_capacity = residual_capacity
        self.original_capacity = original_capacity
        self.edge_id = edge_id


def _send_dinic_flow(
    *,
    adjacency: list[list[_ResidualEdge]],
    levels: list[int],
    edge_cursors: list[int],
    source: int,
    sink: int,
    available: int,
) -> int:
    """Find and augment one admissible level-graph path without recursion."""

    vertices = [source]
    path_edges: list[tuple[int, int]] = []
    path_capacities = [available]
    while vertices:
        vertex = vertices[-1]
        if vertex == sink:
            sent = path_capacities[-1]
            for tail, edge_index in path_edges:
                residual_edge = adjacency[tail][edge_index]
                residual_edge.residual_capacity -= sent
                reverse_edge = adjacency[residual_edge.destination][residual_edge.reverse_index]
                reverse_edge.residual_capacity += sent
            return sent

        advanced = False
        while edge_cursors[vertex] < len(adjacency[vertex]):
            edge_index = edge_cursors[vertex]
            residual_edge = adjacency[vertex][edge_index]
            if (
                residual_edge.residual_capacity > 0
                and levels[residual_edge.destination] == levels[vertex] + 1
            ):
                path_edges.append((vertex, edge_index))
                vertices.append(residual_edge.destination)
                path_capacities.append(min(path_capacities[-1], residual_edge.residual_capacity))
                advanced = True
                break
            edge_cursors[vertex] += 1
        if advanced:
            continue

        vertices.pop()
        path_capacities.pop()
        if path_edges:
            parent, used_edge_index = path_edges.pop()
            if edge_cursors[parent] == used_edge_index:
                edge_cursors[parent] += 1
    return 0


def solve_maxflow(public_instance: Mapping[str, Any]) -> Mapping[str, Any]:
    """Return an exact max-flow/min-cut certificate for a public instance."""

    graph = _parse_graph(public_instance)
    adjacency: list[list[_ResidualEdge]] = [[] for _ in range(graph.num_vertices)]
    original_locations: dict[int, tuple[int, int]] = {}

    def add_residual_pair(edge: _GraphEdge) -> None:
        forward_index = len(adjacency[edge.tail])
        reverse_index = len(adjacency[edge.head])
        adjacency[edge.tail].append(
            _ResidualEdge(
                destination=edge.head,
                reverse_index=reverse_index,
                residual_capacity=edge.capacity,
                original_capacity=edge.capacity,
                edge_id=edge.edge_id,
            )
        )
        adjacency[edge.head].append(
            _ResidualEdge(
                destination=edge.tail,
                reverse_index=forward_index,
                residual_capacity=0,
                original_capacity=0,
                edge_id=None,
            )
        )
        original_locations[edge.edge_id] = (edge.tail, forward_index)

    for graph_edge in graph.edges:
        add_residual_pair(graph_edge)

    flow_value = 0
    source_capacity = sum(edge.capacity for edge in graph.edges if edge.tail == graph.source)
    while True:
        levels = [-1] * graph.num_vertices
        levels[graph.source] = 0
        queue: deque[int] = deque([graph.source])
        while queue:
            vertex = queue.popleft()
            for residual_edge in adjacency[vertex]:
                if residual_edge.residual_capacity > 0 and levels[residual_edge.destination] < 0:
                    levels[residual_edge.destination] = levels[vertex] + 1
                    queue.append(residual_edge.destination)
        if levels[graph.sink] < 0:
            break

        edge_cursors = [0] * graph.num_vertices

        while True:
            augmentation = _send_dinic_flow(
                adjacency=adjacency,
                levels=levels,
                edge_cursors=edge_cursors,
                source=graph.source,
                sink=graph.sink,
                available=source_capacity,
            )
            if augmentation == 0:
                break
            flow_value += augmentation

    reachable = {graph.source}
    queue = deque([graph.source])
    while queue:
        vertex = queue.popleft()
        for residual_edge in adjacency[vertex]:
            if residual_edge.residual_capacity > 0 and residual_edge.destination not in reachable:
                reachable.add(residual_edge.destination)
                queue.append(residual_edge.destination)

    edge_flows: list[Mapping[str, int]] = []
    for graph_edge in graph.edges:
        tail, edge_index = original_locations[graph_edge.edge_id]
        residual_edge = adjacency[tail][edge_index]
        edge_flows.append(
            {
                "edge_id": graph_edge.edge_id,
                "flow": residual_edge.original_capacity - residual_edge.residual_capacity,
            }
        )
    return {
        "flow_value": flow_value,
        "edge_flows": edge_flows,
        "source_side_cut": sorted(reachable),
    }


def _participant_instance(client: ParticipantClient) -> Mapping[str, Any]:
    response = client.get_instance()
    nested = response.get("public_instance")
    if isinstance(nested, Mapping):
        return nested
    return response


def _mutable_certificate(certificate: Mapping[str, Any]) -> dict[str, Any]:
    raw_edge_flows = certificate["edge_flows"]
    raw_cut = certificate["source_side_cut"]
    assert isinstance(raw_edge_flows, list)
    assert isinstance(raw_cut, list)
    return {
        "flow_value": certificate["flow_value"],
        "edge_flows": [dict(edge_flow) for edge_flow in raw_edge_flows],
        "source_side_cut": list(raw_cut),
    }


class HonestMaxFlowAgent:
    agent_id = "virtual-honest"

    def run(self, *, client: ParticipantClient, workspace: Path) -> None:
        del workspace
        certificate = solve_maxflow(_participant_instance(client))
        client.submit_event(
            sequence=0,
            kind=CERTIFICATE_EVENT_KIND,
            payload=certificate,
        )


class WrongFlowMaxFlowAgent:
    agent_id = "virtual-wrong-flow"

    def run(self, *, client: ParticipantClient, workspace: Path) -> None:
        del workspace
        instance = _participant_instance(client)
        certificate = _mutable_certificate(solve_maxflow(instance))
        graph = _parse_graph(instance)
        capacities = {edge.edge_id: edge.capacity for edge in graph.edges}
        edge_flows = certificate["edge_flows"]
        assert isinstance(edge_flows, list)
        saturated = next(
            edge_flow
            for edge_flow in edge_flows
            if edge_flow["flow"] == capacities[edge_flow["edge_id"]]
        )
        saturated["flow"] += 1
        client.submit_event(
            sequence=0,
            kind=CERTIFICATE_EVENT_KIND,
            payload=certificate,
        )


class WrongConservationMaxFlowAgent:
    agent_id = "virtual-wrong-conservation"

    def run(self, *, client: ParticipantClient, workspace: Path) -> None:
        del workspace
        instance = _participant_instance(client)
        certificate = _mutable_certificate(solve_maxflow(instance))
        graph = _parse_graph(instance)
        edges_by_id = {edge.edge_id: edge for edge in graph.edges}
        edge_flows = certificate["edge_flows"]
        assert isinstance(edge_flows, list)
        internal_unsaturated = next(
            edge_flow
            for edge_flow in edge_flows
            if edges_by_id[edge_flow["edge_id"]].tail not in (graph.source, graph.sink)
            and edges_by_id[edge_flow["edge_id"]].head not in (graph.source, graph.sink)
            and edge_flow["flow"] < edges_by_id[edge_flow["edge_id"]].capacity
        )
        internal_unsaturated["flow"] += 1
        client.submit_event(
            sequence=0,
            kind=CERTIFICATE_EVENT_KIND,
            payload=certificate,
        )


class WrongCutMaxFlowAgent:
    agent_id = "virtual-wrong-cut"

    def run(self, *, client: ParticipantClient, workspace: Path) -> None:
        del workspace
        instance = _participant_instance(client)
        certificate = _mutable_certificate(solve_maxflow(instance))
        graph = _parse_graph(instance)
        cut = certificate["source_side_cut"]
        assert isinstance(cut, list)
        cut.append(graph.sink)
        client.submit_event(
            sequence=0,
            kind=CERTIFICATE_EVENT_KIND,
            payload=certificate,
        )


_VIRTUAL_AGENT_LIST: Final[tuple[VirtualAgent, ...]] = (
    HonestMaxFlowAgent(),
    WrongFlowMaxFlowAgent(),
    WrongConservationMaxFlowAgent(),
    WrongCutMaxFlowAgent(),
)

VIRTUAL_AGENTS: Final[Mapping[str, VirtualAgent]] = {
    agent.agent_id: agent for agent in _VIRTUAL_AGENT_LIST
}
