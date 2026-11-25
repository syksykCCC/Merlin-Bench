"""C05: switched CFI isomorphism over a symmetric cyclic cover."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from aipbench.tasks.new_homomorphism_cases.c03 import _EVEN_TRIPLES
from aipbench.tasks.new_homomorphism_cases.common import NewHomomorphismStream
from aipbench.tasks.shared.graph_non_isomorphism_cases import c05 as cfi_primitives
from aipbench.tasks.shared.homomorphism_cases.common import CaseBlueprint, integer_parameter

CASE_ID: Final = "c05"
DEFAULT_PARAMETERS: Final[Mapping[str, Any]] = {"lift_factor": 6}


def build(stream: NewHomomorphismStream, parameters: Mapping[str, Any]) -> CaseBlueprint:
    unexpected = set(parameters) - set(DEFAULT_PARAMETERS)
    if unexpected:
        raise ValueError(f"unsupported c05 parameters: {sorted(unexpected)!r}")
    factor = integer_parameter(parameters, "lift_factor", minimum=2)
    if factor > 8:
        raise ValueError("c05 profile exceeds the supported envelope")

    base = cfi_primitives._cyclic_lift(cfi_primitives._gq_incidence_graph(), factor, stream)
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
    source = cfi_primitives._cfi_graph(base, twists0)
    target = cfi_primitives._cfi_graph(base, twists1)

    mapping = [0] * source.num_vertices
    for vertex, frame in enumerate(frames):
        for incidence in range(3):
            for bit in range(2):
                mapping[10 * vertex + 2 * incidence + bit] = (
                    10 * vertex + 2 * incidence + (bit ^ frame[incidence])
                )
        for state, triple in enumerate(_EVEN_TRIPLES):
            shifted = tuple(bit ^ flip for bit, flip in zip(triple, frame, strict=True))
            mapping[10 * vertex + 6 + state] = 10 * vertex + 6 + _EVEN_TRIPLES.index(shifted)

    half_order = 15 * factor
    targets_by_role: dict[tuple[bool, bool], frozenset[int]] = {}
    for middle in (False, True):
        for right_side in (False, True):
            targets_by_role[middle, right_side] = frozenset(
                logical
                for logical in range(target.num_vertices)
                if (logical % 10 >= 6) == middle and (logical // 10 >= half_order) == right_side
            )
    allowed = tuple(
        targets_by_role[logical % 10 >= 6, logical // 10 >= half_order]
        for logical in range(source.num_vertices)
    )
    return CaseBlueprint(
        source_num_vertices=source.num_vertices,
        source_edges=source.edges,
        target_num_vertices=target.num_vertices,
        target_edges=target.edges,
        allowed_targets=allowed,
        reference_mapping=tuple(mapping),
        metadata={
            "mathematical_family": "symmetric_cyclic_cover_switched_cfi_isomorphism",
            "lift_factor": factor,
            "base_num_vertices": base.num_vertices,
            "base_num_edges": len(base.edges),
            "base_girth": cfi_primitives._girth(base),
            "unique_mapping": False,
        },
    )


__all__ = ["CASE_ID", "DEFAULT_PARAMETERS", "build"]
