"""C04: a hidden Reed--Solomon Construction-A bounded-distance instance."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from aipbench.tasks.new_closest_vector_cases.common import (
    NewClosestVectorStream,
    integer_parameter,
)
from aipbench.tasks.shared.closest_vector_cases.common import CaseBlueprint

CASE_ID: Final = "c04"
DEFAULT_PARAMETERS: Final[Mapping[str, Any]] = {
    "code_length": 128,
    "code_dimension": 20,
    "modulus": 257,
    "num_errors": 32,
    "denominator": 5,
    "coefficient_magnitude": 7,
}


def build(stream: NewClosestVectorStream, parameters: Mapping[str, Any]) -> CaseBlueprint:
    code_length = integer_parameter(parameters, "code_length", minimum=4)
    code_dimension = integer_parameter(parameters, "code_dimension", minimum=1)
    modulus = integer_parameter(parameters, "modulus", minimum=5)
    num_errors = integer_parameter(parameters, "num_errors", minimum=1)
    denominator = integer_parameter(parameters, "denominator", minimum=3)
    coefficient_magnitude = integer_parameter(parameters, "coefficient_magnitude", minimum=1)
    if (
        code_length > 128
        or code_dimension >= code_length
        or code_length >= modulus
        or num_errors < code_dimension
        or 2 * num_errors > code_length - code_dimension
        or denominator != 5
        or coefficient_magnitude > 100
    ):
        raise ValueError("C04 parameters exceed the decodable correctness envelope")
    distance = code_length - code_dimension + 1
    radius = 4 * code_length + 5 * num_errors
    if 4 * radius >= denominator * denominator * distance:
        raise ValueError("C04 target is not inside the proved unique-decoding radius")

    basis_rows: list[tuple[int, ...]] = []
    for row, alpha in enumerate(range(1, code_length + 1)):
        dense = [pow(alpha, power, modulus) for power in range(code_dimension)]
        singleton = [0] * (code_length - code_dimension)
        if row >= code_dimension:
            singleton[row - code_dimension] = modulus
        basis_rows.append(tuple(dense + singleton))

    witness: list[int] = []
    for _ in range(code_length):
        value = stream.randint(-coefficient_magnitude, coefficient_magnitude)
        witness.append(value if value else stream.choice_sign())
    lattice_point = [
        sum(entry * coefficient for entry, coefficient in zip(row, witness, strict=True))
        for row in basis_rows
    ]
    error_order = list(range(code_dimension, code_length))
    stream.shuffle(error_order)
    error_set = set(range(code_dimension))
    error_set.update(error_order[: num_errors - code_dimension])
    target = tuple(
        denominator * coordinate + (-3 if row in error_set else 2)
        for row, coordinate in enumerate(lattice_point)
    )
    return CaseBlueprint(
        basis=tuple(basis_rows),
        target_numerator=target,
        denominator=denominator,
        radius_squared_numerator=radius,
        reference_coefficients=tuple(witness),
        metadata={
            "structure_family": "reed_solomon_construction_a_bdd",
            "code_length": code_length,
            "code_dimension": code_dimension,
            "modulus": modulus,
            "num_errors": num_errors,
            "code_distance": distance,
        },
    )


__all__ = ["CASE_ID", "DEFAULT_PARAMETERS", "build"]
