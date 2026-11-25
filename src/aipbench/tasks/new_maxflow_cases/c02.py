"""C02: a regular bipartite unit-capacity matching network."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from aipbench.tasks.new_maxflow_cases.common import (
    CaseBlueprint,
    LogicalEdge,
    NewMaxFlowStream,
    integer_parameter,
)

CASE_ID: Final = "c02"
DEFAULT_PARAMETERS: Final[Mapping[str, Any]] = {
    "side_size": 200,
    "cyclic_degree": 22,
    "redundant_edges": 200,
}


def build(stream: NewMaxFlowStream, parameters: Mapping[str, Any]) -> CaseBlueprint:
    side_size = integer_parameter(parameters, "side_size", minimum=2)
    cyclic_degree = integer_parameter(parameters, "cyclic_degree", minimum=1)
    redundant_edges = integer_parameter(parameters, "redundant_edges", minimum=0)
    if cyclic_degree > side_size:
        raise ValueError("cyclic_degree cannot exceed side_size")
    available_decoys = side_size * side_size - side_size * cyclic_degree
    if redundant_edges > available_decoys:
        raise ValueError("too many redundant edges for a simple bipartite middle layer")

    source = 0
    first_left = 1
    first_right = first_left + side_size
    sink = first_right + side_size

    nonzero_residues = list(range(1, side_size))
    stream.shuffle(nonzero_residues)
    residues = frozenset({0, *nonzero_residues[: cyclic_degree - 1]})

    edges: list[LogicalEdge] = []
    for index in range(side_size):
        edges.append(LogicalEdge(source, first_left + index, 1))
        edges.append(LogicalEdge(first_right + index, sink, 1))

    middle_pairs: set[tuple[int, int]] = set()
    for left_index in range(side_size):
        for residue in sorted(residues):
            right_index = (left_index + residue) % side_size
            middle_pairs.add((left_index, right_index))

    while len(middle_pairs) < side_size * cyclic_degree + redundant_edges:
        candidate = (stream.randbelow(side_size), stream.randbelow(side_size))
        middle_pairs.add(candidate)

    ordered_middle_pairs = sorted(middle_pairs)
    stream.shuffle(ordered_middle_pairs)
    edges.extend(
        LogicalEdge(first_left + left, first_right + right, 1)
        for left, right in ordered_middle_pairs
    )

    return CaseBlueprint(
        num_vertices=2 * side_size + 2,
        source=source,
        sink=sink,
        edges=tuple(edges),
        reference_flow_value=side_size,
        reference_source_side_cut=frozenset({source}),
        metadata={
            "mathematical_family": "regular_bipartite_matching_network",
            "side_size": side_size,
            "cyclic_degree": cyclic_degree,
            "redundant_edges": redundant_edges,
            "identity_matching_present": True,
        },
    )
