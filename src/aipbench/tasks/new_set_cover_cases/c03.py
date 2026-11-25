"""C03: marker-recoverable bounded-width Boolean path cover."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from aipbench.tasks.new_set_cover_cases.common import (
    CaseBlueprint,
    NewSetCoverStream,
    WeightedCandidate,
    integer_parameter,
)

CASE_ID: Final = "c03"
DEFAULT_PARAMETERS: Final[Mapping[str, Any]] = {
    "num_blocks": 42,
    "block_width": 12,
    "local_clauses": 20,
    "boundary_clauses": 24,
    "weight_base": 10_000,
}


def build(stream: NewSetCoverStream, parameters: Mapping[str, Any]) -> CaseBlueprint:
    num_blocks = integer_parameter(parameters, "num_blocks", minimum=3)
    width = integer_parameter(parameters, "block_width", minimum=6)
    local_count = integer_parameter(parameters, "local_clauses", minimum=1)
    boundary_count = integer_parameter(parameters, "boundary_clauses", minimum=1)
    weight_base = integer_parameter(parameters, "weight_base", minimum=1)
    num_variables = num_blocks * width
    if width > 16 or num_variables > 2_000:
        raise ValueError("bounded-width path exceeds its safe profile")

    offsets = list(range(num_variables))
    stream.shuffle(offsets)
    variable_weights = tuple(weight_base + offset for offset in offsets)
    planted = tuple(stream.randbelow(2) for _ in range(num_variables))
    first_state = tuple(stream.randbelow(2) for _ in range(width))
    planted = tuple(first_state[position % width] for position in range(num_variables))
    logical_groups: list[list[tuple[tuple[int, int], ...]]] = []

    def make_clause(variables: tuple[int, ...]) -> tuple[tuple[int, int], ...]:
        literals = [(variable, stream.randbelow(2)) for variable in variables]
        if not any(planted[variable] == bit for variable, bit in literals):
            slot = stream.randbelow(len(literals))
            variable, _bit = literals[slot]
            literals[slot] = (variable, planted[variable])
        return tuple(literals)

    for block in range(num_blocks):
        variables = tuple(range(block * width, (block + 1) * width))
        clauses = []
        for position in range(width):
            clauses.append(
                make_clause(
                    (
                        variables[position],
                        variables[(position + 1) % width],
                        variables[(position + 2) % width],
                    )
                )
            )
        for _ in range(local_count):
            order = list(variables)
            stream.shuffle(order)
            clauses.append(make_clause(tuple(order[:3])))
        logical_groups.append(clauses)
    for block in range(num_blocks - 1):
        left = tuple(range(block * width, (block + 1) * width))
        right = tuple(range((block + 1) * width, (block + 2) * width))
        clauses = []
        for position in range(width):
            source = left[position]
            destination = right[position]
            for source_bit in (0, 1):
                clauses.append(
                    (
                        (source, 1 - source_bit),
                        (destination, source_bit),
                    )
                )
        for _ in range(boundary_count):
            left_order = list(left)
            right_order = list(right)
            stream.shuffle(left_order)
            stream.shuffle(right_order)
            clauses.append(make_clause(tuple(left_order[:2] + right_order[:2])))
        logical_groups.append(clauses)

    marker_weight = weight_base + num_variables + 1
    incidence: list[set[int]] = [set() for _ in range(2 * num_variables)]
    element = 0
    for variable in range(num_variables):
        incidence[2 * variable].add(element)
        incidence[2 * variable + 1].add(element)
        element += 1
    marker_indices: list[int] = []
    clause_count = 0
    for group in logical_groups:
        marker_index = len(incidence)
        marker_indices.append(marker_index)
        incidence.append({element})
        element += 1
        group_order = list(range(len(group)))
        stream.shuffle(group_order)
        for clause_index in group_order:
            clause = group[clause_index]
            for variable, bit in clause:
                incidence[2 * variable + bit].add(element)
            incidence[marker_index].add(element)
            element += 1
            clause_count += 1

    candidates = tuple(
        WeightedCandidate(
            frozenset(elements),
            variable_weights[index // 2] if index < 2 * num_variables else marker_weight,
        )
        for index, elements in enumerate(incidence)
    )
    reference = (
        *(2 * variable + planted[variable] for variable in range(num_variables)),
        *marker_indices,
    )
    return CaseBlueprint(
        universe_size=element,
        candidates=candidates,
        budget=sum(variable_weights) + marker_weight * len(marker_indices),
        reference_candidate_indices=reference,
        metadata={
            "mathematical_family": "marker_recoverable_bounded_width_boolean_path",
            "num_blocks": num_blocks,
            "block_width": width,
            "num_variables": num_variables,
            "num_markers": len(marker_indices),
            "num_clauses": clause_count,
            "optimality_certificate": "mandatory_marker_and_selector_lower_bound",
        },
    )


__all__ = ["CASE_ID", "DEFAULT_PARAMETERS", "build"]
