"""C04: anonymous affine-plane coordinatization and bivariate error recovery."""

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

CASE_ID: Final = "c04"
TITLE: Final = "Anonymous affine-plane decoding certificate"
DEFAULT_PARAMETERS: Final[Mapping[str, Any]] = {
    "field_modulus": 19,
    "polynomial_degree": 8,
    "fully_corrupted_rows": 2,
    "errors_per_other_row": 2,
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
        raise ValueError(f"affine-plane field {name!r} must be an integer")
    return value


def _integer_sequence(problem: Mapping[str, Any], name: str) -> tuple[int, ...]:
    raw = problem[name]
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        raise ValueError(f"affine-plane field {name!r} must be a sequence")
    values: list[int] = []
    for value in raw:
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"affine-plane field {name!r} must contain integers")
        values.append(value)
    return tuple(values)


def _block_sequence(problem: Mapping[str, Any]) -> tuple[tuple[int, ...], ...]:
    raw = problem["incidence_blocks"]
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        raise ValueError("incidence_blocks must be a sequence")
    blocks: list[tuple[int, ...]] = []
    for block in raw:
        if not isinstance(block, Sequence) or isinstance(block, (str, bytes)):
            raise ValueError("every incidence block must be a sequence")
        values: list[int] = []
        for value in block:
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValueError("incidence blocks must contain integers")
            values.append(value)
        blocks.append(tuple(values))
    return tuple(blocks)


def _solve_linear_system_mod(
    rows: Sequence[Sequence[int]], rhs: Sequence[int], modulus: int
) -> tuple[int, ...]:
    if len(rows) != len(rhs) or not rows:
        raise ValueError("modular linear system dimensions are inconsistent")
    width = len(rows[0])
    matrix = [
        [*(int(value) % modulus for value in row), int(target) % modulus]
        for row, target in zip(rows, rhs, strict=True)
    ]
    if any(len(row) != width + 1 for row in matrix):
        raise ValueError("modular linear system rows have inconsistent widths")

    pivot_rows = [-1] * width
    rank = 0
    for column in range(width):
        pivot = next(
            (row for row in range(rank, len(matrix)) if matrix[row][column] != 0),
            None,
        )
        if pivot is None:
            continue
        matrix[rank], matrix[pivot] = matrix[pivot], matrix[rank]
        inverse = pow(matrix[rank][column], -1, modulus)
        matrix[rank] = [(value * inverse) % modulus for value in matrix[rank]]
        for row in range(len(matrix)):
            factor = matrix[row][column]
            if row != rank and factor:
                matrix[row] = [
                    (left - factor * right) % modulus
                    for left, right in zip(matrix[row], matrix[rank], strict=True)
                ]
        pivot_rows[column] = rank
        rank += 1
    if rank != width:
        raise ValueError("modular linear system is not uniquely solvable")
    for row in matrix[rank:]:
        if not any(row[:-1]) and row[-1] != 0:
            raise ValueError("modular linear system is inconsistent")
    return tuple(matrix[pivot_rows[column]][-1] for column in range(width))


def _eval_poly(coefficients: Sequence[int], value: int, modulus: int) -> int:
    result = 0
    for coefficient in reversed(coefficients):
        result = (result * value + coefficient) % modulus
    return result


def _eval_bivariate(
    coefficients: Sequence[int], x_value: int, y_value: int, degree: int, modulus: int
) -> int:
    y_coefficients: list[int] = []
    for y_power in range(degree + 1):
        start = y_power * (degree + 1) - y_power * (y_power - 1) // 2
        stop = (y_power + 1) * (degree + 1) - y_power * (y_power + 1) // 2
        y_coefficients.append(_eval_poly(coefficients[start:stop], x_value, modulus))
    return _eval_poly(y_coefficients, y_value, modulus)


