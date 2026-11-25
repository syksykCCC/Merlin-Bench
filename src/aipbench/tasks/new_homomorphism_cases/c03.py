"""C03: independently switched isomorphic CFI roots with coarse public lists."""

from __future__ import annotations

from collections import Counter, deque
from collections.abc import Mapping
from typing import Any, Final

from aipbench.tasks.new_homomorphism_cases.common import NewHomomorphismStream
from aipbench.tasks.shared.graph_non_isomorphism_cases import c05 as cfi_primitives
from aipbench.tasks.shared.graph_non_isomorphism_cases.common import (
    LogicalGraph,
    normalized_edges,
)
from aipbench.tasks.shared.homomorphism_cases.common import CaseBlueprint, integer_parameter

CASE_ID: Final = "c03"
DEFAULT_PARAMETERS: Final[Mapping[str, Any]] = {"lift_factor": 8}
_EVEN_TRIPLES: Final = ((0, 0, 0), (0, 1, 1), (1, 0, 1), (1, 1, 0))


def _rooted_wl_signatures(
    *, adjacency: list[set[int]], colors: list[int]
) -> tuple[tuple[int, tuple[tuple[int, int], ...]], ...]:
    import hashlib

    result = []
    for root in range(len(adjacency)):
        refined = [f"{colors[vertex]}:{int(vertex == root)}" for vertex in range(len(adjacency))]
        history = []
        for _iteration in range(len(adjacency)):
            updated = [
                hashlib.sha256(
                    (
                        refined[vertex]
                        + "|"
                        + "|".join(sorted(refined[neighbor] for neighbor in adjacency[vertex]))
                    ).encode()
                ).hexdigest()
                for vertex in range(len(adjacency))
            ]
            histogram = tuple(sorted(Counter(updated).items()))
            history.append(histogram)
            if updated == refined:
                break
            refined = updated
        result.append(tuple(history))
    return tuple(result)


def _random_cubic_bipartite_base(
    stream: NewHomomorphismStream,
    *,
    half_order: int,
    distinguish_bipartition: bool = True,
) -> LogicalGraph:
    order = 2 * half_order
    for _attempt in range(64):
        edges: set[tuple[int, int]] = set()
        valid = True
        for _matching in range(3):
            permutation = list(range(half_order))
            stream.shuffle(permutation)
            matching = {(left, half_order + permutation[left]) for left in range(half_order)}
            if edges & matching:
                valid = False
                break
            edges |= matching
        if not valid:
            continue
        adjacency = [set() for _ in range(order)]
        for first, second in edges:
            adjacency[first].add(second)
            adjacency[second].add(first)
        seen = {0}
        queue = deque([0])
        while queue:
            vertex = queue.popleft()
            for neighbor in adjacency[vertex] - seen:
                seen.add(neighbor)
                queue.append(neighbor)
        if len(seen) != order:
            continue
        colors = [int(distinguish_bipartition and vertex >= half_order) for vertex in range(order)]
        signatures = _rooted_wl_signatures(adjacency=adjacency, colors=colors)
        if len(set(signatures)) != order:
            continue
        return LogicalGraph(order, tuple(colors), normalized_edges(edges))
    raise RuntimeError("C03 could not sample a rooted-WL-rigid cubic bipartite base")


def build(stream: NewHomomorphismStream, parameters: Mapping[str, Any]) -> CaseBlueprint:
    unexpected = set(parameters) - set(DEFAULT_PARAMETERS)
    if unexpected:
        raise ValueError(f"unsupported c03 parameters: {sorted(unexpected)!r}")
    factor = integer_parameter(parameters, "lift_factor", minimum=2)
    if factor > 12:
        raise ValueError("c03 profile exceeds the supported envelope")

    base = _random_cubic_bipartite_base(stream, half_order=15 * factor)
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

    target_by_role: dict[tuple[bool, bool], frozenset[int]] = {}
    for middle in (False, True):
        for right_side in (False, True):
            target_by_role[middle, right_side] = frozenset(
                logical
                for logical in range(target.num_vertices)
                if (logical % 10 >= 6) == middle and (logical // 10 >= 15 * factor) == right_side
            )
    allowed = tuple(
        target_by_role[logical % 10 >= 6, logical // 10 >= 15 * factor]
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
            "mathematical_family": "coarsely_listed_even_frame_switched_cfi_isomorphism",
            "lift_factor": factor,
            "base_num_vertices": base.num_vertices,
            "base_num_edges": len(base.edges),
            "unique_mapping": False,
        },
    )


__all__ = ["CASE_ID", "DEFAULT_PARAMETERS", "build", "_rooted_wl_signatures"]
