"""C05: anonymous modular column equivalence with a kernel-checked witness."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Final

from aipbench.tasks.machine_checked_mathematics_cases.common import (
    DeterministicStream,
    LeanCaseBlueprint,
    challenge_source,
    integer_parameter,
    lean_nat_list,
)

CASE_ID: Final = "c05"
TITLE: Final = "Anonymous modular column equivalence"
DEFAULT_PARAMETERS: Final[Mapping[str, Any]] = {
    "field_modulus": 1009,
    "num_columns": 80,
}


def _is_prime(value: int) -> bool:
    if value < 2:
        return False
    if value % 2 == 0:
        return value == 2
    divisor = 3
    while divisor * divisor <= value:
        if value % divisor == 0:
            return False
        divisor += 2
    return True


def _integer(problem: Mapping[str, Any], name: str) -> int:
    value = problem[name]
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"column-equivalence field {name!r} must be an integer")
    return value


def _matrix(problem: Mapping[str, Any], name: str, columns: int) -> tuple[tuple[int, ...], ...]:
    raw = problem[name]
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)) or len(raw) != 3:
        raise ValueError(f"{name} must contain exactly three rows")
    rows: list[tuple[int, ...]] = []
    for row in raw:
        if not isinstance(row, Sequence) or isinstance(row, (str, bytes)):
            raise ValueError(f"{name} rows must be sequences")
        values = tuple(row)
        if len(values) != columns or any(
            isinstance(value, bool) or not isinstance(value, int) for value in values
        ):
            raise ValueError(f"{name} has an invalid row")
        rows.append(values)
    return tuple(rows)


def _rref(rows: Sequence[Sequence[int]], modulus: int) -> tuple[list[list[int]], tuple[int, ...]]:
    if not rows:
        return [], ()
    width = len(rows[0])
    matrix = [[int(value) % modulus for value in row] for row in rows]
    if any(len(row) != width for row in matrix):
        raise ValueError("inconsistent modular matrix width")
    pivots: list[int] = []
    rank = 0
    for column in range(width):
        pivot = next((row for row in range(rank, len(matrix)) if matrix[row][column]), None)
        if pivot is None:
            continue
        matrix[rank], matrix[pivot] = matrix[pivot], matrix[rank]
        inverse = pow(matrix[rank][column], -1, modulus)
        matrix[rank] = [(value * inverse) % modulus for value in matrix[rank]]
        for row in range(len(matrix)):
            if row == rank:
                continue
            factor = matrix[row][column]
            if factor:
                matrix[row] = [
                    (left - factor * right) % modulus
                    for left, right in zip(matrix[row], matrix[rank], strict=True)
                ]
        pivots.append(column)
        rank += 1
        if rank == len(matrix):
            break
    return matrix, tuple(pivots)


def _nullspace(rows: Sequence[Sequence[int]], modulus: int) -> tuple[tuple[int, ...], ...]:
    if not rows:
        raise ValueError("nullspace input must be nonempty")
    width = len(rows[0])
    reduced, pivots = _rref(rows, modulus)
    free_columns = [column for column in range(width) if column not in pivots]
    basis: list[tuple[int, ...]] = []
    for free in free_columns:
        vector = [0] * width
        vector[free] = 1
        for row, pivot in enumerate(pivots):
            vector[pivot] = (-reduced[row][free]) % modulus
        basis.append(tuple(vector))
    return tuple(basis)


def _mat_mul(
    left: Sequence[Sequence[int]], right: Sequence[Sequence[int]], modulus: int
) -> tuple[tuple[int, ...], ...]:
    if not left or not right or len(left[0]) != len(right):
        raise ValueError("inconsistent matrix multiplication dimensions")
    return tuple(
        tuple(
            sum(left[row][inner] * right[inner][column] for inner in range(len(right))) % modulus
            for column in range(len(right[0]))
        )
        for row in range(len(left))
    )


def _mat_vec(
    matrix: Sequence[Sequence[int]], vector: Sequence[int], modulus: int
) -> tuple[int, ...]:
    return tuple(
        sum(row[index] * vector[index] for index in range(len(vector))) % modulus for row in matrix
    )


def _inverse(matrix: Sequence[Sequence[int]], modulus: int) -> tuple[tuple[int, ...], ...]:
    size = len(matrix)
    if size == 0 or any(len(row) != size for row in matrix):
        raise ValueError("matrix inverse requires a nonempty square matrix")
    augmented = [
        [
            *(int(value) % modulus for value in matrix[row]),
            *(1 if row == column else 0 for column in range(size)),
        ]
        for row in range(size)
    ]
    reduced, pivots = _rref(augmented, modulus)
    if pivots[:size] != tuple(range(size)):
        raise ValueError("matrix is singular")
    return tuple(tuple(reduced[row][size:]) for row in range(size))


def _columns(matrix: Sequence[Sequence[int]]) -> tuple[tuple[int, int, int], ...]:
    return tuple(
        (matrix[0][column], matrix[1][column], matrix[2][column])
        for column in range(len(matrix[0]))
    )


def _normalise_projective(vector: Sequence[int], modulus: int) -> tuple[int, ...]:
    pivot = next((value % modulus for value in vector if value % modulus), None)
    if pivot is None:
        raise ValueError("zero vector has no projective normal form")
    inverse = pow(pivot, -1, modulus)
    return tuple((value * inverse) % modulus for value in vector)


def _recover_conic(points: Sequence[Sequence[int]], modulus: int) -> tuple[int, ...]:
    rows = [
        [
            x * x,
            y * y,
            z * z,
            x * y,
            x * z,
            y * z,
        ]
        for x, y, z in points
    ]
    basis = _nullspace(rows, modulus)
    if len(basis) != 1:
        raise ValueError("public columns do not determine one quadratic relation")
    return _normalise_projective(basis[0], modulus)


def _forms_vanishing_at(
    point: Sequence[int], modulus: int
) -> tuple[tuple[int, int, int], tuple[int, int, int]]:
    pivot = next(index for index, value in enumerate(point) if value % modulus)
    inverse = pow(point[pivot] % modulus, -1, modulus)
    forms: list[tuple[int, int, int]] = []
    for other in range(3):
        if other == pivot:
            continue
        form = [0, 0, 0]
        form[other] = 1
        form[pivot] = (-point[other] * inverse) % modulus
        forms.append(tuple(form))
    return forms[0], forms[1]


def _linear_combination_coordinates(
    target: Sequence[int], first: Sequence[int], second: Sequence[int], modulus: int
) -> tuple[int, int]:
    for left in range(3):
        for right in range(left + 1, 3):
            determinant = (first[left] * second[right] - first[right] * second[left]) % modulus
            if determinant:
                inverse = pow(determinant, -1, modulus)
                a = (target[left] * second[right] - target[right] * second[left]) * inverse
                b = (first[left] * target[right] - first[right] * target[left]) * inverse
                a %= modulus
                b %= modulus
                if all(
                    (a * first[index] + b * second[index] - target[index]) % modulus == 0
                    for index in range(3)
                ):
                    return a, b
    raise ValueError("target form is outside the expected pencil")


def _parametrise_conic(
    points: Sequence[Sequence[int]], coefficients: Sequence[int], modulus: int
) -> tuple[tuple[int, int], ...]:
    base = tuple(value % modulus for value in points[0])
    first, second = _forms_vanishing_at(base, modulus)
    x, y, z = base
    xx, yy, zz, xy, xz, yz = coefficients
    tangent = (
        (2 * xx * x + xy * y + xz * z) % modulus,
        (2 * yy * y + xy * x + yz * z) % modulus,
        (2 * zz * z + xz * x + yz * y) % modulus,
    )
    a, b = _linear_combination_coordinates(tangent, first, second, modulus)
    base_parameter = _normalise_projective((b, -a), modulus)
    parameters: list[tuple[int, int]] = []
    for point in points:
        if _normalise_projective(point, modulus) == _normalise_projective(base, modulus):
            parameter = base_parameter
        else:
            parameter = _normalise_projective(
                (
                    sum(first[index] * point[index] for index in range(3)),
                    sum(second[index] * point[index] for index in range(3)),
                ),
                modulus,
            )
        parameters.append((parameter[0], parameter[1]))
    if len(set(parameters)) != len(parameters):
        raise ValueError("quadratic-pencil parameters are not distinct")
    return tuple(parameters)


def _frame2(
    points: Sequence[Sequence[int]], modulus: int
) -> tuple[tuple[int, int], tuple[int, int]]:
    if len(points) != 3:
        raise ValueError("a projective-line frame has three points")
    x0, y0 = points[0]
    x1, y1 = points[1]
    x2, y2 = points[2]
    determinant = (x0 * y1 - x1 * y0) % modulus
    if not determinant:
        raise ValueError("projective-line frame points must be distinct")
    inverse_determinant = pow(determinant, -1, modulus)
    first_coordinate = (y1 * x2 - x1 * y2) * inverse_determinant % modulus
    second_coordinate = (x0 * y2 - y0 * x2) * inverse_determinant % modulus
    if not first_coordinate or not second_coordinate:
        raise ValueError("projective-line frame points must be distinct")
    return (
        (x0 * first_coordinate % modulus, x1 * second_coordinate % modulus),
        (y0 * first_coordinate % modulus, y1 * second_coordinate % modulus),
    )


def _find_parameter_map(
    left: Sequence[tuple[int, int]], right: Sequence[tuple[int, int]], modulus: int
) -> tuple[tuple[tuple[int, int], tuple[int, int]], tuple[int, ...]]:
    source_frame_inverse = _inverse(_frame2(left[:3], modulus), modulus)
    target_lookup = {point: index for index, point in enumerate(right)}
    count = len(right)
    for first in range(count):
        for second in range(count):
            if second == first:
                continue
            for third in range(count):
                if third in (first, second):
                    continue
                target_frame = _frame2((right[first], right[second], right[third]), modulus)
                transform = _mat_mul(target_frame, source_frame_inverse, modulus)
                permutation: list[int] = []
                for point in left:
                    image = _normalise_projective(_mat_vec(transform, point, modulus), modulus)
                    target = target_lookup.get((image[0], image[1]))
                    if target is None:
                        break
                    permutation.append(target)
                if len(permutation) == len(left) and len(set(permutation)) == len(left):
                    return transform, tuple(permutation)
    raise ValueError("no projective-line equivalence maps the public column sets")


def _matrix_from_correspondence(
    left: Sequence[Sequence[int]],
    right: Sequence[Sequence[int]],
    permutation: Sequence[int],
    modulus: int,
) -> tuple[tuple[tuple[int, ...], ...], tuple[int, ...]]:
    left_basis = tuple(tuple(left[column][row] for column in range(3)) for row in range(3))
    right_basis = tuple(
        tuple(right[permutation[column]][row] for column in range(3)) for row in range(3)
    )
    left_inverse = _inverse(left_basis, modulus)
    right_inverse = _inverse(right_basis, modulus)
    fourth = 3
    left_coordinates = _mat_vec(left_inverse, left[fourth], modulus)
    right_coordinates = _mat_vec(right_inverse, right[permutation[fourth]], modulus)
    if any(value == 0 for value in (*left_coordinates, *right_coordinates)):
        raise ValueError("the recovered projective frame is degenerate")
    diagonal = tuple(
        right_coordinates[index] * pow(left_coordinates[index], -1, modulus) % modulus
        for index in range(3)
    )
    scaled_right_basis = tuple(
        tuple(right_basis[row][column] * diagonal[column] % modulus for column in range(3))
        for row in range(3)
    )
    transform = _mat_mul(scaled_right_basis, left_inverse, modulus)
    scales: list[int] = []
    for column, source in enumerate(left):
        image = _mat_vec(transform, source, modulus)
        target = right[permutation[column]]
        pivot = next(index for index, value in enumerate(image) if value)
        scale = target[pivot] * pow(image[pivot], -1, modulus) % modulus
        if not scale or any((scale * image[index] - target[index]) % modulus for index in range(3)):
            raise ValueError("recovered projectivity does not lift to the public columns")
        scales.append(scale)
    return transform, tuple(scales)


def _pack(values: Sequence[int], base: int, per_word: int) -> tuple[int, ...]:
    return tuple(
        sum(value * base**offset for offset, value in enumerate(values[start : start + per_word]))
        for start in range(0, len(values), per_word)
    )


def solve(problem: Mapping[str, Any]) -> tuple[int, ...]:
    modulus = _integer(problem, "modulus")
    num_columns = _integer(problem, "num_columns")
    if not _is_prime(modulus) or modulus < 5 or num_columns < 5 or num_columns > modulus + 1:
        raise ValueError("invalid public field/column profile")
    left_matrix = _matrix(problem, "left_matrix", num_columns)
    right_matrix = _matrix(problem, "right_matrix", num_columns)
    for matrix in (left_matrix, right_matrix):
        if any(value < 0 or value >= modulus for row in matrix for value in row):
            raise ValueError("matrix entries must be field elements")
        points = _columns(matrix)
        normalised = tuple(_normalise_projective(point, modulus) for point in points)
        if len(set(normalised)) != num_columns:
            raise ValueError("public columns must be nonzero and projectively distinct")
        if len(_rref(matrix, modulus)[1]) != 3:
            raise ValueError("public matrix must have row rank three")

    left_points = _columns(left_matrix)
    right_points = _columns(right_matrix)
    left_conic = _recover_conic(left_points, modulus)
    right_conic = _recover_conic(right_points, modulus)
    left_parameters = _parametrise_conic(left_points, left_conic, modulus)
    right_parameters = _parametrise_conic(right_points, right_conic, modulus)
    _, permutation = _find_parameter_map(left_parameters, right_parameters, modulus)
    transform, scales = _matrix_from_correspondence(left_points, right_points, permutation, modulus)
    inverse = _inverse(transform, modulus)
    inverse_permutation = [0] * num_columns
    for source, target in enumerate(permutation):
        inverse_permutation[target] = source
    return (
        *(value for row in transform for value in row),
        *(value for row in inverse for value in row),
        *scales,
        *_pack(permutation, num_columns, 10),
        *_pack(inverse_permutation, num_columns, 10),
    )


def render_solution(certificate: Sequence[int]) -> str:
    proofs = " ".join("(by decide)" for _ in range(13))
    return f"""import Challenge

