"""Shared construction primitives for the new GNI benchmark."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Final

from aipbench.tasks.shared.graph_non_isomorphism_cases.common import (
    DeterministicStream,
    FinalizedCase,
    LogicalGraph,
    PairBlueprint,
    normalized_edges,
    parse_public_graph,
    relabel_graph,
    serialize_graph,
)


class NewDeterministicStream(DeterministicStream):
    """A task-specific deterministic stream domain."""

    _DOMAIN: Final = b"aipbench/new-graph-non-isomorphism/generator/v1\x00"


def _validate_graph(graph: LogicalGraph) -> None:
    if graph.num_vertices < 1 or len(graph.colors) != graph.num_vertices:
        raise ValueError("invalid logical graph order or color vector")
    if any(
        isinstance(color, bool) or not isinstance(color, int) or color < 0 for color in graph.colors
    ):
        raise ValueError("invalid logical graph color")
    previous: tuple[int, int] | None = None
    for edge in graph.edges:
        if not 0 <= edge[0] < edge[1] < graph.num_vertices:
            raise ValueError("invalid logical graph edge")
        if previous is not None and edge <= previous:
            raise ValueError("logical graph edges must be strictly sorted")
        previous = edge


def adjacency(graph: LogicalGraph) -> tuple[set[int], ...]:
    result = tuple(set() for _ in range(graph.num_vertices))
    for first, second in graph.edges:
        result[first].add(second)
        result[second].add(first)
    return result


def cycle_graph(length: int) -> LogicalGraph:
    if length < 3:
        raise ValueError("a cycle needs at least three vertices")
    edges = {
        (min(vertex, (vertex + 1) % length), max(vertex, (vertex + 1) % length))
        for vertex in range(length)
    }
    return LogicalGraph(length, (0,) * length, normalized_edges(edges))


def cartesian_product(first: LogicalGraph, second: LogicalGraph) -> LogicalGraph:
    """Return the Cartesian product, with pair ``(u,v)`` encoded row-major."""

    _validate_graph(first)
    _validate_graph(second)
    right_order = second.num_vertices
    edges: set[tuple[int, int]] = set()
    for left, right in first.edges:
        for other in range(right_order):
            a = left * right_order + other
            b = right * right_order + other
            edges.add((min(a, b), max(a, b)))
    for left, right in second.edges:
        for other in range(first.num_vertices):
            a = other * right_order + left
            b = other * right_order + right
            edges.add((min(a, b), max(a, b)))
    colors = tuple(
        first.colors[left] * (max(second.colors) + 1) + second.colors[right]
        for left in range(first.num_vertices)
        for right in range(second.num_vertices)
    )
    return LogicalGraph(first.num_vertices * second.num_vertices, colors, normalized_edges(edges))


def subdivision_graph(graph: LogicalGraph) -> LogicalGraph:
    """Subdivide every edge exactly once."""

    _validate_graph(graph)
    edges: set[tuple[int, int]] = set()
    for edge_id, (first, second) in enumerate(graph.edges):
        middle = graph.num_vertices + edge_id
        edges.add((first, middle))
        edges.add((second, middle))
    return LogicalGraph(
        graph.num_vertices + len(graph.edges),
        (0,) * (graph.num_vertices + len(graph.edges)),
        normalized_edges(edges),
    )


def finalize_blueprint(
    *, case_id: str, blueprint: PairBlueprint, stream: NewDeterministicStream
) -> FinalizedCase:
    """Relabel and serialize without requiring a cheap public fingerprint."""

    _validate_graph(blueprint.graph0)
    _validate_graph(blueprint.graph1)
    if blueprint.graph0.num_vertices != blueprint.graph1.num_vertices:
        raise ValueError("new GNI source graphs must have the same order")
    if len(blueprint.graph0.edges) != len(blueprint.graph1.edges):
        raise ValueError("new GNI source graphs must have the same edge count")
    if Counter(blueprint.graph0.colors) != Counter(blueprint.graph1.colors):
        raise ValueError("new GNI source graphs must have equal color-class sizes")

    hidden: list[LogicalGraph] = []
    for graph in (blueprint.graph0, blueprint.graph1):
        permutation = list(range(graph.num_vertices))
        stream.shuffle(permutation)
        hidden.append(relabel_graph(graph, permutation))

    logical_colors = sorted(set(hidden[0].colors) | set(hidden[1].colors))
    public_colors = list(range(len(logical_colors)))
    stream.shuffle(public_colors)
    color_map = dict(zip(logical_colors, public_colors, strict=True))
    hidden = [
        LogicalGraph(
            graph.num_vertices,
            tuple(color_map[color] for color in graph.colors),
            graph.edges,
        )
        for graph in hidden
    ]
    if stream.randbelow(2):
        hidden.reverse()

    public_instance: Mapping[str, Any] = {
        "format_version": "aip-gni-instance/1",
        "graph_model": "undirected_simple_vertex_colored",
        "challenge_lanes": 24,
        "graphs": [serialize_graph(graph) for graph in hidden],
    }
    for graph in public_instance["graphs"]:
        parse_public_graph(graph)
    return FinalizedCase(
        public_instance=public_instance,
        private_instance={},
        generation_metadata={
            "generator": f"new_graph_non_isomorphism/{case_id}/v1",
            "case_id": case_id,
            "num_vertices": hidden[0].num_vertices,
            "num_edges": len(hidden[0].edges),
            **dict(blueprint.metadata),
        },
    )


@dataclass(frozen=True)
class CaseDefinition:
    case_id: str
    parameters: Mapping[str, Any]
    builder: Any


__all__ = [
    "CaseDefinition",
    "LogicalGraph",
    "NewDeterministicStream",
    "PairBlueprint",
    "adjacency",
    "cartesian_product",
    "cycle_graph",
    "finalize_blueprint",
    "subdivision_graph",
]
