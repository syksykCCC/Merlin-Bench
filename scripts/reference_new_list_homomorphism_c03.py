"""Maintainer public-only reference for New List Graph Homomorphism C03."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


class _BaseGraph:
    def __init__(self) -> None:
        self.nodes: dict[int, dict[str, int]] = {}
        self.adjacency: dict[int, set[int]] = {}

    def add_node(self, vertex: int, *, color: int) -> None:
        self.nodes[vertex] = {"color": color}
        self.adjacency.setdefault(vertex, set())

    def add_edge(self, first: int, second: int) -> None:
        self.adjacency.setdefault(first, set()).add(second)
        self.adjacency.setdefault(second, set()).add(first)

    def neighbors(self, vertex: int) -> set[int]:
        return self.adjacency[vertex]

    def __iter__(self):
        return iter(self.nodes)

    @property
    def edges(self) -> tuple[tuple[int, int], ...]:
        return tuple(
            (first, second)
            for first, neighbors in self.adjacency.items()
            for second in neighbors
            if first < second
        )


def _recover_graph(
    *,
    vertex_count: int,
    edges: set[tuple[int, int]],
    middle: set[int],
    class_of: Mapping[int, int],
) -> tuple[
    Any,
    dict[tuple[int, int], tuple[int, int]],
    dict[int, dict[tuple[int, int, int], int]],
    dict[int, int],
    dict[tuple[int, int], int],
]:
    adjacency = [set() for _ in range(vertex_count)]
    for first, second in edges:
        adjacency[first].add(second)
        adjacency[second].add(first)
    parent = {vertex: vertex for vertex in middle}

    def find(vertex: int) -> int:
        while parent[vertex] != vertex:
            parent[vertex] = parent[parent[vertex]]
            vertex = parent[vertex]
        return vertex

    def union(first: int, second: int) -> None:
        left, right = find(first), find(second)
        if left != right:
            parent[right] = left

    outer = set(range(vertex_count)) - middle
    for vertex in outer:
        internal = sorted(adjacency[vertex] & middle)
        if len(internal) == 2:
            union(*internal)
    components: dict[int, set[int]] = {}
    for vertex in middle:
        components.setdefault(find(vertex), set()).add(vertex)
    gadgets: list[tuple[set[int], set[int]]] = []
    owner: dict[int, int] = {}
    for component in components.values():
        if len(component) != 4:
            raise ValueError("public C03 middle component does not have four vertices")
        local_outer = set().union(*(adjacency[vertex] & outer for vertex in component))
        if len(local_outer) != 6:
            raise ValueError("public C03 gadget does not have six outer vertices")
        gadget = len(gadgets)
        gadgets.append((component, local_outer))
        for vertex in component | local_outer:
            owner[vertex] = gadget

    pairs: dict[tuple[int, int], tuple[int, int]] = {}
    states: dict[int, dict[tuple[int, int, int], int]] = {}
    parity: dict[int, int] = {}
    base = _BaseGraph()
    for gadget, (component, local_outer) in enumerate(gadgets):
        base.add_node(gadget, color=class_of[next(iter(component))])
        internal_neighbors = {vertex: adjacency[vertex] & component for vertex in local_outer}
        for first in local_outer:
            for second in local_outer:
                if first < second and not (internal_neighbors[first] & internal_neighbors[second]):
                    next_first = next(iter(adjacency[first] - component))
                    next_second = next(iter(adjacency[second] - component))
                    if owner[next_first] != owner[next_second]:
                        raise ValueError("public C03 outer pair endpoints disagree")
                    neighbor = owner[next_first]
                    pairs[gadget, neighbor] = tuple(sorted((first, second)))
                    base.add_edge(gadget, neighbor)
        state_map: dict[tuple[int, int, int], int] = {}
        for vertex in component:
            bits = tuple(
                int(vertex not in adjacency[pairs[gadget, neighbor][0]])
                for neighbor in sorted(base.neighbors(gadget))
            )
            state_map[bits] = vertex
        if len(state_map) != 4:
            raise ValueError("public C03 middle truth table is malformed")
        states[gadget] = state_map
        state_parities = {sum(bits) % 2 for bits in state_map}
        if len(state_parities) != 1:
            raise ValueError("public C03 gadget parity is malformed")
        parity[gadget] = next(iter(state_parities))
    twists: dict[tuple[int, int], int] = {}
    for first, second in base.edges:
        left = pairs[first, second]
        right = pairs[second, first]
        twists[tuple(sorted((first, second)))] = int(right[0] not in adjacency[left[0]])
    return base, pairs, states, parity, twists


def solve_public(public_instance: Mapping[str, Any]) -> tuple[int, ...]:
    """Recover any accepted C03 mapping from public graphs and lists alone."""

    source_count = public_instance["source_num_vertices"]
    target_count = public_instance["target_num_vertices"]
    source_edges = {
        tuple(sorted((edge["u"] - 1, edge["v"] - 1))) for edge in public_instance["source_edges"]
    }
    target_edges = {
        tuple(sorted((edge["u"] - 1, edge["v"] - 1))) for edge in public_instance["target_edges"]
    }
    domains = [set() for _ in range(source_count)]
    for item in public_instance["lists"]:
        domains[item["source_vertex"] - 1] = {target - 1 for target in item["allowed_targets"]}
    classes = {frozenset(domain) for domain in domains}
    target_class = {target: domain for domain in classes for target in domain}
    middle_class_size = min(map(len, classes))
    source_middle = {
        vertex for vertex, domain in enumerate(domains) if len(domain) == middle_class_size
    }
    target_middle = {
        vertex for vertex, domain in target_class.items() if len(domain) == middle_class_size
    }
    class_keys = {
        domain: index for index, domain in enumerate(sorted(classes, key=lambda item: min(item)))
    }
    left = _recover_graph(
        vertex_count=source_count,
        edges=source_edges,
        middle=source_middle,
        class_of={vertex: class_keys[frozenset(domains[vertex])] for vertex in range(source_count)},
    )
    right = _recover_graph(
        vertex_count=target_count,
        edges=target_edges,
        middle=target_middle,
        class_of={vertex: class_keys[target_class[vertex]] for vertex in range(target_count)},
    )
    from aipbench.tasks.new_homomorphism_cases.c03 import _rooted_wl_signatures

    def signatures(graph: Any) -> tuple[Any, ...]:
        nodes = sorted(graph.nodes)
        index = {node: position for position, node in enumerate(nodes)}
        adjacency = [{index[neighbor] for neighbor in graph.neighbors(node)} for node in nodes]
        colors = [graph.nodes[node]["color"] for node in nodes]
        raw = _rooted_wl_signatures(adjacency=adjacency, colors=colors)
        return tuple(raw[index[node]] for node in nodes)

    left_nodes = sorted(left[0].nodes)
    right_nodes = sorted(right[0].nodes)
    left_signatures = signatures(left[0])
    right_signatures = signatures(right[0])
    right_by_signature = {
        signature: node for node, signature in zip(right_nodes, right_signatures, strict=True)
    }
    if len(right_by_signature) != len(right_nodes) or set(left_signatures) != set(right_signatures):
        raise ValueError("public C03 base signatures are not uniquely matched")
    base_mapping = dict(
        zip(
            left_nodes,
            (right_by_signature[signature] for signature in left_signatures),
            strict=True,
        )
    )

    incidence: dict[tuple[int, int], int] = {}
    variable_count = 0
    for vertex in left[0]:
        for neighbor in left[0].neighbors(vertex):
            incidence[vertex, neighbor] = variable_count
            variable_count += 1
    rows: list[int] = []
    right_hand_side: list[int] = []
    for first, second in left[0].edges:
        rows.append((1 << incidence[first, second]) | (1 << incidence[second, first]))
        rows_key = tuple(sorted((first, second)))
        target_key = tuple(sorted((base_mapping[first], base_mapping[second])))
        right_hand_side.append(left[4][rows_key] ^ right[4][target_key])
    for vertex in left[0]:
        row = 0
        for neighbor in left[0].neighbors(vertex):
            row |= 1 << incidence[vertex, neighbor]
        rows.append(row)
        right_hand_side.append(left[3][vertex] ^ right[3][base_mapping[vertex]])
    pivots: dict[int, tuple[int, int]] = {}
    for row, value in zip(rows, right_hand_side, strict=True):
        while row:
            pivot = (row & -row).bit_length() - 1
            if pivot not in pivots:
                pivots[pivot] = (row, value)
                break
            row ^= pivots[pivot][0]
            value ^= pivots[pivot][1]
        if not row and value:
            raise ValueError("public C03 frame equations are inconsistent")
    solution = [0] * variable_count
    solution_mask = 0
    for pivot in sorted(pivots, reverse=True):
        row, value = pivots[pivot]
        solution[pivot] = value ^ ((row & solution_mask).bit_count() % 2)
        solution_mask |= solution[pivot] << pivot

    mapping = [0] * source_count
    for vertex in left[0]:
        target_vertex = base_mapping[vertex]
        for neighbor in left[0].neighbors(vertex):
            source_pair = left[1][vertex, neighbor]
            target_pair = right[1][target_vertex, base_mapping[neighbor]]
            shift = solution[incidence[vertex, neighbor]]
            mapping[source_pair[0]] = target_pair[shift]
            mapping[source_pair[1]] = target_pair[1 ^ shift]
        source_neighbors = sorted(left[0].neighbors(vertex))
        target_neighbors = sorted(right[0].neighbors(target_vertex))
        for bits, middle_vertex in left[2][vertex].items():
            values = {
                base_mapping[neighbor]: bits[index] ^ solution[incidence[vertex, neighbor]]
                for index, neighbor in enumerate(source_neighbors)
            }
            target_bits = tuple(values[neighbor] for neighbor in target_neighbors)
            mapping[middle_vertex] = right[2][target_vertex][target_bits]
    if any(mapping[vertex] not in domains[vertex] for vertex in range(source_count)):
        raise ValueError("public C03 reconstruction violates a list")
    if any(
        tuple(sorted((mapping[first], mapping[second]))) not in target_edges
        for first, second in source_edges
    ):
        raise ValueError("public C03 reconstruction violates an edge")
    return tuple(target + 1 for target in mapping)


__all__ = ["solve_public"]