namespace AMBenchSolution

theorem proof : Challenge.Target := by
  let certificate : List Nat := {lean_nat_list(certificate)}
  exact Challenge.submit certificate {proofs}

end AMBenchSolution
"""


def _random_invertible(
    stream: DeterministicStream, size: int, modulus: int
) -> tuple[tuple[int, ...], ...]:
    matrix = [[1 if row == column else 0 for column in range(size)] for row in range(size)]
    for _ in range(6 * size):
        operation = stream.randbelow(3)
        left = stream.randbelow(size)
        right = stream.randbelow(size - 1)
        if right >= left:
            right += 1
        if operation == 0:
            matrix[left], matrix[right] = matrix[right], matrix[left]
        elif operation == 1:
            factor = stream.randint(1, modulus - 1)
            matrix[left] = [
                (value + factor * other) % modulus
                for value, other in zip(matrix[left], matrix[right], strict=True)
            ]
        else:
            factor = stream.randint(1, modulus - 1)
            matrix[left] = [factor * value % modulus for value in matrix[left]]
    return tuple(tuple(row) for row in matrix)


def _apply_column_disguise(
    stream: DeterministicStream,
    columns: Sequence[Sequence[int]],
    modulus: int,
) -> tuple[tuple[int, ...], ...]:
    transform = _random_invertible(stream, 3, modulus)
    disguised = []
    for column in columns:
        scale = stream.randint(1, modulus - 1)
        disguised.append(
            tuple(scale * value % modulus for value in _mat_vec(transform, column, modulus))
        )
    stream.shuffle(disguised)
    return tuple(tuple(column[row] for column in disguised) for row in range(3))


def _lean_matrix(matrix: Sequence[Sequence[int]]) -> str:
    return "[\n    " + ",\n    ".join(lean_nat_list(row) for row in matrix) + "\n  ]"


def build(stream: DeterministicStream, parameters: Mapping[str, Any]) -> LeanCaseBlueprint:
    modulus = integer_parameter(parameters, "field_modulus", minimum=101, maximum=4093)
    num_columns = integer_parameter(parameters, "num_columns", minimum=16, maximum=160)
    if not _is_prime(modulus) or num_columns > modulus + 1:
        raise ValueError("field_modulus must be prime and support all requested columns")

    projective_parameters = [(value, 1) for value in range(modulus)] + [(1, 0)]
    for index in range(num_columns):
        other = index + stream.randbelow(len(projective_parameters) - index)
        projective_parameters[index], projective_parameters[other] = (
            projective_parameters[other],
            projective_parameters[index],
        )
    selected = projective_parameters[:num_columns]
    canonical_columns = tuple(
        (v * v % modulus, u * v % modulus, u * u % modulus) for u, v in selected
    )

    parameter_transform = _random_invertible(stream, 2, modulus)
    right_parameters = tuple(
        _mat_vec(parameter_transform, parameter, modulus) for parameter in selected
    )
    right_canonical_columns = tuple(
        (v * v % modulus, u * v % modulus, u * u % modulus) for u, v in right_parameters
    )
    left_matrix = _apply_column_disguise(stream, canonical_columns, modulus)
    right_matrix = _apply_column_disguise(stream, right_canonical_columns, modulus)
    problem = {
        "modulus": modulus,
        "num_columns": num_columns,
        "left_matrix": left_matrix,
        "right_matrix": right_matrix,
    }
    certificate = solve(problem)
    permutation_words = (num_columns + 9) // 10
    certificate_entries = 18 + num_columns + 2 * permutation_words
    groups = [
        list(range(start, min(start + 10, num_columns))) for start in range(0, num_columns, 10)
    ]
    if len(groups) != 8:
        raise ValueError("the released profile requires exactly eight relation groups")
    declarations = f"""set_option maxRecDepth 100000

