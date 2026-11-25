"""Shared primitives used by the current Merlin-Bench tasks."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Final, TypeGuard

MAX_VERTICES: Final = 4096

MAX_EDGES: Final = MAX_VERTICES * (MAX_VERTICES - 1) // 2


def is_strict_integer(value: object) -> TypeGuard[int]:
    return isinstance(value, int) and not isinstance(value, bool)


class DeterministicStream:
    """Domain-separated deterministic stream for instance generation only."""

    _DOMAIN: Final = b"aipbench/hamiltonicity-bind-open/generator/v1\x00"

    def __init__(self, seed: bytes) -> None:
        self._seed = bytes(seed)
        self._counter = 0
        self._buffer = bytearray()

    def _refill(self) -> None:
        self._buffer.extend(
            hashlib.sha256(
                self._DOMAIN
                + len(self._seed).to_bytes(8, "big")
                + self._seed
                + self._counter.to_bytes(16, "big")
            ).digest()
        )
        self._counter += 1

    def take(self, length: int) -> bytes:
        if length < 0:
            raise ValueError("length must be nonnegative")
        while len(self._buffer) < length:
            self._refill()
        result = bytes(self._buffer[:length])
        del self._buffer[:length]
        return result

    def randbelow(self, upper_exclusive: int) -> int:
        if upper_exclusive <= 0:
            raise ValueError("upper_exclusive must be positive")
        width = max(1, (upper_exclusive.bit_length() + 7) // 8)
        sample_space = 1 << (8 * width)
        limit = sample_space - sample_space % upper_exclusive
        while True:
            candidate = int.from_bytes(self.take(width), "big")
            if candidate < limit:
                return candidate % upper_exclusive

    def shuffle(self, values: list[Any]) -> None:
        for index in range(len(values) - 1, 0, -1):
            other = self.randbelow(index + 1)
            values[index], values[other] = values[other], values[index]


def integer_parameter(
    parameters: Mapping[str, Any], name: str, *, minimum: int = 0, maximum: int | None = None
) -> int:
    value = parameters.get(name)
    if not is_strict_integer(value) or value < minimum:
        raise ValueError(f"case parameter {name!r} must be an integer >= {minimum}")
    if maximum is not None and value > maximum:
        raise ValueError(f"case parameter {name!r} must be at most {maximum}")
    return value


def normalized_edges(
    num_vertices: int, pairs: Sequence[tuple[int, int]] | set[tuple[int, int]]
) -> tuple[tuple[int, int], ...]:
    edges: set[tuple[int, int]] = set()
    for first, second in pairs:
        if not 0 <= first < num_vertices or not 0 <= second < num_vertices or first == second:
            raise ValueError("logical edge endpoints must be distinct in-range vertices")
        edges.add((min(first, second), max(first, second)))
    return tuple(sorted(edges))


@dataclass(frozen=True)
class LogicalGraph:
    num_vertices: int
    edges: tuple[tuple[int, int], ...]


def validate_graph(graph: LogicalGraph) -> None:
    if (
        not is_strict_integer(graph.num_vertices)
        or not 3 <= graph.num_vertices <= MAX_VERTICES
        or len(graph.edges) > MAX_EDGES
    ):
        raise ValueError("graph order or size is outside the correctness-scaled envelope")
    previous: tuple[int, int] | None = None
    for edge in graph.edges:
        if (
            not isinstance(edge, tuple)
            or len(edge) != 2
            or not is_strict_integer(edge[0])
            or not is_strict_integer(edge[1])
            or not 0 <= edge[0] < edge[1] < graph.num_vertices
        ):
            raise ValueError("graph contains a malformed edge")
        if previous is not None and edge <= previous:
            raise ValueError("graph edges must be strictly sorted and unique")
        previous = edge


def parse_public_graph(raw: object) -> LogicalGraph:
    if not isinstance(raw, Mapping) or set(raw) != {"num_vertices", "edges"}:
        raise ValueError("graph must contain exactly num_vertices and edges")
    num_vertices = raw.get("num_vertices")
    raw_edges = raw.get("edges")
    if not is_strict_integer(num_vertices) or not 3 <= num_vertices <= MAX_VERTICES:
        raise ValueError("num_vertices is outside the correctness-scaled envelope")
    if not isinstance(raw_edges, list) or len(raw_edges) > MAX_EDGES:
        raise ValueError("edges must be an array inside the edge envelope")
    edges: list[tuple[int, int]] = []
    previous: tuple[int, int] | None = None
    for raw_edge in raw_edges:
        if not isinstance(raw_edge, list) or len(raw_edge) != 2:
            raise ValueError("every edge must be a two-element array")
        first, second = raw_edge
        if (
            not is_strict_integer(first)
            or not is_strict_integer(second)
            or not 0 <= first < second < num_vertices
        ):
            raise ValueError("every edge must satisfy 0 <= u < v < num_vertices")
        edge = (first, second)
        if previous is not None and edge <= previous:
            raise ValueError("edge array must be strictly lexicographically sorted")
        edges.append(edge)
        previous = edge
    graph = LogicalGraph(num_vertices, tuple(edges))
    validate_graph(graph)
    return graph


def relabel_graph(graph: LogicalGraph, permutation: Sequence[int]) -> LogicalGraph:
    validate_graph(graph)
    if (
        len(permutation) != graph.num_vertices
        or any(not is_strict_integer(vertex) for vertex in permutation)
        or set(permutation) != set(range(graph.num_vertices))
    ):
        raise ValueError("permutation must be a bijection of the vertex set")
    return LogicalGraph(
        graph.num_vertices,
        normalized_edges(
            graph.num_vertices,
            [(permutation[first], permutation[second]) for first, second in graph.edges],
        ),
    )


def adjacency(graph: LogicalGraph) -> tuple[set[int], ...]:
    validate_graph(graph)
    result: tuple[set[int], ...] = tuple(set() for _ in range(graph.num_vertices))
    for first, second in graph.edges:
        result[first].add(second)
        result[second].add(first)
    return result


def validate_hamilton_cycle(graph: LogicalGraph, cycle: Sequence[int]) -> None:
    validate_graph(graph)
    if (
        len(cycle) != graph.num_vertices
        or any(not is_strict_integer(vertex) for vertex in cycle)
        or set(cycle) != set(range(graph.num_vertices))
    ):
        raise ValueError("Hamilton cycle must be a permutation of every vertex")
    edge_set = set(graph.edges)
    for index, first in enumerate(cycle):
        second = cycle[(index + 1) % len(cycle)]
        if (min(first, second), max(first, second)) not in edge_set:
            raise ValueError("Hamilton cycle uses a non-edge")


@dataclass(frozen=True)
class GraphBlueprint:
    graph: LogicalGraph
    cycle: tuple[int, ...]
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class FinalizedCase:
    public_instance: Mapping[str, Any]
    private_instance: Mapping[str, Any]
    generation_metadata: Mapping[str, Any]


def finalize_blueprint(
    *, case_id: str, blueprint: GraphBlueprint, stream: DeterministicStream
) -> FinalizedCase:
    validate_graph(blueprint.graph)
    validate_hamilton_cycle(blueprint.graph, blueprint.cycle)
    permutation = list(range(blueprint.graph.num_vertices))
    stream.shuffle(permutation)
    public_graph = relabel_graph(blueprint.graph, permutation)
    public_cycle = tuple(permutation[vertex] for vertex in blueprint.cycle)
    validate_hamilton_cycle(public_graph, public_cycle)
    public_instance: Mapping[str, Any] = {
        "format_version": "aip-hamiltonicity/1",
        "graph_model": "undirected_simple",
        "num_vertices": public_graph.num_vertices,
        "edges": [[first, second] for first, second in public_graph.edges],
        "challenge_lanes": 24,
    }
    metadata: Mapping[str, Any] = {
        "generator": f"hamiltonicity_bind_open/{case_id}/v1",
        "case_id": case_id,
        "num_vertices": public_graph.num_vertices,
        "num_edges": len(public_graph.edges),
        **dict(blueprint.metadata),
    }
    return FinalizedCase(public_instance, {}, metadata)
