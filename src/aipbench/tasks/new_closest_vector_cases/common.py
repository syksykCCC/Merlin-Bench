"""Independent generation primitives for New Structured Closest Vector."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Final

from aipbench.tasks.shared.closest_vector_cases.common import (
    CaseBlueprint,
    exact_matrix_rank,
    squared_distance_numerator,
)

MAX_SAFE_INTEGER: Final = 9_007_199_254_740_991
_MAX_REJECTION_SAMPLES: Final = 128


class NewClosestVectorStream:
    """Deterministic stream with a task-specific domain."""

    _DOMAIN: Final = b"aipbench/new-structured-closest-vector/generator/v1\x00"

    def __init__(self, seed: bytes) -> None:
        self._seed = bytes(seed)
        self._counter = 0
        self._buffer = bytearray()

    def _refill(self) -> None:
        self._buffer.extend(
            hashlib.sha256(
                self._DOMAIN
                + len(self._seed).to_bytes(8, "big")
                + self._seed
                + self._counter.to_bytes(16, "big")
            ).digest()
        )
        self._counter += 1

    def take(self, length: int) -> bytes:
        if length < 0:
            raise ValueError("length must be non-negative")
        while len(self._buffer) < length:
            self._refill()
        result = bytes(self._buffer[:length])
        del self._buffer[:length]
        return result

    def randbelow(self, upper_exclusive: int) -> int:
        if upper_exclusive <= 0:
            raise ValueError("upper_exclusive must be positive")
        width = max(1, (upper_exclusive.bit_length() + 7) // 8)
        sample_space = 1 << (8 * width)
        rejection_limit = sample_space - sample_space % upper_exclusive
        for _ in range(_MAX_REJECTION_SAMPLES):
            candidate = int.from_bytes(self.take(width), "big")
            if candidate < rejection_limit:
                return candidate % upper_exclusive
        return int.from_bytes(self.take(width), "big") % upper_exclusive

    def randint(self, lower: int, upper: int) -> int:
        if lower > upper:
            raise ValueError("lower must not exceed upper")
        return lower + self.randbelow(upper - lower + 1)

    def choice_sign(self) -> int:
        return -1 if self.randbelow(2) == 0 else 1

    def shuffle(self, values: list[Any]) -> None:
        for index in range(len(values) - 1, 0, -1):
            other = self.randbelow(index + 1)
            values[index], values[other] = values[other], values[index]


def integer_parameter(parameters: Mapping[str, Any], name: str, *, minimum: int) -> int:
    value = parameters.get(name)
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"case parameter {name!r} must be an integer >= {minimum}")
    return value


def _has_full_column_rank_modulo(
    rows: tuple[tuple[int, ...], ...] | list[list[int]], modulus: int
) -> bool:
    """Certify rational full column rank through one finite-field minor."""

    if not rows or modulus <= 2:
        return False
    width = len(rows[0])
    work = [[value % modulus for value in row] for row in rows]
    pivot_row = 0
    for column in range(width):
        pivot = next(
            (row for row in range(pivot_row, len(work)) if work[row][column]),
            None,
        )
        if pivot is None:
            return False
        work[pivot_row], work[pivot] = work[pivot], work[pivot_row]
        inverse = pow(work[pivot_row][column], -1, modulus)
        for row in range(pivot_row + 1, len(work)):
            if work[row][column] == 0:
                continue
            factor = work[row][column] * inverse % modulus
            work[row][column:] = [
                (left - factor * right) % modulus
                for left, right in zip(work[row][column:], work[pivot_row][column:], strict=True)
            ]
        pivot_row += 1
    return True


@dataclass(frozen=True)
class FinalizedCase:
    public_instance: Mapping[str, Any]
    private_instance: Mapping[str, Any]
    generation_metadata: Mapping[str, Any]


def finalize_blueprint(
    *, blueprint: CaseBlueprint, stream: NewClosestVectorStream
) -> FinalizedCase:
    """Validate and hide a calibration blueprint with exact isometries."""

    basis = blueprint.basis
    if not basis or not basis[0]:
        raise ValueError("basis must be nonempty")
    ambient_dimension = len(basis)
    rank = len(basis[0])
    if ambient_dimension > 256 or rank > 256 or ambient_dimension * rank > 65_536:
        raise ValueError("basis exceeds the public matrix envelope")
    certificate_prime = blueprint.metadata.get("full_rank_certificate_prime")
    if certificate_prime is not None and (
        isinstance(certificate_prime, bool)
        or not isinstance(certificate_prime, int)
        or certificate_prime <= 2
    ):
        raise ValueError("full-rank certificate prime is malformed")
    rank_is_full = (
        _has_full_column_rank_modulo(basis, certificate_prime)
        if certificate_prime is not None
        else exact_matrix_rank(basis) == rank
    )
    if any(len(row) != rank for row in basis) or not rank_is_full:
        raise ValueError("basis must be rectangular and full-column-rank")
    if len(blueprint.target_numerator) != ambient_dimension:
        raise ValueError("target has the wrong dimension")
    if len(blueprint.reference_coefficients) != rank:
        raise ValueError("reference has the wrong dimension")
    values = [value for row in basis for value in row]
    values.extend(blueprint.target_numerator)
    values.extend(blueprint.reference_coefficients)
    if any(isinstance(value, bool) or not isinstance(value, int) for value in values):
        raise ValueError("blueprint values must be integers")
    if any(abs(value) > MAX_SAFE_INTEGER for value in values):
        raise ValueError("blueprint values exceed the JSON safe-integer envelope")
    if not 1 <= blueprint.denominator <= MAX_SAFE_INTEGER:
        raise ValueError("denominator is outside the public envelope")
    if not 0 <= blueprint.radius_squared_numerator <= MAX_SAFE_INTEGER:
        raise ValueError("radius is outside the public envelope")

    canonical_distance = squared_distance_numerator(
        basis,
        blueprint.target_numerator,
        blueprint.denominator,
        blueprint.reference_coefficients,
    )
    if canonical_distance != blueprint.radius_squared_numerator:
        raise ValueError("calibration reference must attain the exact radius")

    row_order = list(range(ambient_dimension))
    column_order = list(range(rank))
    stream.shuffle(row_order)
    stream.shuffle(column_order)
    row_signs = [stream.choice_sign() for _ in row_order]
    column_signs = [stream.choice_sign() for _ in column_order]
    public_basis = [
        [
            row_signs[public_row]
            * column_signs[public_column]
            * basis[canonical_row][canonical_column]
            for public_column, canonical_column in enumerate(column_order)
        ]
        for public_row, canonical_row in enumerate(row_order)
    ]
    public_target = [
        row_signs[public_row] * blueprint.target_numerator[canonical_row]
        for public_row, canonical_row in enumerate(row_order)
    ]
    public_reference = [
        column_signs[public_column] * blueprint.reference_coefficients[canonical_column]
        for public_column, canonical_column in enumerate(column_order)
    ]
    public_distance = squared_distance_numerator(
        public_basis,
        public_target,
        blueprint.denominator,
        public_reference,
    )
    public_rank_is_full = (
        _has_full_column_rank_modulo(public_basis, certificate_prime)
        if certificate_prime is not None
        else exact_matrix_rank(public_basis) == rank
    )
    if public_distance != canonical_distance or not public_rank_is_full:
        raise RuntimeError("semantic hiding did not preserve the exact relation")
    coefficient_bound = max(32, max(abs(value) for value in public_reference) + 8)
    return FinalizedCase(
        public_instance={
            "format_version": "aip-structured-closest-vector-instance/1",
            "ambient_dimension": ambient_dimension,
            "rank": rank,
            "basis": public_basis,
            "target_numerator": public_target,
            "denominator": blueprint.denominator,
            "radius_squared_numerator": blueprint.radius_squared_numerator,
            "coefficient_bound": coefficient_bound,
        },
        private_instance={
            "reference_coefficients": public_reference,
            "reference_distance_numerator": public_distance,
        },
        generation_metadata={
            "ambient_dimension": ambient_dimension,
            "rank": rank,
            "denominator": blueprint.denominator,
            "reference_distance_numerator": public_distance,
            "correctness_scaled": True,
            **dict(blueprint.metadata),
        },
    )


__all__ = [
    "FinalizedCase",
    "NewClosestVectorStream",
    "finalize_blueprint",
    "integer_parameter",
]
