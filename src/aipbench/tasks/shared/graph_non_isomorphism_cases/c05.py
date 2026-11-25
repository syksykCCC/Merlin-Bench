"""Shared primitives used by the current Merlin-Bench tasks."""

from __future__ import annotations

from collections import deque

from aipbench.tasks.shared.graph_non_isomorphism_cases.common import (
    DeterministicStream,
    LogicalGraph,
    normalized_edges,
)


def _perfect_matchings(values: tuple[int, ...]) -> list[tuple[tuple[int, int], ...]]:
    if not values:
        return [()]
    first = values[0]
    result: list[tuple[tuple[int, int], ...]] = []
    for index in range(1, len(values)):
        second = values[index]
        remaining = values[1:index] + values[index + 1 :]
        for suffix in _perfect_matchings(remaining):
            result.append(tuple(sorted(((first, second), *suffix))))
    return sorted(set(result))


def _gq_incidence_graph() -> LogicalGraph:
    duads = [(first, second) for first in range(6) for second in range(first + 1, 6)]
    synthemes = _perfect_matchings(tuple(range(6)))
    duad_id = {duad: index for index, duad in enumerate(duads)}
    edges = {
        (duad_id[duad], len(duads) + syntheme_id)
        for syntheme_id, syntheme in enumerate(synthemes)
        for duad in syntheme
    }
    return LogicalGraph(30, (0,) * 30, tuple(sorted(edges)))


def _adjacency(graph: LogicalGraph) -> list[set[int]]:
    adjacency: list[set[int]] = [set() for _ in range(graph.num_vertices)]
    for first, second in graph.edges:
        adjacency[first].add(second)
        adjacency[second].add(first)
    return adjacency


def _spanning_tree_edges(graph: LogicalGraph) -> set[tuple[int, int]]:
    adjacency = _adjacency(graph)
    seen = {0}
    queue = deque([0])
    tree: set[tuple[int, int]] = set()
    while queue:
        vertex = queue.popleft()
        for neighbor in sorted(adjacency[vertex]):
            if neighbor not in seen:
                seen.add(neighbor)
                queue.append(neighbor)
                tree.add((min(vertex, neighbor), max(vertex, neighbor)))
    if len(seen) != graph.num_vertices:
        raise AssertionError("the GQ(2,2) incidence graph must be connected")
    return tree


def _cyclic_lift(base: LogicalGraph, factor: int, stream: DeterministicStream) -> LogicalGraph:
    tree_edges = _spanning_tree_edges(base)
    non_tree_edges = [edge for edge in base.edges if edge not in tree_edges]
    if not non_tree_edges:
        raise AssertionError("the GQ(2,2) base unexpectedly is a tree")
    distinguished = non_tree_edges[stream.randbelow(len(non_tree_edges))]
    voltages: dict[tuple[int, int], int] = {}
    for edge in base.edges:
        if edge in tree_edges:
            voltages[edge] = 0
        elif edge == distinguished:
            voltages[edge] = 1
        else:
            voltages[edge] = stream.randbelow(factor)
    edges: set[tuple[int, int]] = set()
    for (first, second), voltage in voltages.items():
        for layer in range(factor):
            lifted_first = factor * first + layer
            lifted_second = factor * second + (layer + voltage) % factor
            edges.add((min(lifted_first, lifted_second), max(lifted_first, lifted_second)))
    return LogicalGraph(
        base.num_vertices * factor,
        (0,) * (base.num_vertices * factor),
        normalized_edges(edges),
    )


def _girth(graph: LogicalGraph) -> int | None:
    adjacency = _adjacency(graph)
    best = graph.num_vertices + 1
    for start in range(graph.num_vertices):
        distance = [-1] * graph.num_vertices
        parent = [-1] * graph.num_vertices
        distance[start] = 0
        queue = deque([start])
        while queue:
            vertex = queue.popleft()
            if 2 * distance[vertex] + 1 >= best:
                continue
            for neighbor in adjacency[vertex]:
                if distance[neighbor] < 0:
                    distance[neighbor] = distance[vertex] + 1
                    parent[neighbor] = vertex
                    queue.append(neighbor)
                elif parent[vertex] != neighbor:
                    best = min(best, distance[vertex] + distance[neighbor] + 1)
    return None if best == graph.num_vertices + 1 else best


def _conditioned_twists(
    edge_count: int, parity: int, stream: DeterministicStream
) -> tuple[int, ...]:
    bits = [stream.randbelow(2) for _ in range(edge_count - 1)]
    current = 0
    for bit in bits:
        current ^= bit
    bits.append(current ^ parity)
    return tuple(bits)


def _cfi_graph(base: LogicalGraph, twists: tuple[int, ...]) -> LogicalGraph:
    if len(twists) != len(base.edges):
        raise ValueError("one CFI twist is required per base edge")
    incidences: list[list[int]] = [[] for _ in range(base.num_vertices)]
    for edge_id, (first, second) in enumerate(base.edges):
        incidences[first].append(edge_id)
        incidences[second].append(edge_id)
    if any(len(edge_ids) != 3 for edge_ids in incidences):
        raise ValueError("the CFI builder requires a cubic base graph")

    # Per base vertex: outer vertices 10v..10v+5 are ordered by incidence then
    # bit; middle vertices 10v+6..10v+9 represent 000,011,101,110.
    even_triples = ((0, 0, 0), (0, 1, 1), (1, 0, 1), (1, 1, 0))
    edges: set[tuple[int, int]] = set()
    for vertex, edge_ids in enumerate(incidences):
        edge_ids.sort()
        offset = 10 * vertex
        for middle_index, triple in enumerate(even_triples):
            middle = offset + 6 + middle_index
            for incidence_index, bit in enumerate(triple):
                outer = offset + 2 * incidence_index + bit
                edges.add((min(middle, outer), max(middle, outer)))

    incidence_position = [
        {edge_id: position for position, edge_id in enumerate(sorted(edge_ids))}
        for edge_ids in incidences
    ]
    for edge_id, ((first, second), twist) in enumerate(zip(base.edges, twists, strict=True)):
        first_position = incidence_position[first][edge_id]
        second_position = incidence_position[second][edge_id]
        for bit in range(2):
            first_outer = 10 * first + 2 * first_position + bit
            second_outer = 10 * second + 2 * second_position + (bit ^ twist)
            edges.add((min(first_outer, second_outer), max(first_outer, second_outer)))

    colors = tuple(
        1 if local_index < 6 else 0
        for _vertex in range(base.num_vertices)
        for local_index in range(10)
    )
    return LogicalGraph(10 * base.num_vertices, colors, normalized_edges(edges))
