"""C01: disjoint weighted group calibration."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from aipbench.tasks.new_set_cover_cases.common import (
    CaseBlueprint,
    NewSetCoverStream,
    WeightedCandidate,
    integer_parameter,
)

CASE_ID: Final = "c01"
DEFAULT_PARAMETERS: Final[Mapping[str, Any]] = {
    "num_groups": 24,
    "elements_per_group": 6,
    "decoys_per_group": 8,
    "min_group_weight": 5,
    "max_group_weight": 17,
}


def build(stream: NewSetCoverStream, parameters: Mapping[str, Any]) -> CaseBlueprint:
    num_groups = integer_parameter(parameters, "num_groups", minimum=2)
    group_size = integer_parameter(parameters, "elements_per_group", minimum=3)
    decoys_per_group = integer_parameter(parameters, "decoys_per_group", minimum=1)
    min_weight = integer_parameter(parameters, "min_group_weight", minimum=1)
    max_weight = integer_parameter(parameters, "max_group_weight", minimum=1)
    if max_weight < min_weight or decoys_per_group > (1 << group_size) - 2:
        raise ValueError("invalid group calibration parameters")

    candidates: list[WeightedCandidate] = []
    reference: list[int] = []
    budget = 0
    for group in range(num_groups):
        elements = tuple(range(group * group_size, (group + 1) * group_size))
        group_weight = min_weight + stream.randbelow(max_weight - min_weight + 1)
        reference.append(len(candidates))
        candidates.append(WeightedCandidate(frozenset(elements), group_weight))
        budget += group_weight

        proper_subsets = [mask for mask in range(1, (1 << group_size) - 1)]
        stream.shuffle(proper_subsets)
        for mask in proper_subsets[:decoys_per_group]:
            subset = frozenset(
                elements[position] for position in range(group_size) if (mask >> position) & 1
            )
            candidates.append(
                WeightedCandidate(subset, group_weight + 1 + stream.randbelow(group_weight + 1))
            )

    return CaseBlueprint(
        universe_size=num_groups * group_size,
        candidates=tuple(candidates),
        budget=budget,
        reference_candidate_indices=tuple(reference),
        metadata={
            "mathematical_family": "disjoint_weighted_group_calibration",
            "num_groups": num_groups,
            "elements_per_group": group_size,
            "decoys_per_group": decoys_per_group,
            "unique_optimum": True,
            "optimality_certificate": "independent_group_weight_lower_bounds",
        },
    )


__all__ = ["CASE_ID", "DEFAULT_PARAMETERS", "build"]