def _decode_polynomial_with_exact_errors(
    coordinates: Sequence[int],
    observations: Sequence[int],
    *,
    degree: int,
    errors: int,
    modulus: int,
) -> tuple[int, ...]:
    q_degree = degree + errors
    rows: list[list[int]] = []
    rhs: list[int] = []
    for coordinate, observation in zip(coordinates, observations, strict=True):
        powers = [1]
        for _ in range(q_degree):
            powers.append((powers[-1] * coordinate) % modulus)
        rows.append(
            [
                *powers,
                *((-observation * powers[index]) % modulus for index in range(errors)),
            ]
        )
        rhs.append((observation * powers[errors]) % modulus)
    solved = _solve_linear_system_mod(rows, rhs, modulus)
    quotient_coefficients = list(solved[: q_degree + 1])
    error_locator = [*solved[q_degree + 1 :], 1]

    polynomial = [0] * (degree + 1)
    remainder = quotient_coefficients[:]
    for power in range(q_degree, errors - 1, -1):
        factor = remainder[power]
        quotient_index = power - errors
        polynomial[quotient_index] = factor
        for index, locator_coefficient in enumerate(error_locator):
            remainder[quotient_index + index] = (
                remainder[quotient_index + index] - factor * locator_coefficient
            ) % modulus
    if any(remainder[:errors]):
        raise ValueError("error-locator quotient has a nonzero remainder")
    mismatches = sum(
        _eval_poly(polynomial, coordinate, modulus) != observation
        for coordinate, observation in zip(coordinates, observations, strict=True)
    )
    if mismatches != errors:
        raise ValueError("row does not have the requested exact error count")
    return tuple(polynomial)


def _interpolate(
    coordinates: Sequence[int], observations: Sequence[int], degree: int, modulus: int
) -> tuple[int, ...]:
    if len(coordinates) != degree + 1 or len(observations) != degree + 1:
        raise ValueError("interpolation requires degree + 1 samples")
    rows = [
        [pow(coordinate, power, modulus) for power in range(degree + 1)]
        for coordinate in coordinates
    ]
    return _solve_linear_system_mod(rows, observations, modulus)


def _recover_coordinates(problem: Mapping[str, Any]) -> tuple[tuple[int, int], ...]:
    modulus = _integer(problem, "modulus")
    num_items = _integer(problem, "num_items")
    blocks = _block_sequence(problem)
    if num_items != modulus * modulus:
        raise ValueError("invalid affine-plane dimensions")
    if len(blocks) != modulus * (modulus + 1):
        raise ValueError("invalid affine-plane block count")

    block_sets: list[frozenset[int]] = []
    point_blocks: list[list[int]] = [[] for _ in range(num_items)]
    pair_to_block: dict[tuple[int, int], int] = {}
    for block_index, block in enumerate(blocks):
        block_set = frozenset(block)
        if len(block_set) != modulus or any(item < 0 or item >= num_items for item in block_set):
            raise ValueError("invalid affine-plane block")
        block_sets.append(block_set)
        for item in block_set:
            point_blocks[item].append(block_index)
        sorted_block = sorted(block_set)
        for left_index, left in enumerate(sorted_block):
            for right in sorted_block[left_index + 1 :]:
                pair = (left, right)
                if pair in pair_to_block:
                    raise ValueError("a public pair occurs in multiple incidence blocks")
                pair_to_block[pair] = block_index
    if any(len(indices) != modulus + 1 for indices in point_blocks):
        raise ValueError("invalid affine-plane point degree")

    def line_through(left: int, right: int) -> int:
        if left == right:
            raise ValueError("two distinct items are required to determine a block")
        return pair_to_block[(min(left, right), max(left, right))]

    def parallel_through(block_index: int, item: int) -> int:
        if item in block_sets[block_index]:
            return block_index
        candidates = [
            candidate
            for candidate in point_blocks[item]
            if block_sets[candidate].isdisjoint(block_sets[block_index])
        ]
        if len(candidates) != 1:
            raise ValueError("parallel block is not unique")
        return candidates[0]

    def intersection(left: int, right: int) -> int:
        common = block_sets[left] & block_sets[right]
        if len(common) != 1:
            raise ValueError("blocks do not have a unique intersection")
        return next(iter(common))

    x_axis = 0
    origin, x_unit = blocks[x_axis][:2]
    y_unit = next(item for item in range(num_items) if item not in block_sets[x_axis])
    y_axis = line_through(origin, y_unit)
    unit_horizontal = parallel_through(x_axis, y_unit)
    descending_diagonal = line_through(x_unit, y_unit)

    x_points = [origin, x_unit]
    while len(x_points) < modulus:
        current = x_points[-1]
        vertical = parallel_through(y_axis, current)
        lifted = intersection(vertical, unit_horizontal)
        successor_line = parallel_through(descending_diagonal, lifted)
        successor = intersection(successor_line, x_axis)
        if successor in x_points:
            raise ValueError("synthetic successor closed before exhausting the prime field")
        x_points.append(successor)
    current = x_points[-1]
    vertical = parallel_through(y_axis, current)
    lifted = intersection(vertical, unit_horizontal)
    successor_line = parallel_through(descending_diagonal, lifted)
    if intersection(successor_line, x_axis) != origin:
        raise ValueError("synthetic successor does not have the public field order")

    y_points = [
        intersection(parallel_through(descending_diagonal, item), y_axis) for item in x_points
    ]
    coordinates: list[tuple[int, int] | None] = [None] * num_items
    for x_value, x_point in enumerate(x_points):
        vertical = parallel_through(y_axis, x_point)
        for y_value, y_point in enumerate(y_points):
            horizontal = parallel_through(x_axis, y_point)
            item = intersection(vertical, horizontal)
            coordinate = (x_value, y_value)
            if coordinates[item] is not None:
                raise ValueError("synthetic grid assigns an item more than once")
            coordinates[item] = coordinate
    if any(coordinate is None for coordinate in coordinates):
        raise ValueError("synthetic grid does not cover every public item")
    return tuple(coordinate for coordinate in coordinates if coordinate is not None)


