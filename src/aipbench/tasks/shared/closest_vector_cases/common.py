"""Shared primitives used by the current Merlin-Bench tasks."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from fractions import Fraction
from typing import Any, Final

MAX_SAFE_INTEGER: Final = 9_007_199_254_740_991

MAX_AMBIENT_DIMENSION: Final = 256

MAX_LATTICE_RANK: Final = 256

MAX_MATRIX_CELLS: Final = 65_536

IntegerMatrix = tuple[tuple[int, ...], ...]


def exact_matrix_rank(rows: Sequence[Sequence[int]]) -> int:
    """Return the rank over Q without floating-point arithmetic."""

    if not rows:
        return 0
    width = len(rows[0])
    if any(len(row) != width for row in rows):
        raise ValueError("matrix rows have inconsistent lengths")
    work = [[Fraction(value) for value in row] for row in rows]
    rank = 0
    for column in range(width):
        pivot = next(
            (row for row in range(rank, len(work)) if work[row][column] != 0),
            None,
        )
        if pivot is None:
            continue
        work[rank], work[pivot] = work[pivot], work[rank]
        pivot_value = work[rank][column]
        for row in range(rank + 1, len(work)):
            if work[row][column] == 0:
                continue
            factor = work[row][column] / pivot_value
            for index in range(column, width):
                work[row][index] -= factor * work[rank][index]
        rank += 1
        if rank == len(work):
            break
    return rank


def matrix_vector(rows: Sequence[Sequence[int]], vector: Sequence[int]) -> tuple[int, ...]:
    if any(len(row) != len(vector) for row in rows):
        raise ValueError("matrix-vector dimensions do not agree")
    return tuple(
        sum(entry * coefficient for entry, coefficient in zip(row, vector, strict=True))
        for row in rows
    )


def squared_distance_numerator(
    basis: Sequence[Sequence[int]],
    target_numerator: Sequence[int],
    denominator: int,
    coefficients: Sequence[int],
) -> int:
    point = matrix_vector(basis, coefficients)
    if len(point) != len(target_numerator):
        raise ValueError("target dimension does not agree with the basis")
    return sum(
        (denominator * coordinate - target_coordinate) ** 2
        for coordinate, target_coordinate in zip(point, target_numerator, strict=True)
    )


@dataclass(frozen=True)
class CaseBlueprint:
    """A canonical exact CVP instance before task-wide semantic hiding."""

    basis: IntegerMatrix
    target_numerator: tuple[int, ...]
    denominator: int
    radius_squared_numerator: int
    reference_coefficients: tuple[int, ...]
    metadata: Mapping[str, Any] = field(default_factory=dict)
