"""C04: a line-graph blind transform of a switched CFI isomorphism."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from aipbench.tasks.new_homomorphism_cases.c03 import (
    _EVEN_TRIPLES,
    _random_cubic_bipartite_base,
)
from aipbench.tasks.new_homomorphism_cases.common import NewHomomorphismStream
from aipbench.tasks.shared.graph_non_isomorphism_cases import c05 as cfi_primitives
from aipbench.tasks.shared.graph_non_isomorphism_cases.common import line_graph
from aipbench.tasks.shared.homomorphism_cases.common import CaseBlueprint, integer_parameter

CASE_ID: Final = "c04"
DEFAULT_PARAMETERS: Final[Mapping[str, Any]] = {"lift_factor": 4}


def build(stream: NewHomomorphismStream, parameters: Mapping[str, Any]) -> CaseBlueprint:
    unexpected = set(parameters) - set(DEFAULT_PARAMETERS)
    if unexpected:
        raise ValueError(f"unsupported c04 parameters: {sorted(unexpected)!r}")
    factor = integer_parameter(parameters, "lift_factor", minimum=2)
    if factor > 12:
        raise ValueError("c04 profile exceeds the supported envelope")

    base = _random_cubic_bipartite_base(
        stream,
        half_order=15 * factor,
        distinguish_bipartition=False,
    )
    twists0 = cfi_primitives._conditioned_twists(len(base.edges), 0, stream)
    incidences: list[list[int]] = [[] for _ in range(base.num_vertices)]
    for edge_id, (first, second) in enumerate(base.edges):
        incidences[first].append(edge_id)
        incidences[second].append(edge_id)
    for edge_ids in incidences:
        edge_ids.sort()
    positions = [
        {edge_id: position for position, edge_id in enumerate(edge_ids)} for edge_ids in incidences
    ]
    frames = [_EVEN_TRIPLES[stream.randbelow(len(_EVEN_TRIPLES))] for _ in range(base.num_vertices)]
    twists1 = tuple(
        twist
        ^ frames[first][positions[first][edge_id]]
        ^ frames[second][positions[second][edge_id]]
        for edge_id, ((first, second), twist) in enumerate(zip(base.edges, twists0, strict=True))
    )
    source_root = cfi_primitives._cfi_graph(base, twists0)
    target_root = cfi_primitives._cfi_graph(base, twists1)
    root_mapping = [0] * source_root.num_vertices
    for vertex, frame in enumerate(frames):
        for incidence in range(3):
            for bit in range(2):
                root_mapping[10 * vertex + 2 * incidence + bit] = (
                    10 * vertex + 2 * incidence + (bit ^ frame[incidence])
                )
        for state, triple in enumerate(_EVEN_TRIPLES):
            shifted = tuple(bit ^ flip for bit, flip in zip(triple, frame, strict=True))
            root_mapping[10 * vertex + 6 + state] = 10 * vertex + 6 + _EVEN_TRIPLES.index(shifted)

    source_first_line = line_graph(source_root)
    target_first_line = line_graph(target_root)
    target_root_edge_id = {edge: index for index, edge in enumerate(target_root.edges)}
    first_line_mapping = tuple(
        target_root_edge_id[tuple(sorted((root_mapping[first], root_mapping[second])))]
        for first, second in source_root.edges
    )
    source = line_graph(source_first_line)
    target = line_graph(target_first_line)
    target_first_line_edge_id = {edge: index for index, edge in enumerate(target_first_line.edges)}
    mapping = tuple(
        target_first_line_edge_id[
            tuple(sorted((first_line_mapping[first], first_line_mapping[second])))
        ]
        for first, second in source_first_line.edges
    )

    half_order = 15 * factor

    root_incident: list[set[int]] = [set() for _ in range(source_root.num_vertices)]
    for edge_id, (first, second) in enumerate(source_root.edges):
        root_incident[first].add(edge_id)
        root_incident[second].add(edge_id)

    def role(
        first_line_edge: tuple[int, int], *, root_edges: tuple[tuple[int, int], ...]
    ) -> tuple[str, int, int]:
        first_root_edge = root_edges[first_line_edge[0]]
        second_root_edge = root_edges[first_line_edge[1]]
        common = set(first_root_edge) & set(second_root_edge)
        if len(common) != 1:
            raise AssertionError("C04 first-line edge does not have one root center")
        center = next(iter(common))
        center_base, center_local = divmod(center, 10)
        side = int(center_base >= half_order)
        if center_local >= 6:
            return ("middle", side, 0)
        incident = {edge_id for edge_id, edge in enumerate(root_edges) if center in edge}
        omitted = next(iter(incident - set(first_line_edge)))
        omitted_edge = root_edges[omitted]
        omitted_external = omitted_edge[0] // 10 != omitted_edge[1] // 10
        return ("outer", side, int(omitted_external))

    targets_by_role: dict[tuple[str, int, int], set[int]] = {}
    for edge_id, edge in enumerate(target_first_line.edges):
        targets_by_role.setdefault(role(edge, root_edges=target_root.edges), set()).add(edge_id)
    allowed = tuple(
        frozenset(targets_by_role[role(edge, root_edges=source_root.edges)])
        for edge in source_first_line.edges
    )
    return CaseBlueprint(
        source_num_vertices=source.num_vertices,
        source_edges=source.edges,
        target_num_vertices=target.num_vertices,
        target_edges=target.edges,
        allowed_targets=allowed,
        reference_mapping=mapping,
        metadata={
            "mathematical_family": "line_graph_of_switched_cfi_isomorphism",
            "lift_factor": factor,
            "root_num_vertices": source_root.num_vertices,
            "root_num_edges": len(source_root.edges),
            "first_line_num_vertices": source_first_line.num_vertices,
            "first_line_num_edges": len(source_first_line.edges),
            "base_num_vertices": base.num_vertices,
            "base_num_edges": len(base.edges),
            "unique_mapping": False,
        },
    )


__all__ = ["CASE_ID", "DEFAULT_PARAMETERS", "build"]