def _recover_bivariate_polynomial(
    coordinates: Sequence[tuple[int, int]],
    readings: Sequence[int],
    *,
    degree: int,
    modulus: int,
) -> tuple[int, ...]:
    rows_by_y: list[list[tuple[int, int]]] = [[] for _ in range(modulus)]
    for (x_value, y_value), reading in zip(coordinates, readings, strict=True):
        rows_by_y[y_value].append((x_value, reading))

    maximum_row_errors = (modulus - degree - 1) // 2
    decoded_rows: dict[int, tuple[int, ...]] = {}
    for y_value, samples in enumerate(rows_by_y):
        ordered = sorted(samples)
        x_values = [x_value for x_value, _ in ordered]
        observations = [reading for _, reading in ordered]
        for errors in range(maximum_row_errors + 1):
            try:
                polynomial = _decode_polynomial_with_exact_errors(
                    x_values,
                    observations,
                    degree=degree,
                    errors=errors,
                    modulus=modulus,
                )
            except ValueError:
                continue
            decoded_rows[y_value] = polynomial
            break
    if len(decoded_rows) < degree + 1:
        raise ValueError("too few public fibers decode inside the unique radius")

    decoded_y_values = sorted(decoded_rows)
    coefficients_by_x_power: list[tuple[int, ...]] = []
    for x_power in range(degree + 1):
        outer_degree = degree - x_power
        maximum_outer_errors = (len(decoded_y_values) - outer_degree - 1) // 2
        outer_observations = [decoded_rows[y_value][x_power] for y_value in decoded_y_values]
        recovered: tuple[int, ...] | None = None
        for errors in range(maximum_outer_errors + 1):
            try:
                recovered = _decode_polynomial_with_exact_errors(
                    decoded_y_values,
                    outer_observations,
                    degree=outer_degree,
                    errors=errors,
                    modulus=modulus,
                )
            except ValueError:
                continue
            break
        if recovered is None:
            raise ValueError("decoded fiber coefficients do not form a bivariate codeword")
        coefficients_by_x_power.append(recovered)
    coefficients = tuple(
        coefficients_by_x_power[x_power][y_power]
        for y_power in range(degree + 1)
        for x_power in range(degree - y_power + 1)
    )
    return coefficients


def _pack(values: Sequence[int], base: int, per_word: int) -> tuple[int, ...]:
    return tuple(
        sum(value * base**offset for offset, value in enumerate(values[start : start + per_word]))
        for start in range(0, len(values), per_word)
    )


def solve(problem: Mapping[str, Any]) -> tuple[int, ...]:
    modulus = _integer(problem, "modulus")
    num_items = _integer(problem, "num_items")
    degree = _integer(problem, "polynomial_degree")
    mismatch_count = _integer(problem, "mismatch_count")
    readings = _integer_sequence(problem, "readings")
    if not _is_prime(modulus) or num_items != modulus * modulus:
        raise ValueError("the public modulus/profile is invalid")
    if degree < 1 or degree >= modulus or len(readings) != num_items:
        raise ValueError("the public polynomial/readings profile is invalid")
    if any(reading < 0 or reading >= modulus for reading in readings):
        raise ValueError("readings must be field elements")

    coordinates = _recover_coordinates(problem)
    coefficients = _recover_bivariate_polynomial(
        coordinates,
        readings,
        degree=degree,
        modulus=modulus,
    )
    mismatch_flags = tuple(
        int(_eval_bivariate(coefficients, x_value, y_value, degree, modulus) != reading)
        for (x_value, y_value), reading in zip(coordinates, readings, strict=True)
    )
    top_degree_indices = tuple(
        y_power * (degree + 1) - y_power * (y_power - 1) // 2 + degree - y_power
        for y_power in range(degree + 1)
    )
    if sum(mismatch_flags) != mismatch_count or not any(
        coefficients[index] for index in top_degree_indices
    ):
        raise ValueError("decoded certificate does not match the public profile")
    coordinate_codes = tuple(x_value + modulus * y_value for x_value, y_value in coordinates)
    inverse_items = [0] * num_items
    for item, code in enumerate(coordinate_codes):
        inverse_items[code] = item
    return (
        *_pack(coordinate_codes, num_items, modulus),
        *_pack(inverse_items, num_items, modulus),
        *coefficients,
        *_pack(mismatch_flags, 2, modulus),
    )


