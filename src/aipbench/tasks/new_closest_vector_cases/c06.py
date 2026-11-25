"""C06: hidden Boolean-cube Reed--Muller Construction-A lattice."""

from __future__ import annotations

from collections.abc import Mapping
from itertools import combinations, product
from math import comb
from typing import Any, Final

from aipbench.tasks.new_closest_vector_cases.common import (
    NewClosestVectorStream,
    integer_parameter,
)
from aipbench.tasks.shared.closest_vector_cases.common import CaseBlueprint

CASE_ID: Final = "c06"
DEFAULT_PARAMETERS: Final[Mapping[str, Any]] = {
    "cube_dimension": 8,
    "degree": 3,
    "modulus": 257,
    "num_errors": 15,
    "denominator": 13,
    "clean_offset": 1,
    "error_offset": -7,
    "coefficient_magnitude": 7,
    "kernel_shear_layers": 28,
    "kernel_injections_per_code_column": 8,
}


def _monomials(cube_dimension: int, degree: int) -> list[tuple[int, ...]]:
    return [
        subset for size in range(degree + 1) for subset in combinations(range(cube_dimension), size)
    ]


def _evaluation_row(point: tuple[int, ...], monomials: list[tuple[int, ...]]) -> list[int]:
    return [int(all(point[axis] for axis in monomial)) for monomial in monomials]


def _information_first_points(
    *, cube_dimension: int, monomials: list[tuple[int, ...]], modulus: int
) -> list[tuple[int, ...]]:
    all_points = list(product((0, 1), repeat=cube_dimension))
    pivots: dict[int, list[int]] = {}
    selected: list[tuple[int, ...]] = []
    for point in all_points:
        residual = _evaluation_row(point, monomials)
        for pivot in sorted(pivots):
            if residual[pivot] == 0:
                continue
            factor = residual[pivot]
            residual = [
                (left - factor * right) % modulus
                for left, right in zip(residual, pivots[pivot], strict=True)
            ]
        pivot = next((index for index, value in enumerate(residual) if value), None)
        if pivot is None:
            continue
        inverse = pow(residual[pivot], -1, modulus)
        pivots[pivot] = [(value * inverse) % modulus for value in residual]
        selected.append(point)
        if len(selected) == len(monomials):
            break
    if len(selected) != len(monomials):
        raise RuntimeError("C06 Boolean evaluation code lacks a full information set")
    selected_set = set(selected)
    return selected + [point for point in all_points if point not in selected_set]


def _mix_columns(
    stream: NewClosestVectorStream,
    basis_rows: list[list[int]],
    *,
    dimension: int,
    shear_layers: int,
    injections_per_code_column: int,
) -> None:
    rank = len(basis_rows[0])
    kernel_columns = list(range(dimension, rank))
    for _ in range(shear_layers):
        order = list(kernel_columns)
        stream.shuffle(order)
        for offset in range(0, len(order) - 1, 2):
            source, target = order[offset : offset + 2]
            factor = stream.choice_sign()
            for row in basis_rows:
                row[target] += factor * row[source]
    for target in range(dimension):
        for _ in range(injections_per_code_column):
            source = kernel_columns[stream.randbelow(len(kernel_columns))]
            factor = stream.choice_sign()
            for row in basis_rows:
                row[target] += factor * row[source]


def build(stream: NewClosestVectorStream, parameters: Mapping[str, Any]) -> CaseBlueprint:
    cube_dimension = integer_parameter(parameters, "cube_dimension", minimum=3)
    degree = integer_parameter(parameters, "degree", minimum=1)
    modulus = integer_parameter(parameters, "modulus", minimum=5)
    num_errors = integer_parameter(parameters, "num_errors", minimum=1)
    denominator = integer_parameter(parameters, "denominator", minimum=3)
    clean_offset = parameters.get("clean_offset")
    error_offset = parameters.get("error_offset")
    coefficient_magnitude = integer_parameter(parameters, "coefficient_magnitude", minimum=1)
    shear_layers = integer_parameter(parameters, "kernel_shear_layers", minimum=1)
    injections = integer_parameter(parameters, "kernel_injections_per_code_column", minimum=1)
    if (
        isinstance(clean_offset, bool)
        or not isinstance(clean_offset, int)
        or isinstance(error_offset, bool)
        or not isinstance(error_offset, int)
    ):
        raise ValueError("C06 offsets must be integers")
    rank = 1 << cube_dimension
    dimension = sum(comb(cube_dimension, size) for size in range(degree + 1))
    code_distance = 1 << (cube_dimension - degree)
    decoding_radius = (code_distance - 1) // 2
    if (
        rank > 256
        or degree >= cube_dimension
        or modulus <= rank
        or dimension >= rank
        or num_errors > decoding_radius
        or abs(2 * clean_offset) >= denominator
        or abs(2 * error_offset) <= denominator
        or coefficient_magnitude > 100
        or shear_layers > 64
        or injections > 16
    ):
        raise ValueError("C06 parameters exceed the proved decoding envelope")
    radius = (rank - num_errors) * clean_offset**2 + num_errors * error_offset**2
    if 4 * radius >= denominator * denominator * code_distance:
        raise ValueError("C06 target is not inside the proved unique-decoding radius")

    monomials = _monomials(cube_dimension, degree)
    points = _information_first_points(
        cube_dimension=cube_dimension, monomials=monomials, modulus=modulus
    )
    basis_rows: list[list[int]] = []
    for row, point in enumerate(points):
        code = _evaluation_row(point, monomials)
        kernel = [0] * (rank - dimension)
        if row >= dimension:
            kernel[row - dimension] = modulus
        basis_rows.append(code + kernel)
    _mix_columns(
        stream,
        basis_rows,
        dimension=dimension,
        shear_layers=shear_layers,
        injections_per_code_column=injections,
    )

    witness = []
    for _ in range(rank):
        value = stream.randint(-coefficient_magnitude, coefficient_magnitude)
        witness.append(value if value else stream.choice_sign())
    lattice_point = [
        sum(entry * coefficient for entry, coefficient in zip(row, witness, strict=True))
        for row in basis_rows
    ]
    error_points = set(points[:num_errors])
    target = tuple(
        denominator * lattice_point[row] + (error_offset if point in error_points else clean_offset)
        for row, point in enumerate(points)
    )
    return CaseBlueprint(
        basis=tuple(tuple(row) for row in basis_rows),
        target_numerator=target,
        denominator=denominator,
        radius_squared_numerator=radius,
        reference_coefficients=tuple(witness),
        metadata={
            "structure_family": "boolean_reed_muller_construction_a_bdd",
            "cube_dimension": cube_dimension,
            "degree": degree,
            "modulus": modulus,
            "num_errors": num_errors,
            "code_distance": code_distance,
            "full_rank_certificate_prime": 1_000_000_007,
        },
    )


__all__ = ["CASE_ID", "DEFAULT_PARAMETERS", "build"]
