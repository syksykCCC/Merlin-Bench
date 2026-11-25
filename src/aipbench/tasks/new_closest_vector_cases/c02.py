"""C02: hidden signed path equations with an orthogonal residual."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from aipbench.tasks.new_closest_vector_cases.common import (
    NewClosestVectorStream,
    integer_parameter,
)
from aipbench.tasks.shared.closest_vector_cases.common import CaseBlueprint

CASE_ID: Final = "c02"
DEFAULT_PARAMETERS: Final[Mapping[str, Any]] = {
    "rank": 128,
    "minimum_scale": 7,
    "maximum_scale": 31,
    "coefficient_magnitude": 13,
    "residual_magnitude": 5,
}


def build(stream: NewClosestVectorStream, parameters: Mapping[str, Any]) -> CaseBlueprint:
    rank = integer_parameter(parameters, "rank", minimum=3)
    minimum_scale = integer_parameter(parameters, "minimum_scale", minimum=2)
    maximum_scale = integer_parameter(parameters, "maximum_scale", minimum=minimum_scale)
    coefficient_magnitude = integer_parameter(parameters, "coefficient_magnitude", minimum=1)
    residual_magnitude = integer_parameter(parameters, "residual_magnitude", minimum=1)
    if rank > 128 or maximum_scale > 10_000 or coefficient_magnitude > 1_000:
        raise ValueError("C02 parameters exceed the correctness envelope")

    witness = []
    for _ in range(rank):
        value = stream.randint(-coefficient_magnitude, coefficient_magnitude)
        witness.append(value if value != 0 else stream.choice_sign())

    diagonal = [stream.randint(minimum_scale, maximum_scale) for _ in range(rank)]
    coupling = [
        stream.choice_sign() * stream.randint(minimum_scale, maximum_scale) for _ in range(rank - 1)
    ]
    equation_rows: list[tuple[int, ...]] = []
    anchor = [0] * rank
    anchor[0] = diagonal[0]
    equation_rows.append(tuple(anchor))
    for index in range(1, rank):
        row = [0] * rank
        row[index - 1] = coupling[index - 1]
        row[index] = diagonal[index]
        equation_rows.append(tuple(row))

    residual = [stream.choice_sign() * stream.randint(1, residual_magnitude) for _ in range(rank)]
    equation_target = tuple(
        sum(entry * coefficient for entry, coefficient in zip(row, witness, strict=True))
        for row in equation_rows
    )
    target = equation_target + tuple(residual)
    radius = sum(value * value for value in residual)
    return CaseBlueprint(
        basis=tuple(equation_rows) + ((0,) * rank,) * rank,
        target_numerator=target,
        denominator=1,
        radius_squared_numerator=radius,
        reference_coefficients=tuple(witness),
        metadata={
            "structure_family": "hidden_signed_path_equations",
            "equation_rows": rank,
            "residual_coordinates": rank,
        },
    )


__all__ = ["CASE_ID", "DEFAULT_PARAMETERS", "build"]
