"""C02: a relabeled weighted cycle-cover instance."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Final

from aipbench.tasks.new_set_cover_cases.common import (
    CaseBlueprint,
    NewSetCoverStream,
    WeightedCandidate,
    integer_parameter,
)

CASE_ID: Final = "c02"
DEFAULT_PARAMETERS: Final[Mapping[str, Any]] = {
    "cycle_length": 3_072,
    "min_vertex_weight": 7,
    "max_vertex_weight": 41,
}


def minimum_weight_cycle_vertex_cover(weights: Sequence[int]) -> tuple[int, ...]:
    """Return an exact minimum-weight vertex cover of a cycle in linear time."""

    if len(weights) < 3 or any(
        isinstance(weight, bool) or not isinstance(weight, int) or weight <= 0 for weight in weights
    ):
        raise ValueError("cycle weights must be positive integers of length at least three")

    solutions: list[tuple[int, tuple[int, ...]]] = []
    for first in (0, 1):
        costs: dict[int, int] = {first: first * weights[0]}
        parents: list[dict[int, int]] = [{} for _ in weights]
        for index in range(1, len(weights)):
            next_costs: dict[int, int] = {}
            for current in (0, 1):
                choices = [
                    (cost + current * weights[index], previous)
                    for previous, cost in costs.items()
                    if previous or current
                ]
                if choices:
                    next_costs[current], parents[index][current] = min(choices)
            costs = next_costs
        final_cost, current = min((cost, last) for last, cost in costs.items() if last or first)
        bits = [0] * len(weights)
        bits[-1] = current
        for index in range(len(weights) - 1, 0, -1):
            bits[index - 1] = parents[index][bits[index]]
        solutions.append((final_cost, tuple(index for index, bit in enumerate(bits) if bit)))
    return min(solutions)[1]


def build(stream: NewSetCoverStream, parameters: Mapping[str, Any]) -> CaseBlueprint:
    cycle_length = integer_parameter(parameters, "cycle_length", minimum=3)
    min_weight = integer_parameter(parameters, "min_vertex_weight", minimum=1)
    max_weight = integer_parameter(parameters, "max_vertex_weight", minimum=1)
    if max_weight < min_weight:
        raise ValueError("maximum vertex weight must not be below the minimum")

    weights = tuple(
        min_weight + stream.randbelow(max_weight - min_weight + 1) for _ in range(cycle_length)
    )
    candidates = tuple(
        WeightedCandidate(
            frozenset({(vertex - 1) % cycle_length, vertex}),
            weights[vertex],
        )
        for vertex in range(cycle_length)
    )
    reference = minimum_weight_cycle_vertex_cover(weights)
    budget = sum(weights[index] for index in reference)
    return CaseBlueprint(
        universe_size=cycle_length,
        candidates=candidates,
        budget=budget,
        reference_candidate_indices=reference,
        metadata={
            "mathematical_family": "weighted_vertex_cover_on_a_cycle",
            "cycle_length": cycle_length,
            "optimality_certificate": "two_boundary_state_cycle_dynamic_program",
        },
    )


__all__ = [
    "CASE_ID",
    "DEFAULT_PARAMETERS",
    "build",
    "minimum_weight_cycle_vertex_cover",
]
