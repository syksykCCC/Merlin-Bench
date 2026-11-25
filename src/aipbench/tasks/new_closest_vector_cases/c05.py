"""C05: hidden tensor-product evaluation Construction-A lattice."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from aipbench.tasks.new_closest_vector_cases.common import (
    NewClosestVectorStream,
    integer_parameter,
)
from aipbench.tasks.shared.closest_vector_cases.common import CaseBlueprint

CASE_ID: Final = "c05"
DEFAULT_PARAMETERS: Final[Mapping[str, Any]] = {
    "grid_size": 16,
    "component_dimension": 12,
    "modulus": 257,
    "num_errors": 16,
    "denominator": 13,
    "clean_offset": 1,
    "error_offset": -7,
    "coefficient_magnitude": 7,
}


def _logical_points(grid_size: int, component_dimension: int) -> list[tuple[int, int]]:
    systematic = [
        (left, right)
        for left in range(1, component_dimension + 1)
        for right in range(1, component_dimension + 1)
    ]
    remaining = [
        (left, right)
        for left in range(1, grid_size + 1)
        for right in range(1, grid_size + 1)
        if (left, right) not in set(systematic)
    ]
    return systematic + remaining


def _error_points(
    stream: NewClosestVectorStream,
    *,
    grid_size: int,
    component_dimension: int,
    num_errors: int,
) -> set[tuple[int, int]]:
    del component_dimension
    errors: set[tuple[int, int]] = set()
    remaining = num_errors
    left_order = list(range(1, grid_size + 1))
    right_order = list(range(1, grid_size + 1))
    stream.shuffle(left_order)
    stream.shuffle(right_order)
    shift = 0
    while remaining:
        progress = False
        for index, left in enumerate(left_order):
            if remaining == 0:
                break
            right = right_order[(index + shift) % len(right_order)]
            edge = (left, right)
            if edge in errors:
                continue
            errors.add(edge)
            remaining -= 1
            progress = True
        shift += 1
        if not progress or shift > grid_size:
            raise ValueError("C05 error pattern cannot satisfy the degree envelope")
    return errors


def _mix_columns(
    stream: NewClosestVectorStream,
    basis_rows: list[list[int]],
    *,
    dimension: int,
    component_dimension: int,
) -> None:
    """Apply bounded determinant-one shears while preserving quotient landmarks."""

    rank = len(basis_rows[0])
    protected = {0, 1, component_dimension}

    def shear_layers(columns: list[int], layers: int) -> None:
        for _ in range(layers):
            order = list(columns)
            stream.shuffle(order)
            for offset in range(0, len(order) - 1, 2):
                source, target = order[offset : offset + 2]
                factor = stream.choice_sign()
                for row in basis_rows:
                    row[target] += factor * row[source]

    shear_layers([column for column in range(dimension) if column not in protected], 18)
    shear_layers(list(range(dimension, rank)), 18)
    kernel_columns = list(range(dimension, rank))
    for target in range(dimension):
        for _ in range(3):
            source = kernel_columns[stream.randbelow(len(kernel_columns))]
            factor = stream.choice_sign()
            for row in basis_rows:
                row[target] += factor * row[source]


def build(stream: NewClosestVectorStream, parameters: Mapping[str, Any]) -> CaseBlueprint:
    grid_size = integer_parameter(parameters, "grid_size", minimum=4)
    component_dimension = integer_parameter(parameters, "component_dimension", minimum=1)
    modulus = integer_parameter(parameters, "modulus", minimum=5)
    num_errors = integer_parameter(parameters, "num_errors", minimum=1)
    denominator = integer_parameter(parameters, "denominator", minimum=3)
    clean_offset = parameters.get("clean_offset")
    error_offset = parameters.get("error_offset")
    coefficient_magnitude = integer_parameter(parameters, "coefficient_magnitude", minimum=1)
    if (
        isinstance(clean_offset, bool)
        or not isinstance(clean_offset, int)
        or isinstance(error_offset, bool)
        or not isinstance(error_offset, int)
    ):
        raise ValueError("C05 offsets must be integers")
    component_distance = grid_size - component_dimension + 1
    component_radius = (component_distance - 1) // 2
    rank = grid_size * grid_size
    dimension = component_dimension * component_dimension
    if (
        rank > 256
        or component_dimension >= grid_size
        or grid_size >= modulus
        or num_errors > grid_size * component_radius
        or abs(2 * clean_offset) >= denominator
        or abs(2 * error_offset) <= denominator
        or coefficient_magnitude > 100
    ):
        raise ValueError("C05 parameters exceed the decodable correctness envelope")
    code_distance = component_distance * component_distance
    radius = (rank - num_errors) * clean_offset**2 + num_errors * error_offset**2
    if 4 * radius >= denominator * denominator * code_distance:
        raise ValueError("C05 target is not inside the proved unique-decoding radius")

    points = _logical_points(grid_size, component_dimension)
    basis_rows: list[list[int]] = []
    monomials = [
        (left_power, right_power)
        for left_power in range(component_dimension)
        for right_power in range(component_dimension)
    ]
    for row, (left, right) in enumerate(points):
        dense = [
            pow(left, left_power, modulus) * pow(right, right_power, modulus) % modulus
            for left_power, right_power in monomials
        ]
        singleton = [0] * (rank - dimension)
        if row >= dimension:
            singleton[row - dimension] = modulus
        basis_rows.append(dense + singleton)

    _mix_columns(
        stream,
        basis_rows,
        dimension=dimension,
        component_dimension=component_dimension,
    )

    witness: list[int] = []
    for _ in range(rank):
        value = stream.randint(-coefficient_magnitude, coefficient_magnitude)
        witness.append(value if value else stream.choice_sign())
    lattice_point = [
        sum(entry * coefficient for entry, coefficient in zip(row, witness, strict=True))
        for row in basis_rows
    ]
    errors = _error_points(
        stream,
        grid_size=grid_size,
        component_dimension=component_dimension,
        num_errors=num_errors,
    )
    if any(
        sum((left, right) in errors for right in range(1, grid_size + 1)) > component_radius
        for left in range(1, grid_size + 1)
    ):
        raise RuntimeError("C05 row error radius was exceeded")
    target = tuple(
        denominator * lattice_point[row] + (error_offset if point in errors else clean_offset)
        for row, point in enumerate(points)
    )
    return CaseBlueprint(
        basis=tuple(tuple(row) for row in basis_rows),
        target_numerator=target,
        denominator=denominator,
        radius_squared_numerator=radius,
        reference_coefficients=tuple(witness),
        metadata={
            "structure_family": "tensor_evaluation_construction_a_bdd",
            "grid_size": grid_size,
            "component_dimension": component_dimension,
            "modulus": modulus,
            "num_errors": num_errors,
            "code_distance": code_distance,
            "full_rank_certificate_prime": 1_000_000_007,
        },
    )


__all__ = ["CASE_ID", "DEFAULT_PARAMETERS", "build"]
