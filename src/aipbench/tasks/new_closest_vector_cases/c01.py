"""C01: orthogonal residual calibration."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from aipbench.tasks.new_closest_vector_cases.common import (
    NewClosestVectorStream,
    integer_parameter,
)
from aipbench.tasks.shared.closest_vector_cases.common import CaseBlueprint

CASE_ID: Final = "c01"
DEFAULT_PARAMETERS: Final[Mapping[str, Any]] = {
    "rank": 24,
    "minimum_scale": 11,
    "maximum_scale": 29,
    "coefficient_magnitude": 9,
    "residual_magnitude": 3,
}


def build(stream: NewClosestVectorStream, parameters: Mapping[str, Any]) -> CaseBlueprint:
    rank = integer_parameter(parameters, "rank", minimum=2)
    minimum_scale = integer_parameter(parameters, "minimum_scale", minimum=2)
    maximum_scale = integer_parameter(parameters, "maximum_scale", minimum=minimum_scale)
    coefficient_magnitude = integer_parameter(parameters, "coefficient_magnitude", minimum=2)
    residual_magnitude = integer_parameter(parameters, "residual_magnitude", minimum=1)
    if rank > 128 or maximum_scale > 10_000 or coefficient_magnitude > 1_000:
        raise ValueError("C01 parameters exceed the correctness envelope")

    scales = [stream.randint(minimum_scale, maximum_scale) for _ in range(rank)]
    witness = []
    for _ in range(rank):
        value = stream.randint(-coefficient_magnitude, coefficient_magnitude)
        witness.append(value if value != 0 else stream.choice_sign())
    residual = [stream.choice_sign() * stream.randint(1, residual_magnitude) for _ in range(rank)]
    basis_rows = [
        tuple(scale if row == column else 0 for column, scale in enumerate(scales))
        for row in range(rank)
    ]
    basis_rows.extend((0,) * rank for _ in range(rank))
    target = tuple(scales[index] * witness[index] for index in range(rank)) + tuple(residual)
    radius = sum(value * value for value in residual)
    return CaseBlueprint(
        basis=tuple(basis_rows),
        target_numerator=target,
        denominator=1,
        radius_squared_numerator=radius,
        reference_coefficients=tuple(witness),
        metadata={
            "structure_family": "orthogonal_residual_calibration",
            "pivot_scales": tuple(scales),
            "residual_coordinates": rank,
        },
    )


__all__ = ["CASE_ID", "DEFAULT_PARAMETERS", "build"]
