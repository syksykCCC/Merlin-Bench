"""Maintainer public-only reference for New List Graph Homomorphism C05."""

from __future__ import annotations

import importlib.util
from collections import defaultdict, deque
from collections.abc import Mapping
from pathlib import Path
from typing import Any


def _cover_isomorphism(left: Any, right: Any) -> dict[int, int]:
    from aipbench.tasks.new_homomorphism_cases.c03 import _rooted_wl_signatures

    def signatures(graph: Any) -> dict[int, Any]:
        nodes = sorted(graph.nodes)
        index = {node: position for position, node in enumerate(nodes)}
        adjacency = [{index[neighbor] for neighbor in graph.neighbors(node)} for node in nodes]
        colors = [graph.nodes[node]["color"] for node in nodes]
        raw = _rooted_wl_signatures(adjacency=adjacency, colors=colors)
        return {node: raw[index[node]] for node in nodes}

    left_signature = signatures(left)
    right_signature = signatures(right)
    left_groups: dict[Any, list[int]] = defaultdict(list)
    right_groups: dict[Any, list[int]] = defaultdict(list)
    for vertex, signature in left_signature.items():
        left_groups[signature].append(vertex)
    for vertex, signature in right_signature.items():
        right_groups[signature].append(vertex)
    if set(left_groups) != set(right_groups) or any(
        len(left_groups[key]) != len(right_groups[key]) for key in left_groups
    ):
        raise ValueError("public C05 cyclic-cover signatures disagree")
    if len(left_groups) != 30 or set(map(len, left_groups.values())) != {6}:
        raise ValueError("public C05 signatures do not recover thirty six-sheets")

    start = min(left.nodes)
    for target_start in right_groups[left_signature[start]]:
        mapping = {start: target_start}
        inverse = {target_start: start}
        queue = deque([start])
        valid = True
        while queue and valid:
            vertex = queue.popleft()
            target_vertex = mapping[vertex]
            for neighbor in left.neighbors(vertex):
                candidates = [
                    target_neighbor
                    for target_neighbor in right.neighbors(target_vertex)
                    if right_signature[target_neighbor] == left_signature[neighbor]
                ]
                if len(candidates) != 1:
                    valid = False
                    break
                image = candidates[0]
                if neighbor in mapping and mapping[neighbor] != image:
                    valid = False
                    break
                if image in inverse and inverse[image] != neighbor:
                    valid = False
                    break
                if neighbor not in mapping:
                    mapping[neighbor] = image
                    inverse[image] = neighbor
                    queue.append(neighbor)
        if (
            valid
            and len(mapping) == len(left.nodes)
            and all(
                mapping[second] in right.neighbors(mapping[first]) for first, second in left.edges
            )
        ):
            return mapping
    raise ValueError("public C05 cover phase propagation found no isomorphism")


def solve_public(public_instance: Mapping[str, Any]) -> tuple[int, ...]:
    """Contract CFI gadgets, match cover sheets, solve frames, and recheck."""

    reference_path = Path(__file__).with_name("reference_new_list_homomorphism_c03.py")
    specification = importlib.util.spec_from_file_location(
        "aipbench_c03_reference_for_c05", reference_path
    )
    if specification is None or specification.loader is None:
        raise RuntimeError("C03 reference primitives could not be loaded")
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)

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
    middle_size = min(map(len, classes))
    source_middle = {vertex for vertex, domain in enumerate(domains) if len(domain) == middle_size}
    target_middle = {
        vertex for vertex, domain in target_class.items() if len(domain) == middle_size
    }
    class_keys = {
        domain: index for index, domain in enumerate(sorted(classes, key=lambda item: min(item)))
    }
    left = module._recover_graph(
        vertex_count=source_count,
        edges=source_edges,
        middle=source_middle,
        class_of={vertex: class_keys[frozenset(domains[vertex])] for vertex in range(source_count)},
    )
    right = module._recover_graph(
        vertex_count=target_count,
        edges=target_edges,
        middle=target_middle,
        class_of={vertex: class_keys[target_class[vertex]] for vertex in range(target_count)},
    )
    base_mapping = _cover_isomorphism(left[0], right[0])

    incidence: dict[tuple[int, int], int] = {}
    directed_incidences = [
        (vertex, neighbor) for vertex in left[0] for neighbor in left[0].neighbors(vertex)
    ]
    for variable, (vertex, neighbor) in enumerate(directed_incidences):
        incidence[vertex, neighbor] = variable
    rows: list[int] = []
    values: list[int] = []
    for first, second in left[0].edges:
        rows.append((1 << incidence[first, second]) | (1 << incidence[second, first]))
        values.append(
            left[4][tuple(sorted((first, second)))]
            ^ right[4][tuple(sorted((base_mapping[first], base_mapping[second])))]
        )
    for vertex in left[0]:
        row = 0
        for neighbor in left[0].neighbors(vertex):
            row |= 1 << incidence[vertex, neighbor]
        rows.append(row)
        values.append(left[3][vertex] ^ right[3][base_mapping[vertex]])
    pivots: dict[int, tuple[int, int]] = {}
    for row, value in zip(rows, values, strict=True):
        while row:
            pivot = (row & -row).bit_length() - 1
            if pivot not in pivots:
                pivots[pivot] = (row, value)
                break
            row ^= pivots[pivot][0]
            value ^= pivots[pivot][1]
        if not row and value:
            raise ValueError("public C05 frame equations are inconsistent")
    solution = [0] * len(incidence)
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
            assigned = {
                base_mapping[neighbor]: bits[index] ^ solution[incidence[vertex, neighbor]]
                for index, neighbor in enumerate(source_neighbors)
            }
            target_bits = tuple(assigned[neighbor] for neighbor in target_neighbors)
            mapping[middle_vertex] = right[2][target_vertex][target_bits]
    if any(mapping[vertex] not in domains[vertex] for vertex in range(source_count)):
        raise ValueError("public C05 reconstruction violates a list")
    if any(
        tuple(sorted((mapping[first], mapping[second]))) not in target_edges
        for first, second in source_edges
    ):
        raise ValueError("public C05 reconstruction violates an edge")
    return tuple(target + 1 for target in mapping)


__all__ = ["solve_public"]
