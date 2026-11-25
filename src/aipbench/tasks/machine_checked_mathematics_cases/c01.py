"""C01: a full-rank binary linear system with a kernel-checked solution."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Final

from aipbench.tasks.machine_checked_mathematics_cases.common import (
    DeterministicStream,
    LeanCaseBlueprint,
    challenge_source,
    integer_parameter,
)

CASE_ID: Final = "c01"
TITLE: Final = "Dense binary linear certificate"
DEFAULT_PARAMETERS: Final[Mapping[str, Any]] = {"dimension": 80}


def _row_mask(row: Sequence[Any], dimension: int) -> int:
    mask = 0
    seen: set[int] = set()
    for raw_column in row:
        if isinstance(raw_column, bool) or not isinstance(raw_column, int):
            raise ValueError("binary-system column indices must be integers")
        column = int(raw_column)
        if column < 0 or column >= dimension or column in seen:
            raise ValueError("binary-system rows must contain distinct in-range columns")
        seen.add(column)
        mask |= 1 << column
    return mask


def _solve_masks(row_masks: Sequence[int], rhs: Sequence[Any], dimension: int) -> tuple[int, ...]:
    """Solve a square full-rank system over GF(2) by public row reduction."""

    if len(row_masks) != dimension or len(rhs) != dimension:
        raise ValueError("binary system must be square")
    augmented: list[int] = []
    for mask, raw_value in zip(row_masks, rhs, strict=True):
        if isinstance(raw_value, bool) or not isinstance(raw_value, int) or raw_value not in (0, 1):
            raise ValueError("binary-system right-hand sides must be bits")
        if mask < 0 or mask >= 1 << dimension:
            raise ValueError("binary-system row mask is out of range")
        augmented.append(mask | (raw_value << dimension))

    pivot_rows = [-1] * dimension
    rank = 0
    for column in range(dimension):
        pivot = next(
            (row for row in range(rank, dimension) if (augmented[row] >> column) & 1),
            None,
        )
        if pivot is None:
            continue
        augmented[rank], augmented[pivot] = augmented[pivot], augmented[rank]
        for row in range(dimension):
            if row != rank and ((augmented[row] >> column) & 1):
                augmented[row] ^= augmented[rank]
        pivot_rows[column] = rank
        rank += 1
    if rank != dimension:
        raise ValueError("binary system is not full rank")

    solution = tuple(
        (augmented[pivot_rows[column]] >> dimension) & 1 for column in range(dimension)
    )
    solution_mask = sum(bit << column for column, bit in enumerate(solution))
    for mask, value in zip(row_masks, rhs, strict=True):
        if (mask & solution_mask).bit_count() % 2 != value:
            raise AssertionError("row reduction produced an invalid binary solution")
    return solution


def solve(problem: Mapping[str, Any]) -> tuple[int, ...]:
    raw_dimension = problem["dimension"]
    if isinstance(raw_dimension, bool) or not isinstance(raw_dimension, int):
        raise ValueError("binary-system dimension must be an integer")
    dimension = raw_dimension
    raw_rows = problem["rows"]
    raw_rhs = problem["rhs"]
    if not isinstance(raw_rows, Sequence) or isinstance(raw_rows, (str, bytes)):
        raise ValueError("binary-system rows must be a sequence")
    if not isinstance(raw_rhs, Sequence) or isinstance(raw_rhs, (str, bytes)):
        raise ValueError("binary-system right-hand side must be a sequence")
    row_masks = tuple(_row_mask(row, dimension) for row in raw_rows)
    return _solve_masks(row_masks, tuple(raw_rhs), dimension)


def _random_full_rank_masks(stream: DeterministicStream, dimension: int) -> tuple[int, ...]:
    # Form A = L*U over GF(2), where both triangular factors have unit
    # diagonal.  Independent row and column permutations remove the visible
    # triangular order without weakening the full-rank guarantee.
    upper: list[int] = []
    for row in range(dimension):
        mask = 1 << row
        for column in range(row + 1, dimension):
            if stream.randbelow(2):
                mask |= 1 << column
        upper.append(mask)

    product: list[int] = []
    for row in range(dimension):
        mask = upper[row]
        for factor_row in range(row):
            if stream.randbelow(2):
                mask ^= upper[factor_row]
        product.append(mask)

    stream.shuffle(product)
    column_permutation = list(range(dimension))
    stream.shuffle(column_permutation)
    permuted = tuple(
        sum(1 << column_permutation[column] for column in range(dimension) if (mask >> column) & 1)
        for mask in product
    )
    # This assertion audits the encoding while generation is still trusted;
    # the public solver below does not know or use either triangular factor.
    _solve_masks(permuted, (0,) * dimension, dimension)
    return permuted


def _lean_rows(rows: Sequence[Sequence[int]]) -> str:
    return (
        "[\n    "
        + ",\n    ".join("[" + ", ".join(str(column) for column in row) + "]" for row in rows)
        + "\n  ]"
    )


def build(stream: DeterministicStream, parameters: Mapping[str, Any]) -> LeanCaseBlueprint:
    dimension = integer_parameter(parameters, "dimension", minimum=6, maximum=128)
    row_masks = _random_full_rank_masks(stream, dimension)
    rows = tuple(
        tuple(column for column in range(dimension) if (mask >> column) & 1) for mask in row_masks
    )

    while True:
        planted = tuple(stream.randbelow(2) for _ in range(dimension))
        weight = sum(planted)
        if dimension // 3 <= weight <= (2 * dimension) // 3:
            break
    solution_mask = sum(bit << column for column, bit in enumerate(planted))
    rhs = tuple((mask & solution_mask).bit_count() % 2 for mask in row_masks)
    problem = {
        "dimension": dimension,
        "rows": [list(row) for row in rows],
        "rhs": list(rhs),
    }
    certificate = solve(problem)
    if certificate != planted:
        raise AssertionError("full-rank public system did not recover the planted solution")

    predicate = """abbrev valid (bits : List Nat) : Prop :=
  BinarySystemSolution bits"""
    declarations = f"""def dimension : Nat := {dimension}
def rows : List (List Nat) := {_lean_rows(rows)}
def rhs : List Nat := [{", ".join(str(value) for value in rhs)}]

def rowParity (bits row : List Nat) : Nat :=
  (row.foldl (fun total column => total + bits.getD column 0) 0) % 2

def equationsHold (bits : List Nat) : Bool :=
  (rows.zip rhs).all (fun equation => rowParity bits equation.1 == equation.2)

abbrev BinarySystemSolution (bits : List Nat) : Prop :=
  bits.length = dimension ∧
  bits.all (fun bit => bit <= 1) = true ∧
  equationsHold bits = true"""
    source = challenge_source(
        declarations=declarations,
        predicate=predicate,
        claim="True",
    )
    return LeanCaseBlueprint(
        title=TITLE,
        problem=problem,
        challenge_source=source,
        reference_certificate=certificate,
        public_features={"variables": dimension, "equations": dimension},
        metadata={
            "criterion": "full_rank_gf2_system",
            "matrix_ones": sum(len(row) for row in rows),
            "solution_weight": sum(certificate),
        },
    )


__all__ = ["CASE_ID", "DEFAULT_PARAMETERS", "TITLE", "build", "solve"]
