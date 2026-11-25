"""C02: a tree of independently permuted finite-domain constraints."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from aipbench.tasks.new_homomorphism_cases.common import NewHomomorphismStream
from aipbench.tasks.shared.homomorphism_cases.common import (
    CaseBlueprint,
    integer_parameter,
    normalized_edges,
)

CASE_ID: Final = "c02"
DEFAULT_PARAMETERS: Final[Mapping[str, Any]] = {
    "branching_factor": 4,
    "depth": 5,
    "domain_size": 6,
}


def build(stream: NewHomomorphismStream, parameters: Mapping[str, Any]) -> CaseBlueprint:
    unexpected = set(parameters) - set(DEFAULT_PARAMETERS)
    if unexpected:
        raise ValueError(f"unsupported c02 parameters: {sorted(unexpected)!r}")
    branching = integer_parameter(parameters, "branching_factor", minimum=2)
    depth = integer_parameter(parameters, "depth", minimum=1)
    domain_size = integer_parameter(parameters, "domain_size", minimum=2)
    num_vertices = sum(branching**level for level in range(depth + 1))
    target_num_vertices = num_vertices * domain_size
    if num_vertices > 20_000 or target_num_vertices > 100_000:
        raise ValueError("c02 profile exceeds the supported envelope")

    source_edges: set[tuple[int, int]] = set()
    target_edges: set[tuple[int, int]] = set()
    states = [0] * num_vertices
    states[0] = stream.randbelow(domain_size)
    for child in range(1, num_vertices):
        parent = (child - 1) // branching
        source_edges.add((parent, child))
        permutation = list(range(domain_size))
        stream.shuffle(permutation)
        states[child] = permutation[states[parent]]
        for parent_state, child_state in enumerate(permutation):
            target_edges.add(
                tuple(
                    sorted(
                        (
                            parent * domain_size + parent_state,
                            child * domain_size + child_state,
                        )
                    )
                )
            )

    allowed = [
        frozenset({states[0]})
        if vertex == 0
        else frozenset(range(vertex * domain_size, (vertex + 1) * domain_size))
        for vertex in range(num_vertices)
    ]
    mapping = tuple(vertex * domain_size + states[vertex] for vertex in range(num_vertices))
    return CaseBlueprint(
        source_num_vertices=num_vertices,
        source_edges=normalized_edges(source_edges),
        target_num_vertices=target_num_vertices,
        target_edges=normalized_edges(target_edges),
        allowed_targets=tuple(allowed),
        reference_mapping=mapping,
        metadata={
            "mathematical_family": "tree_of_permutation_constraints",
            "branching_factor": branching,
            "depth": depth,
            "domain_size": domain_size,
            "unique_mapping": True,
        },
    )


__all__ = ["CASE_ID", "DEFAULT_PARAMETERS", "build"]