def fieldModulus : Nat := {modulus}
def numColumns : Nat := {num_columns}
def valuesPerWord : Nat := 10
def permutationBase : Nat := numColumns
def matrixOffset : Nat := 0
def inverseOffset : Nat := 9
def scaleOffset : Nat := 18
def permutationOffset : Nat := scaleOffset + numColumns
def permutationWords : Nat := {permutation_words}
def inversePermutationOffset : Nat := permutationOffset + permutationWords
def certificateEntries : Nat := inversePermutationOffset + permutationWords
def leftMatrix : List (List Nat) := {_lean_matrix(left_matrix)}
def rightMatrix : List (List Nat) := {_lean_matrix(right_matrix)}
def columnGroups : List (List Nat) := {
        "[" + ", ".join(lean_nat_list(group) for group in groups) + "]"
    }

def matrixEntry (certificate : List Nat) (row column : Nat) : Nat :=
  certificate.getD (matrixOffset + 3 * row + column) fieldModulus

def inverseEntry (certificate : List Nat) (row column : Nat) : Nat :=
  certificate.getD (inverseOffset + 3 * row + column) fieldModulus

def scale (certificate : List Nat) (column : Nat) : Nat :=
  certificate.getD (scaleOffset + column) fieldModulus

def packedValue (certificate : List Nat) (offset index : Nat) : Nat :=
  ((certificate.getD (offset + index / valuesPerWord) 0) /
    (permutationBase ^ (index % valuesPerWord))) % permutationBase

