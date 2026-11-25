"""Shared primitives used by the current Merlin-Bench tasks."""

from __future__ import annotations


def _euler_edge_order(
    num_vertices: int, root_edges: tuple[tuple[int, int], ...]
) -> tuple[int, ...]:
    incidence: list[list[tuple[int, int]]] = [[] for _ in range(num_vertices)]
    for edge_id, (first, second) in enumerate(root_edges):
        incidence[first].append((edge_id, second))
        incidence[second].append((edge_id, first))
    used = [False] * len(root_edges)
    positions = [0] * num_vertices
    vertex_stack = [0]
    edge_stack: list[int] = []
    reversed_edges: list[int] = []
    while vertex_stack:
        vertex = vertex_stack[-1]
        while (
            positions[vertex] < len(incidence[vertex])
            and used[incidence[vertex][positions[vertex]][0]]
        ):
            positions[vertex] += 1
        if positions[vertex] == len(incidence[vertex]):
            vertex_stack.pop()
            if edge_stack:
                reversed_edges.append(edge_stack.pop())
            continue
        edge_id, neighbor = incidence[vertex][positions[vertex]]
        positions[vertex] += 1
        if used[edge_id]:
            continue
        used[edge_id] = True
        vertex_stack.append(neighbor)
        edge_stack.append(edge_id)
    if not all(used) or len(reversed_edges) != len(root_edges):
        raise ValueError("root graph is not connected Eulerian")
    return tuple(reversed(reversed_edges))