def render_solution(certificate: Sequence[int]) -> str:
    proofs = " ".join("(by decide)" for _ in range(7))
    return f"""import Challenge

namespace AMBenchSolution

theorem proof : Challenge.Target := by
  let certificate : List Nat := {lean_nat_list(certificate)}
  exact Challenge.submit certificate {proofs}

end AMBenchSolution
"""


def _lean_block_groups(blocks: Sequence[Sequence[int]], group_size: int = 32) -> str:
    groups = [blocks[index : index + group_size] for index in range(0, len(blocks), group_size)]
    return (
        "[\n    "
        + ",\n    ".join(
            "[" + ", ".join(lean_nat_list(block) for block in group) + "]" for group in groups
        )
        + "\n  ]"
    )


def _lean_range_groups(length: int, group_size: int = 64) -> str:
    groups = [
        range(index, min(index + group_size, length)) for index in range(0, length, group_size)
    ]
    return "[\n    " + ",\n    ".join(lean_nat_list(group) for group in groups) + "\n  ]"


def build(stream: DeterministicStream, parameters: Mapping[str, Any]) -> LeanCaseBlueprint:
    modulus = integer_parameter(parameters, "field_modulus", minimum=5, maximum=29)
    degree = integer_parameter(parameters, "polynomial_degree", minimum=1, maximum=8)
    fully_corrupted_rows = integer_parameter(
        parameters, "fully_corrupted_rows", minimum=1, maximum=8
    )
    errors_per_other_row = integer_parameter(
        parameters, "errors_per_other_row", minimum=1, maximum=8
    )
    if not _is_prime(modulus):
        raise ValueError("field_modulus must be prime")
    if modulus <= degree + 2 * errors_per_other_row:
        raise ValueError("ordinary rows must stay inside the univariate unique-decoding radius")
    if modulus - fully_corrupted_rows < degree + 1:
        raise ValueError("too few ordinary rows remain for bivariate reconstruction")
    mismatch_count = (
        fully_corrupted_rows * modulus + (modulus - fully_corrupted_rows) * errors_per_other_row
    )
    minimum_distance = modulus * (modulus - degree)
    if 2 * mismatch_count >= minimum_distance:
        raise ValueError("the whole profile must stay inside the bivariate unique-decoding radius")

    num_items = modulus * modulus
    public_by_code = list(range(num_items))
    stream.shuffle(public_by_code)

    blocks: list[list[int]] = []
    for x_value in range(modulus):
        blocks.append([public_by_code[x_value + modulus * y] for y in range(modulus)])
    for slope in range(modulus):
        for offset in range(modulus):
            blocks.append(
                [
                    public_by_code[x + modulus * ((slope * x + offset) % modulus)]
                    for x in range(modulus)
                ]
            )
    reference_axis = blocks[modulus]
    for block in blocks:
        stream.shuffle(block)
    stream.shuffle(blocks)
    reference_axis_index = next(
        index for index, block in enumerate(blocks) if block is reference_axis
    )
    blocks[0], blocks[reference_axis_index] = blocks[reference_axis_index], blocks[0]

    coefficient_count = (degree + 1) * (degree + 2) // 2
    coefficients = [stream.randbelow(modulus) for _ in range(coefficient_count)]
    coefficients[-1] = stream.randint(1, modulus - 1)
    readings = [0] * num_items
    for code, public_item in enumerate(public_by_code):
        x_value = code % modulus
        y_value = code // modulus
        readings[public_item] = _eval_bivariate(coefficients, x_value, y_value, degree, modulus)

    row_order = list(range(modulus))
    stream.shuffle(row_order)
    bad_rows = set(row_order[:fully_corrupted_rows])
    for y_value in range(modulus):
        if y_value in bad_rows:
            error_x_values = range(modulus)
        else:
            x_order = list(range(modulus))
            stream.shuffle(x_order)
            error_x_values = x_order[:errors_per_other_row]
        for x_value in error_x_values:
            public_item = public_by_code[x_value + modulus * y_value]
            readings[public_item] = (
                readings[public_item] + stream.randint(1, modulus - 1)
            ) % modulus

    problem = {
        "modulus": modulus,
        "num_items": num_items,
        "polynomial_degree": degree,
        "mismatch_count": mismatch_count,
        "incidence_blocks": blocks,
        "readings": readings,
    }
    certificate = solve(problem)
    coordinate_words = num_items // modulus
    inverse_words = num_items // modulus
    error_words = num_items // modulus
    top_degree_indices = [
        y_power * (degree + 1) - y_power * (y_power - 1) // 2 + degree - y_power
        for y_power in range(degree + 1)
    ]
    declarations = f"""set_option maxRecDepth 100000

def fieldModulus : Nat := {modulus}
def numItems : Nat := {num_items}
def polynomialDegree : Nat := {degree}
def coefficientSide : Nat := polynomialDegree + 1
def coefficientCount : Nat := coefficientSide * (coefficientSide + 1) / 2
def promisedMismatchCount : Nat := {mismatch_count}
def valuesPerWord : Nat := fieldModulus
def coordinateBase : Nat := numItems
def coordinateWords : Nat := {coordinate_words}
def inverseOffset : Nat := coordinateWords
def inverseWords : Nat := {inverse_words}
def coefficientOffset : Nat := inverseOffset + inverseWords
def errorOffset : Nat := coefficientOffset + coefficientCount
def errorWords : Nat := {error_words}
def certificateWords : Nat := errorOffset + errorWords
def incidenceBlockGroups : List (List (List Nat)) :=
  {_lean_block_groups(blocks)}
def readings : List Nat := {lean_nat_list(readings)}
def itemGroups : List (List Nat) := {_lean_range_groups(num_items)}

def coordinateCode (certificate : List Nat) (item : Nat) : Nat :=
  ((certificate.getD (item / valuesPerWord) 0) /
    (coordinateBase ^ (item % valuesPerWord))) % coordinateBase

def coordinateX (certificate : List Nat) (item : Nat) : Nat :=
  coordinateCode certificate item % fieldModulus

def coordinateY (certificate : List Nat) (item : Nat) : Nat :=
  coordinateCode certificate item / fieldModulus

def coordinateWordsValid (certificate : List Nat) : Bool :=
  (List.range coordinateWords).all (fun index =>
    certificate.getD index 0 < coordinateBase ^ valuesPerWord)

def inverseItem (certificate : List Nat) (code : Nat) : Nat :=
  ((certificate.getD (inverseOffset + code / valuesPerWord) 0) /
    (coordinateBase ^ (code % valuesPerWord))) % coordinateBase

def inverseWordsValid (certificate : List Nat) : Bool :=
  (List.range inverseWords).all (fun index =>
    certificate.getD (inverseOffset + index) 0 < coordinateBase ^ valuesPerWord)

def coordinatesPermuteGrid (certificate : List Nat) : Bool :=
  coordinateWordsValid certificate &&
  inverseWordsValid certificate &&
  itemGroups.all (fun group => group.all (fun item =>
    inverseItem certificate (coordinateCode certificate item) == item))

def collinear (certificate : List Nat) (a b c : Nat) : Bool :=
  let abx := (coordinateX certificate b + fieldModulus - coordinateX certificate a) %
    fieldModulus
  let aby := (coordinateY certificate b + fieldModulus - coordinateY certificate a) %
    fieldModulus
  let acx := (coordinateX certificate c + fieldModulus - coordinateX certificate a) %
    fieldModulus
  let acy := (coordinateY certificate c + fieldModulus - coordinateY certificate a) %
    fieldModulus
  (abx * acy) % fieldModulus == (aby * acx) % fieldModulus

def incidenceBlockHolds (certificate : List Nat) (block : List Nat) : Bool :=
  let first := block.getD 0 numItems
  let second := block.getD 1 numItems
  block.all (fun item => collinear certificate first second item)

def incidenceHolds (certificate : List Nat) : Bool :=
  incidenceBlockGroups.all (fun group =>
    group.all (incidenceBlockHolds certificate))

def coefficient (certificate : List Nat) (index : Nat) : Nat :=
  certificate.getD (coefficientOffset + index) fieldModulus

def topDegreeIndices : List Nat := {lean_nat_list(top_degree_indices)}

def coefficientsValid (certificate : List Nat) : Bool :=
  (List.range coefficientCount).all (fun index =>
    coefficient certificate index < fieldModulus) &&
  topDegreeIndices.any (fun index => coefficient certificate index != 0)

def coefficientIndex (yPower xPower : Nat) : Nat :=
  yPower * coefficientSide - yPower * (yPower - 1) / 2 + xPower

def xPolynomial (certificate : List Nat) (yPower : Nat) : List Nat :=
  (List.range (coefficientSide - yPower)).map (fun xPower =>
    coefficient certificate (coefficientIndex yPower xPower))

def evaluate (certificate : List Nat) (item : Nat) : Nat :=
  let yCoefficients := (List.range coefficientSide).map (fun yPower =>
    AMBenchPrelude.evalPolyMod (xPolynomial certificate yPower)
      (coordinateX certificate item) fieldModulus)
  AMBenchPrelude.evalPolyMod yCoefficients (coordinateY certificate item) fieldModulus

def errorFlag (certificate : List Nat) (item : Nat) : Nat :=
  ((certificate.getD (errorOffset + item / valuesPerWord) 0) /
    (2 ^ (item % valuesPerWord))) % 2

def errorWordsValid (certificate : List Nat) : Bool :=
  (List.range errorWords).all (fun index =>
    certificate.getD (errorOffset + index) 0 < 2 ^ valuesPerWord)

def bitCount (word : Nat) : Nat :=
  (List.range valuesPerWord).foldl (fun total offset =>
    total + (word / (2 ^ offset)) % 2) 0

def mismatchCount (certificate : List Nat) : Nat :=
  (List.range errorWords).foldl (fun total index =>
    total + bitCount (certificate.getD (errorOffset + index) 0)) 0

def readingHolds (certificate : List Nat) (item : Nat) : Bool :=
  let expected := evaluate certificate item
  let observed := readings.getD item fieldModulus
  if errorFlag certificate item == 0 then expected == observed else expected != observed

def readingsHold (certificate : List Nat) : Bool :=
  itemGroups.all (fun group => group.all (readingHolds certificate))

abbrev ProfileEncoded : Prop :=
  numItems = fieldModulus * fieldModulus ∧
  certificateWords = coordinateWords + inverseWords + coefficientCount + errorWords"""
    predicate = """abbrev valid (certificate : List Nat) : Prop :=
  certificate.length = certificateWords ∧
  coordinatesPermuteGrid certificate = true ∧
  incidenceHolds certificate = true ∧
  coefficientsValid certificate = true ∧
  errorWordsValid certificate = true ∧
  mismatchCount certificate = promisedMismatchCount ∧
  readingsHold certificate = true"""
    source = challenge_source(
        declarations=declarations,
        predicate=predicate,
        claim="ProfileEncoded",
    )
    source = source.replace(
        "\nend Challenge\n",
        """

theorem submit (certificate : List Nat)
    (hLength : certificate.length = certificateWords)
    (hCoordinates : coordinatesPermuteGrid certificate = true)
    (hIncidence : incidenceHolds certificate = true)
    (hCoefficients : coefficientsValid certificate = true)
    (hErrorWords : errorWordsValid certificate = true)
    (hMismatchCount : mismatchCount certificate = promisedMismatchCount)
    (hReadings : readingsHold certificate = true) : Target := by
  exact Exists.intro certificate
    (And.intro
      ⟨hLength, hCoordinates, hIncidence, hCoefficients,
        hErrorWords, hMismatchCount, hReadings⟩
      (by decide))

end Challenge
""",
    )
    return LeanCaseBlueprint(
        title=TITLE,
        problem=problem,
        challenge_source=source,
        reference_certificate=certificate,
        public_features={"items": num_items, "blocks": len(blocks)},
        metadata={
            "criterion": "anonymous_affine_plane_then_total_degree_fiber_decode",
            "certificate_entries": len(certificate),
            "coordinate_words": coordinate_words,
            "inverse_words": inverse_words,
            "error_words": error_words,
        },
    )


__all__ = ["CASE_ID", "DEFAULT_PARAMETERS", "TITLE", "build", "render_solution", "solve"]