def permutation (certificate : List Nat) (column : Nat) : Nat :=
  packedValue certificate permutationOffset column

def inversePermutation (certificate : List Nat) (column : Nat) : Nat :=
  packedValue certificate inversePermutationOffset column

def entriesValid (certificate : List Nat) : Bool :=
  (List.range 9).all (fun index =>
    certificate.getD (matrixOffset + index) fieldModulus < fieldModulus) &&
  (List.range 9).all (fun index =>
    certificate.getD (inverseOffset + index) fieldModulus < fieldModulus) &&
  (List.range numColumns).all (fun column =>
    0 < scale certificate column && scale certificate column < fieldModulus)

def inverseHolds (certificate : List Nat) : Bool :=
  (List.range 3).all (fun row => (List.range 3).all (fun column =>
    ((List.range 3).foldl (fun total inner =>
      total + matrixEntry certificate row inner * inverseEntry certificate inner column) 0) %
      fieldModulus == (if row == column then 1 else 0))) &&
  (List.range 3).all (fun row => (List.range 3).all (fun column =>
    ((List.range 3).foldl (fun total inner =>
      total + inverseEntry certificate row inner * matrixEntry certificate inner column) 0) %
      fieldModulus == (if row == column then 1 else 0)))

def packedWordsValid (certificate : List Nat) : Bool :=
  (List.range permutationWords).all (fun word =>
    certificate.getD (permutationOffset + word) 0 < permutationBase ^ valuesPerWord) &&
  (List.range permutationWords).all (fun word =>
    certificate.getD (inversePermutationOffset + word) 0 < permutationBase ^ valuesPerWord)

