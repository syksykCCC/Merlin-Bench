"""Maintainer public-only reference for New List Graph Homomorphism C04."""

from __future__ import annotations

from collections.abc import Mapping
from itertools import combinations
from typing import Any


def _invert_line_graph(
    *, vertex_count: int, edges: set[tuple[int, int]], clique_size: int
) -> tuple[list[tuple[int, int]], list[tuple[int, ...]]]:
    adjacency = [set() for _ in range(vertex_count)]
    for first, second in edges:
        adjacency[first].add(second)
        adjacency[second].add(first)
    cliques: set[tuple[int, ...]] = set()
    for first in range(vertex_count):
        neighbors = sorted(adjacency[first])
        for selected in combinations(neighbors, clique_size - 1):
            if all(
                second in adjacency[left]
                for index, left in enumerate(selected)
                for second in selected[index + 1 :]
            ):
                cliques.add(tuple(sorted((first, *selected))))
    ordered = sorted(cliques)
    membership: list[list[int]] = [[] for _ in range(vertex_count)]
    for triangle_id, triangle in enumerate(ordered):
        for vertex in triangle:
            membership[vertex].append(triangle_id)
    if any(len(containers) != 2 for containers in membership):
        raise ValueError("public C04 graph is not a line graph of a cubic root")
    root_edges = [tuple(sorted(containers)) for containers in membership]
    if len(set(root_edges)) != vertex_count:
        raise ValueError("public C04 line-root edges are not unique")
    return root_edges, ordered


def solve_public(public_instance: Mapping[str, Any]) -> tuple[int, ...]:
    """Invert the public line graphs, solve their roots, and lift the mapping."""

    import importlib.util
    from pathlib import Path

    reference_path = Path(__file__).with_name("reference_new_list_homomorphism_c03.py")
    specification = importlib.util.spec_from_file_location(
        "aipbench_c03_reference_for_c04", reference_path
    )
    if specification is None or specification.loader is None:
        raise RuntimeError("C03 root reference could not be loaded")
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    solve_root = module.solve_public

    source_count = public_instance["source_num_vertices"]
    target_count = public_instance["target_num_vertices"]
    source_edges = {
        tuple(sorted((edge["u"] - 1, edge["v"] - 1))) for edge in public_instance["source_edges"]
    }
    target_edges = {
        tuple(sorted((edge["u"] - 1, edge["v"] - 1))) for edge in public_instance["target_edges"]
    }
    source_first_edges, source_k4 = _invert_line_graph(
        vertex_count=source_count, edges=source_edges, clique_size=4
    )
    target_first_edges, target_k4 = _invert_line_graph(
        vertex_count=target_count, edges=target_edges, clique_size=4
    )
    source_root_edges, source_k3 = _invert_line_graph(
        vertex_count=len(source_k4),
        edges=set(source_first_edges),
        clique_size=3,
    )
    target_root_edges, target_k3 = _invert_line_graph(
        vertex_count=len(target_k4),
        edges=set(target_first_edges),
        clique_size=3,
    )
    domains = [set() for _ in range(source_count)]
    for item in public_instance["lists"]:
        domains[item["source_vertex"] - 1] = {target - 1 for target in item["allowed_targets"]}
    domain_class = {
        domain: class_id
        for class_id, domain in enumerate(
            sorted({frozenset(domain) for domain in domains}, key=lambda item: min(item))
        )
    }
    source_class = [domain_class[frozenset(domain)] for domain in domains]
    target_class = {
        target: domain_class[frozenset(domain)] for domain in domains for target in domain
    }
    source_middle = {
        root_vertex
        for root_vertex, triangle in enumerate(source_k3)
        if len(
            {
                source_class[line_vertex]
                for line_vertex, edge in enumerate(source_first_edges)
                if set(edge) <= set(triangle)
            }
        )
        == 1
    }
    target_middle = {
        root_vertex
        for root_vertex, triangle in enumerate(target_k3)
        if len(
            {
                target_class[line_vertex]
                for line_vertex, edge in enumerate(target_first_edges)
                if set(edge) <= set(triangle)
            }
        )
        == 1
    }
    source_root_count = len(source_k3)
    target_root_count = len(target_k3)
    source_middle_targets = [vertex + 1 for vertex in sorted(target_middle)]
    source_outer_targets = [
        vertex + 1 for vertex in range(target_root_count) if vertex not in target_middle
    ]
    root_public: Mapping[str, Any] = {
        "source_num_vertices": source_root_count,
        "source_edges": [
            {"edge_id": edge_id + 1, "u": first + 1, "v": second + 1}
            for edge_id, (first, second) in enumerate(source_root_edges)
        ],
        "target_num_vertices": target_root_count,
        "target_edges": [
            {"edge_id": edge_id + 1, "u": first + 1, "v": second + 1}
            for edge_id, (first, second) in enumerate(target_root_edges)
        ],
        "lists": [
            {
                "source_vertex": vertex + 1,
                "allowed_targets": (
                    source_middle_targets if vertex in source_middle else source_outer_targets
                ),
            }
            for vertex in range(source_root_count)
        ],
    }
    root_mapping = [target - 1 for target in solve_root(root_public)]
    target_first_by_root_edge = {
        edge: line_vertex for line_vertex, edge in enumerate(target_root_edges)
    }
    first_mapping = [
        target_first_by_root_edge[tuple(sorted((root_mapping[first], root_mapping[second])))]
        for first, second in source_root_edges
    ]
    target_second_by_first_edge = {
        edge: line_vertex for line_vertex, edge in enumerate(target_first_edges)
    }
    mapping = [
        target_second_by_first_edge[tuple(sorted((first_mapping[first], first_mapping[second])))]
        for first, second in source_first_edges
    ]
    if any(mapping[vertex] not in domains[vertex] for vertex in range(source_count)):
        raise ValueError("public C04 lifted mapping violates a list")
    if any(
        tuple(sorted((mapping[first], mapping[second]))) not in target_edges
        for first, second in source_edges
    ):
        raise ValueError("public C04 lifted mapping violates an edge")
    return tuple(target + 1 for target in mapping)


__all__ = ["solve_public"]
