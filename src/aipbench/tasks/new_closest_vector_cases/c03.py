"""C03: paired-residual equations on a hidden low-width tree."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from aipbench.tasks.new_closest_vector_cases.common import (
    NewClosestVectorStream,
    integer_parameter,
)
from aipbench.tasks.shared.closest_vector_cases.common import CaseBlueprint

CASE_ID: Final = "c03"
DEFAULT_PARAMETERS: Final[Mapping[str, Any]] = {
    "rank": 128,
    "branching_factor": 3,
    "minimum_scale": 17,
    "maximum_scale": 43,
    "coefficient_magnitude": 15,
    "residual_magnitude": 7,
}


def build(stream: NewClosestVectorStream, parameters: Mapping[str, Any]) -> CaseBlueprint:
    rank = integer_parameter(parameters, "rank", minimum=4)
    branching_factor = integer_parameter(parameters, "branching_factor", minimum=2)
    minimum_scale = integer_parameter(parameters, "minimum_scale", minimum=2)
    maximum_scale = integer_parameter(parameters, "maximum_scale", minimum=minimum_scale)
    coefficient_magnitude = integer_parameter(parameters, "coefficient_magnitude", minimum=1)
    residual_magnitude = integer_parameter(parameters, "residual_magnitude", minimum=1)
    if rank > 128 or branching_factor > 8 or maximum_scale > 10_000:
        raise ValueError("C03 parameters exceed the correctness envelope")

    witness: list[int] = []
    for _ in range(rank):
        value = stream.randint(-coefficient_magnitude, coefficient_magnitude)
        witness.append(value if value else stream.choice_sign())

    equation_rows: list[tuple[int, ...]] = []
    for node in range(rank):
        row = [0] * rank
        row[node] = stream.randint(minimum_scale, maximum_scale)
        if node:
            parent = (node - 1) // branching_factor
            row[parent] = stream.choice_sign() * stream.randint(minimum_scale, maximum_scale)
            if parent:
                grandparent = (parent - 1) // branching_factor
                row[grandparent] = stream.choice_sign() * stream.randint(
                    minimum_scale, maximum_scale
                )
        equation_rows.append(tuple(row))

    paired_rows: list[tuple[int, ...]] = []
    paired_target: list[int] = []
    residuals: list[int] = []
    for row in equation_rows:
        equation_value = sum(
            entry * coefficient for entry, coefficient in zip(row, witness, strict=True)
        )
        residual = stream.randint(1, residual_magnitude)
        residuals.append(residual)
        paired_rows.extend((row, row))
        paired_target.extend((equation_value + residual, equation_value - residual))

    return CaseBlueprint(
        basis=tuple(paired_rows),
        target_numerator=tuple(paired_target),
        denominator=1,
        radius_squared_numerator=2 * sum(value * value for value in residuals),
        reference_coefficients=tuple(witness),
        metadata={
            "structure_family": "paired_residual_low_width_tree",
            "branching_factor": branching_factor,
            "equation_rows": rank,
            "paired_rows": 2 * rank,
        },
    )


__all__ = ["CASE_ID", "DEFAULT_PARAMETERS", "build"]