def permutationHolds (certificate : List Nat) : Bool :=
  (List.range numColumns).all (fun column =>
    inversePermutation certificate (permutation certificate column) == column)

def transformedEntry (certificate : List Nat) (row column : Nat) : Nat :=
  ((List.range 3).foldl (fun total inner =>
    total + matrixEntry certificate row inner *
      ((leftMatrix.getD inner []).getD column fieldModulus)) 0) % fieldModulus

def columnHolds (certificate : List Nat) (column : Nat) : Bool :=
  (List.range 3).all (fun row =>
    (scale certificate column * transformedEntry certificate row column) % fieldModulus ==
      (rightMatrix.getD row []).getD (permutation certificate column) fieldModulus)

def relationGroupHolds (certificate : List Nat) (group : Nat) : Bool :=
  (columnGroups.getD group []).all (columnHolds certificate)

abbrev ProfileEncoded : Prop :=
  certificateEntries = 18 + numColumns + 2 * permutationWords ∧
  numColumns = 80"""
    group_terms = " ∧\n  ".join(
        f"relationGroupHolds certificate {group} = true" for group in range(8)
    )
    predicate = f"""abbrev valid (certificate : List Nat) : Prop :=
  certificate.length = certificateEntries ∧
  entriesValid certificate = true ∧
  inverseHolds certificate = true ∧
  packedWordsValid certificate = true ∧
  permutationHolds certificate = true ∧
  {group_terms}"""
    source = challenge_source(
        declarations=declarations, predicate=predicate, claim="ProfileEncoded"
    )
    group_arguments = "\n    ".join(
        f"(hGroup{group} : relationGroupHolds certificate {group} = true)" for group in range(8)
    )
    group_names = ", ".join(f"hGroup{group}" for group in range(8))
    source = source.replace(
        "\nend Challenge\n",
        f"""

theorem submit (certificate : List Nat)
    (hLength : certificate.length = certificateEntries)
    (hEntries : entriesValid certificate = true)
    (hInverse : inverseHolds certificate = true)
    (hPacked : packedWordsValid certificate = true)
    (hPermutation : permutationHolds certificate = true)
    {group_arguments} : Target := by
  exact Exists.intro certificate
    (And.intro
      ⟨hLength, hEntries, hInverse, hPacked, hPermutation, {group_names}⟩
      (by decide))

end Challenge
""",
    )
    return LeanCaseBlueprint(
        title=TITLE,
        problem=problem,
        challenge_source=source,
        reference_certificate=certificate,
        public_features={"rows": 3, "columns": num_columns},
        metadata={
            "criterion": "hidden_conic_monomial_code_equivalence",
            "certificate_entries": certificate_entries,
            "permutation_words": permutation_words,
        },
    )


__all__ = [
    "CASE_ID",
    "DEFAULT_PARAMETERS",
    "TITLE",
    "_columns",
    "_inverse",
    "_mat_mul",
    "_mat_vec",
    "_normalise_projective",
    "build",
    "render_solution",
    "solve",
]
