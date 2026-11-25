"""Independent 600-second Structured Closest Vector task."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from itertools import combinations, product
from pathlib import Path
from typing import Any, Final

from aipbench.core.models import GeneratedCase
from aipbench.core.protocol import ParticipantClient, VirtualAgent
from aipbench.tasks.new_closest_vector_cases import (
    CASE_DEFINITIONS,
    CASE_PARAMETERS,
    NewClosestVectorStream,
    finalize_blueprint,
)
from aipbench.tasks.shared.structured_closest_vector import (
    COEFFICIENTS_EVENT_KIND,
    VIRTUAL_AGENTS,
    ClosestVectorProtocolState,
    ClosestVectorReason,
    CoefficientEvaluation,
    StructuredClosestVectorProtocol,
    evaluate_coefficients,
)

SHARED_VIRTUAL_AGENTS = VIRTUAL_AGENTS

TASK_ID: Final = "t1.new_structured_closest_vector"
TASK_VERSION: Final = "0.1.0"
CASE_IDS: Final = tuple(CASE_PARAMETERS)

TASK_MANIFEST: Final[Mapping[str, Any]] = {
    "id": TASK_ID,
    "version": TASK_VERSION,
    "tier": 1,
    "title": "New Structured Closest Vector",
    "plugin": {"entrypoint": "aipbench.tasks.new_structured_closest_vector:create_task"},
    "protocol": {
        "api_version": "aip/1",
        "mode": "one_shot",
        "public_coin": False,
        "one_shot_eval": True,
        "max_events": 1,
        "participant_feedback": {"dev": "verbose", "eval": "minimal"},
    },
    "randomness": {
        "model": "committed_prg",
        "reveal_on_terminal": True,
        "domain_separation": "required",
    },
    "instance": {
        "public_schema": (
            "tasks/tier1_np/new_structured_closest_vector/schemas/public_instance.schema.json"
        ),
        "private_schema": (
            "tasks/tier1_np/new_structured_closest_vector/schemas/private_instance.schema.json"
        ),
    },
    "resources": {
        "wall_time_seconds": 600,
        "cpu_cores": 4,
        "memory_mb": 4096,
        "disk_mb": 4096,
        "max_artifact_bytes": 8_388_608,
        "max_events": 1,
    },
    "audit": {
        "replay_mode": "strict",
        "require_signature": True,
        "require_seed_commitment": True,
        "require_instance_digest": True,
        "require_event_chain": True,
        "require_seed_reveal": True,
    },
    "scoring": {"primary": "binary_accept", "partial_progress": "coefficients_submitted"},
    "soundness": {
        "class": "deterministic_certificate",
        "statement": (
            "the submitted integer coefficients define a point of the public lattice "
            "whose exact squared distance from the public rational target is at most "
            "the public squared radius"
        ),
    },
}


class NewStructuredClosestVectorGenerator:
    def generate(
        self,
        *,
        instance_seed: bytes,
        case_id: str,
        case_parameters: Mapping[str, Any],
    ) -> GeneratedCase:
        if not isinstance(instance_seed, bytes):
            raise TypeError("instance_seed must be bytes")
        definition = CASE_DEFINITIONS.get(case_id)
        if definition is None:
            raise ValueError(f"unsupported new structured-closest-vector case: {case_id}")
        parameters = dict(definition.parameters)
        parameters.update(case_parameters)
        stream = NewClosestVectorStream(instance_seed)
        finalized = finalize_blueprint(
            blueprint=definition.builder(stream, parameters), stream=stream
        )
        return GeneratedCase(
            task_id=TASK_ID,
            task_version=TASK_VERSION,
            case_id=case_id,
            public_instance=finalized.public_instance,
            private_instance=finalized.private_instance,
            generation_metadata={
                **dict(finalized.generation_metadata),
                "generator": f"new-structured-closest-vector/{case_id}/v1",
                "case_id": case_id,
            },
        )


class NewStructuredClosestVectorProtocol(StructuredClosestVectorProtocol):
    task_id = TASK_ID
    task_version = TASK_VERSION

    @staticmethod
    def _validate_task_identity(generated_case: GeneratedCase) -> None:
        if generated_case.task_id != TASK_ID or generated_case.task_version != TASK_VERSION:
            raise ValueError("generated case does not belong to the new Closest Vector task")

    def public_protocol_description(self, *, generated_case: GeneratedCase) -> Mapping[str, Any]:
        description = dict(super().public_protocol_description(generated_case=generated_case))
        description["event_schemas"] = {
            COEFFICIENTS_EVENT_KIND: {
                "schema_ref": (
                    "tasks/tier1_np/new_structured_closest_vector/schemas/coefficients.schema.json"
                )
            }
        }
        return description


def solve_public_c01(public_instance: Mapping[str, Any]) -> tuple[int, ...]:
    """Recover C01 from public pivot rows and verify the exact relation."""

    raw_basis = public_instance.get("basis")
    raw_target = public_instance.get("target_numerator")
    rank = public_instance.get("rank")
    denominator = public_instance.get("denominator")
    if (
        not isinstance(raw_basis, list)
        or not isinstance(raw_target, list)
        or isinstance(rank, bool)
        or not isinstance(rank, int)
        or isinstance(denominator, bool)
        or not isinstance(denominator, int)
    ):
        raise ValueError("malformed public C01 instance")
    coefficients = [0] * rank
    found = [False] * rank
    for row, target in zip(raw_basis, raw_target, strict=True):
        if not isinstance(row, list) or isinstance(target, bool) or not isinstance(target, int):
            raise ValueError("malformed public C01 matrix")
        nonzero = [(index, value) for index, value in enumerate(row) if value != 0]
        if not nonzero:
            continue
        if len(nonzero) != 1:
            raise ValueError("public C01 row is not a pivot row")
        column, pivot = nonzero[0]
        numerator = target
        divisor = denominator * pivot
        if numerator % divisor != 0 or found[column]:
            raise ValueError("public C01 pivot is inconsistent")
        coefficients[column] = numerator // divisor
        found[column] = True
    if not all(found):
        raise ValueError("public C01 has a missing pivot")
    evaluation = evaluate_coefficients(public_instance, coefficients)
    if not evaluation.within_radius:
        raise ValueError("public C01 recovery exceeds the radius")
    return tuple(coefficients)


def _public_matrix_fields(
    public_instance: Mapping[str, Any],
) -> tuple[list[list[int]], list[int], int, int]:
    raw_basis = public_instance.get("basis")
    raw_target = public_instance.get("target_numerator")
    rank = public_instance.get("rank")
    denominator = public_instance.get("denominator")
    if (
        not isinstance(raw_basis, list)
        or not isinstance(raw_target, list)
        or isinstance(rank, bool)
        or not isinstance(rank, int)
        or isinstance(denominator, bool)
        or not isinstance(denominator, int)
        or len(raw_basis) != len(raw_target)
    ):
        raise ValueError("malformed public matrix fields")
    basis: list[list[int]] = []
    target: list[int] = []
    for raw_row, raw_value in zip(raw_basis, raw_target, strict=True):
        if (
            not isinstance(raw_row, list)
            or len(raw_row) != rank
            or any(isinstance(value, bool) or not isinstance(value, int) for value in raw_row)
            or isinstance(raw_value, bool)
            or not isinstance(raw_value, int)
        ):
            raise ValueError("malformed public matrix row")
        basis.append(raw_row)
        target.append(raw_value)
    return basis, target, rank, denominator


def solve_path_equations(
    *, basis: list[list[int]], target: list[int], denominator: int
) -> tuple[int, ...]:
    """Solve an exactly determined singleton/adjacent-pair path system."""

    if not basis or len(basis) != len(target):
        raise ValueError("equation system must be nonempty and aligned")
    rank = len(basis[0])
    if rank < 1 or any(len(row) != rank for row in basis):
        raise ValueError("equation matrix must be rectangular")
    equations: list[tuple[dict[int, int], int]] = []
    incidence = {column: set() for column in range(rank)}
    for raw_row, raw_target in zip(basis, target, strict=True):
        entries = {column: value for column, value in enumerate(raw_row) if value}
        if not entries:
            continue
        if len(entries) > 2:
            raise ValueError("equation support exceeds the path envelope")
        equation_index = len(equations)
        equations.append((entries, raw_target))
        for column in entries:
            incidence[column].add(equation_index)
    if len(equations) != rank or any(not indices for indices in incidence.values()):
        raise ValueError("public equations are not square and spanning")

    solution: list[int | None] = [None] * rank
    remaining = set(range(len(equations)))
    while remaining:
        progress = False
        for equation_index in sorted(remaining):
            entries, raw_target = equations[equation_index]
            unknown = [column for column in entries if solution[column] is None]
            if len(unknown) != 1:
                continue
            column = unknown[0]
            known_sum = sum(
                coefficient * solution[other]
                for other, coefficient in entries.items()
                if other != column
            )
            numerator = raw_target - denominator * known_sum
            divisor = denominator * entries[column]
            if numerator % divisor:
                raise ValueError("public equation has no integral solution")
            value = numerator // divisor
            if solution[column] is not None and solution[column] != value:
                raise ValueError("public equations are inconsistent")
            solution[column] = value
            remaining.remove(equation_index)
            progress = True
        if not progress:
            raise ValueError("public equation support is not leaf-solvable")
    if any(value is None for value in solution):
        raise ValueError("public equation system left an unknown coefficient")
    return tuple(int(value) for value in solution)


def solve_public_c02(public_instance: Mapping[str, Any]) -> tuple[int, ...]:
    """Recover C02's hidden sparse path equations from public row supports."""

    basis, target, _rank, denominator = _public_matrix_fields(public_instance)
    coefficients = solve_path_equations(
        basis=basis,
        target=target,
        denominator=denominator,
    )
    evaluation = evaluate_coefficients(public_instance, list(coefficients))
    if not evaluation.within_radius:
        raise ValueError("public C02 recovery exceeds the radius")
    return coefficients


def recover_paired_equations(
    *, basis: list[list[int]], target: list[int]
) -> tuple[list[list[int]], list[int]]:
    """Pair rows equal up to sign and average away antisymmetric residuals."""

    if not basis or len(basis) != len(target) or len(basis) % 2:
        raise ValueError("paired equation matrix must have positive even height")
    groups: dict[tuple[int, ...], list[tuple[int, int]]] = {}
    for row_index, (row, _raw_target) in enumerate(zip(basis, target, strict=True)):
        first = next((value for value in row if value), None)
        if first is None:
            raise ValueError("paired equation system has a zero row")
        sign = 1 if first > 0 else -1
        normalized = tuple(sign * value for value in row)
        groups.setdefault(normalized, []).append((sign, row_index))
    if len(groups) * 2 != len(basis) or any(len(group) != 2 for group in groups.values()):
        raise ValueError("public rows do not form unique signed pairs")

    equations: list[list[int]] = []
    equation_targets: list[int] = []
    for normalized, group in sorted(groups.items()):
        normalized_targets = [sign * target[index] for sign, index in group]
        total = sum(normalized_targets)
        if total % 2:
            raise ValueError("paired targets do not have an integral midpoint")
        if normalized_targets[0] == normalized_targets[1]:
            raise ValueError("paired targets have no residual separation")
        equations.append(list(normalized))
        equation_targets.append(total // 2)
    return equations, equation_targets


def solve_low_width_tree_equations(
    *, basis: list[list[int]], target: list[int], denominator: int
) -> tuple[int, ...]:
    """Solve a square sparse elimination system by exposed-variable peeling."""

    if not basis or len(basis) != len(target):
        raise ValueError("tree equation system must be nonempty and aligned")
    rank = len(basis[0])
    if len(basis) != rank or any(len(row) != rank for row in basis):
        raise ValueError("tree equation system must be square")
    remaining_rows = set(range(rank))
    remaining_columns = set(range(rank))
    assignments: dict[int, tuple[int, int]] = {}
    while remaining_rows:
        incidence = {
            column: [row for row in remaining_rows if basis[row][column] != 0]
            for column in remaining_columns
        }
        leaf_columns = sorted(column for column, rows in incidence.items() if len(rows) == 1)
        if not leaf_columns:
            raise ValueError("public sparse system has no eliminable column")
        progress = False
        for column in leaf_columns:
            if column not in remaining_columns:
                continue
            row = incidence[column][0]
            if row not in remaining_rows:
                continue
            assignments[column] = (row, basis[row][column])
            remaining_columns.remove(column)
            remaining_rows.remove(row)
            progress = True
        if not progress:
            raise ValueError("public sparse elimination stalled")
    if remaining_columns or len(assignments) != rank:
        raise ValueError("public sparse system did not yield a full matching")

    solution: list[int | None] = [None] * rank
    for column, (row, pivot) in reversed(tuple(assignments.items())):
        known_sum = sum(
            coefficient * solution[other]
            for other, coefficient in enumerate(basis[row])
            if other != column and coefficient
        )
        if any(
            solution[other] is None
            for other, coefficient in enumerate(basis[row])
            if other != column and coefficient
        ):
            raise ValueError("public sparse back substitution order is invalid")
        numerator = target[row] - denominator * known_sum
        divisor = denominator * pivot
        if numerator % divisor:
            raise ValueError("public sparse equation has no integral solution")
        solution[column] = numerator // divisor
    return tuple(int(value) for value in solution)


def solve_public_c03(public_instance: Mapping[str, Any]) -> tuple[int, ...]:
    """Recover paired equations, eliminate the hidden tree, and verify."""

    basis, target, _rank, denominator = _public_matrix_fields(public_instance)
    equations, equation_targets = recover_paired_equations(basis=basis, target=target)
    coefficients = solve_low_width_tree_equations(
        basis=equations,
        target=equation_targets,
        denominator=denominator,
    )
    evaluation = evaluate_coefficients(public_instance, list(coefficients))
    if not evaluation.within_radius:
        raise ValueError("public C03 recovery exceeds the radius")
    return coefficients


def _modular_inverse(value: int, modulus: int) -> int:
    value %= modulus
    if value == 0:
        raise ValueError("zero has no modular inverse")
    return pow(value, -1, modulus)


def solve_modular_linear_system(
    matrix: list[list[int]], right_hand_side: list[int], *, modulus: int
) -> tuple[int, ...]:
    """Solve a square linear system over a prime field by exact elimination."""

    size = len(matrix)
    if size == 0 or len(right_hand_side) != size or any(len(row) != size for row in matrix):
        raise ValueError("modular system must be nonempty and square")
    work = [
        [*(value % modulus for value in row), right_hand_side[index] % modulus]
        for index, row in enumerate(matrix)
    ]
    for column in range(size):
        pivot = next(
            (row for row in range(column, size) if work[row][column] % modulus),
            None,
        )
        if pivot is None:
            raise ValueError("modular system is singular")
        work[column], work[pivot] = work[pivot], work[column]
        inverse = _modular_inverse(work[column][column], modulus)
        work[column] = [(value * inverse) % modulus for value in work[column]]
        for row in range(size):
            if row == column or work[row][column] == 0:
                continue
            factor = work[row][column]
            work[row] = [
                (left - factor * right) % modulus
                for left, right in zip(work[row], work[column], strict=True)
            ]
    return tuple(work[index][-1] for index in range(size))


def solve_modular_overdetermined_system(
    matrix: list[list[int]], right_hand_side: list[int], *, modulus: int
) -> tuple[int, ...]:
    """Solve a full-column-rank consistent rectangular field system."""

    row_count = len(matrix)
    column_count = len(matrix[0]) if matrix else 0
    if (
        row_count < column_count
        or column_count == 0
        or len(right_hand_side) != row_count
        or any(len(row) != column_count for row in matrix)
    ):
        raise ValueError("modular rectangular system has invalid dimensions")
    work = [
        [*(value % modulus for value in row), right_hand_side[index] % modulus]
        for index, row in enumerate(matrix)
    ]
    pivot_row = 0
    for column in range(column_count):
        pivot = next(
            (row for row in range(pivot_row, row_count) if work[row][column]),
            None,
        )
        if pivot is None:
            raise ValueError("modular rectangular system lacks full column rank")
        work[pivot_row], work[pivot] = work[pivot], work[pivot_row]
        inverse = _modular_inverse(work[pivot_row][column], modulus)
        work[pivot_row] = [(value * inverse) % modulus for value in work[pivot_row]]
        for row in range(row_count):
            if row == pivot_row or work[row][column] == 0:
                continue
            factor = work[row][column]
            work[row] = [
                (left - factor * right) % modulus
                for left, right in zip(work[row], work[pivot_row], strict=True)
            ]
        pivot_row += 1
    if any(all(value == 0 for value in row[:-1]) and row[-1] != 0 for row in work):
        raise ValueError("modular rectangular system is inconsistent")
    return tuple(work[column][-1] for column in range(column_count))


def _polynomial_division_exact(
    numerator: list[int], denominator: list[int], *, modulus: int
) -> tuple[int, ...]:
    while numerator and numerator[-1] % modulus == 0:
        numerator.pop()
    while denominator and denominator[-1] % modulus == 0:
        denominator.pop()
    if not denominator:
        raise ValueError("polynomial denominator is zero")
    quotient = [0] * max(1, len(numerator) - len(denominator) + 1)
    inverse_lead = _modular_inverse(denominator[-1], modulus)
    while len(numerator) >= len(denominator):
        shift = len(numerator) - len(denominator)
        factor = numerator[-1] * inverse_lead % modulus
        quotient[shift] = factor
        for index, value in enumerate(denominator):
            numerator[index + shift] = (numerator[index + shift] - factor * value) % modulus
        while numerator and numerator[-1] % modulus == 0:
            numerator.pop()
    if numerator:
        raise ValueError("Berlekamp--Welch quotient is not exact")
    while len(quotient) > 1 and quotient[-1] == 0:
        quotient.pop()
    return tuple(quotient)


def berlekamp_welch_decode(
    values: list[int], *, dimension: int, num_errors: int, modulus: int
) -> tuple[int, ...]:
    """Recover a degree-bounded evaluation polynomial from exact errors."""

    length = len(values)
    unknowns = dimension + 2 * num_errors
    if unknowns > length or dimension < 1 or num_errors < 0:
        raise ValueError("Berlekamp--Welch dimensions are invalid")
    matrix: list[list[int]] = []
    right_hand_side: list[int] = []
    for point_index in range(length):
        alpha = point_index + 1
        value = values[point_index] % modulus
        row = [pow(alpha, power, modulus) for power in range(dimension + num_errors)]
        row.extend((-value * pow(alpha, power, modulus)) % modulus for power in range(num_errors))
        matrix.append(row)
        right_hand_side.append(value * pow(alpha, num_errors, modulus) % modulus)
    solved = solve_modular_overdetermined_system(matrix, right_hand_side, modulus=modulus)
    numerator = list(solved[: dimension + num_errors])
    denominator = list(solved[dimension + num_errors :]) + [1]
    polynomial = _polynomial_division_exact(numerator, denominator, modulus=modulus)
    if len(polynomial) > dimension:
        raise ValueError("decoded polynomial exceeds the degree bound")
    polynomial = polynomial + (0,) * (dimension - len(polynomial))
    decoded = [
        sum(
            coefficient * pow(alpha, power, modulus) for power, coefficient in enumerate(polynomial)
        )
        % modulus
        for alpha in range(1, length + 1)
    ]
    disagreement_count = sum(
        left != right % modulus for left, right in zip(decoded, values, strict=True)
    )
    if disagreement_count > num_errors:
        raise ValueError("decoded polynomial exceeds the public error envelope")
    return tuple(polynomial)


def _nearest_congruent_integer(
    target_numerator: int, denominator: int, residue: int, modulus: int
) -> int:
    center_numerator = target_numerator - denominator * residue
    step = denominator * modulus
    lower = center_numerator // step
    candidates = (lower - 1, lower, lower + 1, lower + 2)
    shift = min(
        candidates,
        key=lambda value: (abs(center_numerator - step * value), abs(value), value),
    )
    return residue + modulus * shift


def solve_integer_linear_system(matrix: list[list[int]], target: list[int]) -> tuple[int, ...]:
    """Solve a nonsingular integer system using fraction-free elimination."""

    from fractions import Fraction

    size = len(matrix)
    if size == 0 or len(target) != size or any(len(row) != size for row in matrix):
        raise ValueError("integer system must be nonempty and square")
    work = [
        [*(Fraction(value) for value in row), Fraction(target[index])]
        for index, row in enumerate(matrix)
    ]
    for column in range(size):
        pivot = next((row for row in range(column, size) if work[row][column]), None)
        if pivot is None:
            raise ValueError("integer system is singular")
        work[column], work[pivot] = work[pivot], work[column]
        pivot_value = work[column][column]
        for row in range(column + 1, size):
            if work[row][column] == 0:
                continue
            factor = work[row][column] / pivot_value
            for index in range(column, size + 1):
                work[row][index] -= factor * work[column][index]
    solution = [Fraction(0)] * size
    for row in range(size - 1, -1, -1):
        known = sum(work[row][column] * solution[column] for column in range(row + 1, size))
        value = work[row][-1] - known
        solution[row] = value / work[row][row]
    if any(value.denominator != 1 for value in solution):
        raise ValueError("lattice point has nonintegral public coefficients")
    return tuple(value.numerator for value in solution)


def _solve_modular_square_echelon(
    matrix: list[list[int]], target: list[int], *, modulus: int
) -> tuple[int, ...]:
    """Solve one dense square field system with forward elimination/backsolve."""

    size = len(matrix)
    if size == 0 or len(target) != size or any(len(row) != size for row in matrix):
        raise ValueError("modular system must be nonempty and square")
    work = [
        [*(value % modulus for value in row), target[index] % modulus]
        for index, row in enumerate(matrix)
    ]
    for column in range(size):
        pivot = next((row for row in range(column, size) if work[row][column]), None)
        if pivot is None:
            raise ValueError("modular system is singular")
        work[column], work[pivot] = work[pivot], work[column]
        inverse = pow(work[column][column], -1, modulus)
        pivot_row = work[column]
        for row in range(column + 1, size):
            factor = work[row][column] * inverse % modulus
            if factor == 0:
                continue
            current = work[row]
            for index in range(column, size + 1):
                current[index] = (current[index] - factor * pivot_row[index]) % modulus
    solution = [0] * size
    for row in range(size - 1, -1, -1):
        right = work[row][-1] - sum(
            work[row][column] * solution[column] for column in range(row + 1, size)
        )
        solution[row] = right * pow(work[row][row], -1, modulus) % modulus
    return tuple(solution)


def solve_construction_a_evaluation(
    public_instance: Mapping[str, Any], *, dimension: int, num_errors: int
) -> tuple[int, ...]:
    """Recover and decode a public modular evaluation lattice."""

    basis, target, rank, denominator = _public_matrix_fields(public_instance)
    if rank != len(basis) or denominator != 5:
        raise ValueError("public C04 dimensions are malformed")
    modulus_candidates = []
    for candidate in sorted({abs(value) for row in basis for value in row if abs(value) > rank}):
        zero_columns = [
            column for column in range(rank) if all(row[column] % candidate == 0 for row in basis)
        ]
        if len(zero_columns) != rank - dimension:
            continue
        if all(
            sum(value != 0 for value in (row[column] for row in basis)) == 1
            and max(abs(row[column]) for row in basis) == candidate
            for column in zero_columns
        ):
            modulus_candidates.append(candidate)
    if len(modulus_candidates) != 1:
        raise ValueError("public C04 modulus is not uniquely recoverable")
    modulus = modulus_candidates[0]
    modular_rows = [[value % modulus for value in row] for row in basis]
    informative_columns = [
        column for column in range(rank) if any(row[column] for row in modular_rows)
    ]
    if len(informative_columns) != dimension:
        raise ValueError("public C04 code dimension is malformed")

    rounded = []
    for raw in target:
        lower = raw // denominator
        rounded.append(
            min(
                (lower - 1, lower, lower + 1, lower + 2),
                key=lambda value: (abs(denominator * value - raw), abs(value), value),
            )
        )
    constant_columns = [
        column for column in informative_columns if all(abs(row[column]) == 1 for row in basis)
    ]
    if len(constant_columns) != 1:
        raise ValueError("public C04 constant code coordinate is not unique")
    constant_column = constant_columns[0]
    normalized_rows = [
        [row[column] * row[constant_column] % modulus for column in informative_columns]
        for row in basis
    ]
    normalized_values = [
        value * basis[row][constant_column] % modulus for row, value in enumerate(rounded)
    ]
    positive_points = set(range(1, rank + 1))
    negative_points = {(-value) % modulus for value in positive_points}
    point_candidates: list[tuple[int, int]] = []
    for offset, _column in enumerate(informative_columns):
        values = {row[offset] for row in normalized_rows}
        if values == positive_points:
            point_candidates.append((offset, 1))
        elif values == negative_points:
            point_candidates.append((offset, -1))
    if len(point_candidates) != 1:
        raise ValueError("public C04 evaluation coordinate is not unique")
    point_column, point_sign = point_candidates[0]
    point_by_row = [point_sign * row[point_column] % modulus for row in normalized_rows]
    if set(point_by_row) != positive_points:
        raise ValueError("public C04 evaluation points are malformed")
    value_by_point = [0] * rank
    row_by_point = [0] * rank
    for row, point in enumerate(point_by_row):
        value_by_point[point - 1] = normalized_values[row]
        row_by_point[point - 1] = row
    polynomial = berlekamp_welch_decode(
        value_by_point,
        dimension=dimension,
        num_errors=num_errors,
        modulus=modulus,
    )
    normalized_codeword_by_point = [
        sum(
            coefficient * pow(point, power, modulus) for power, coefficient in enumerate(polynomial)
        )
        % modulus
        for point in range(1, rank + 1)
    ]
    codeword = [0] * rank
    for point_index, row in enumerate(row_by_point):
        codeword[row] = (
            normalized_codeword_by_point[point_index] * basis[row][constant_column]
        ) % modulus
    point = [
        _nearest_congruent_integer(raw, denominator, residue, modulus)
        for raw, residue in zip(target, codeword, strict=True)
    ]
    coefficients = solve_integer_linear_system(basis, point)
    evaluation = evaluate_coefficients(public_instance, list(coefficients))
    if not evaluation.within_radius:
        raise ValueError("public C04 recovery exceeds the radius")
    return coefficients


def solve_public_c04(public_instance: Mapping[str, Any]) -> tuple[int, ...]:
    """Recover and decode C04's public modular evaluation lattice."""

    return solve_construction_a_evaluation(public_instance, dimension=20, num_errors=32)


def _decode_with_bounded_errors(
    values: list[int], *, dimension: int, radius: int, modulus: int
) -> tuple[int, ...]:
    for error_count in range(radius + 1):
        try:
            return berlekamp_welch_decode(
                values,
                dimension=dimension,
                num_errors=error_count,
                modulus=modulus,
            )
        except ValueError:
            continue
    raise ValueError("component word exceeds its unique-decoding radius")


def solve_tensor_evaluation_lattice(
    public_instance: Mapping[str, Any], *, grid_size: int, component_dimension: int
) -> tuple[int, ...]:
    """Recover a hidden tensor quotient, decode its rows, and lift the point."""

    basis, target, rank, denominator = _public_matrix_fields(public_instance)
    dimension = component_dimension * component_dimension
    if rank != grid_size * grid_size or rank != len(basis):
        raise ValueError("public tensor lattice dimensions are malformed")
    from math import gcd

    column_gcds = {abs(gcd(*(row[column] for row in basis))) for column in range(rank)}
    modulus_candidates: list[int] = []
    for candidate in sorted(value for value in column_gcds if value > 1):
        zero_columns = [
            column for column in range(rank) if all(row[column] % candidate == 0 for row in basis)
        ]
        if len(zero_columns) != rank - dimension:
            continue
        modulus_candidates.append(candidate)
    if len(modulus_candidates) != 1:
        raise ValueError("public tensor modulus is not uniquely recoverable")
    modulus = modulus_candidates[0]
    modular_rows = [[value % modulus for value in row] for row in basis]
    informative_columns = [
        column for column in range(rank) if any(row[column] for row in modular_rows)
    ]
    if len(informative_columns) != dimension:
        raise ValueError("public tensor code dimension is malformed")
    constant_columns = [
        column
        for column in informative_columns
        if all(row[column] % modulus in (1, modulus - 1) for row in basis)
    ]
    if len(constant_columns) != 1:
        raise ValueError("public tensor constant column is not unique")
    constant_column = constant_columns[0]
    row_signs = [1 if row[constant_column] % modulus == 1 else -1 for row in basis]
    normalized_rows = [
        [row[column] * row_signs[index] % modulus for column in informative_columns]
        for index, row in enumerate(basis)
    ]
    point_multiset = sorted(value for value in range(1, grid_size + 1) for _ in range(grid_size))
    axis_candidates: list[tuple[int, int]] = []
    for offset, _column in enumerate(informative_columns):
        values = sorted(row[offset] for row in normalized_rows)
        if values == point_multiset:
            axis_candidates.append((offset, 1))
        elif sorted((-value) % modulus for value in values) == point_multiset:
            axis_candidates.append((offset, -1))
    if len(axis_candidates) != 2:
        raise ValueError("public tensor axes are not uniquely recoverable")
    (left_column, left_sign), (right_column, right_sign) = axis_candidates
    coordinates = [
        (
            left_sign * row[left_column] % modulus,
            right_sign * row[right_column] % modulus,
        )
        for row in normalized_rows
    ]
    expected_coordinates = {
        (left, right) for left in range(1, grid_size + 1) for right in range(1, grid_size + 1)
    }
    if set(coordinates) != expected_coordinates or len(set(coordinates)) != rank:
        raise ValueError("public tensor grid coordinates are malformed")

    rounded = []
    for raw in target:
        lower = raw // denominator
        rounded.append(
            min(
                (lower - 1, lower, lower + 1, lower + 2),
                key=lambda value: (abs(denominator * value - raw), abs(value), value),
            )
        )
    normalized_symbols = [value * row_signs[row] % modulus for row, value in enumerate(rounded)]
    row_by_coordinate = {coordinate: row for row, coordinate in enumerate(coordinates)}
    component_radius = (grid_size - component_dimension) // 2
    normalized_codeword = [0] * rank
    for left in range(1, grid_size + 1):
        rows = [row_by_coordinate[(left, right)] for right in range(1, grid_size + 1)]
        values = [normalized_symbols[row] for row in rows]
        polynomial = _decode_with_bounded_errors(
            values,
            dimension=component_dimension,
            radius=component_radius,
            modulus=modulus,
        )
        for right, row in enumerate(rows, start=1):
            normalized_codeword[row] = (
                sum(
                    coefficient * pow(right, power, modulus)
                    for power, coefficient in enumerate(polynomial)
                )
                % modulus
            )
    codeword = [value * row_signs[row] % modulus for row, value in enumerate(normalized_codeword)]
    point = [
        _nearest_congruent_integer(raw, denominator, residue, modulus)
        for raw, residue in zip(target, codeword, strict=True)
    ]

    zero_columns = sorted(set(range(rank)) - set(informative_columns))
    systematic_rows = [
        row for row in range(rank) if all(basis[row][column] == 0 for column in zero_columns)
    ]
    if len(systematic_rows) != dimension:
        raise ValueError("public tensor systematic row count is malformed")
    informative_residues = _solve_modular_square_echelon(
        [[basis[row][column] for column in informative_columns] for row in systematic_rows],
        [point[row] for row in systematic_rows],
        modulus=modulus,
    )
    informative_solution = tuple(
        value if value <= modulus // 2 else value - modulus for value in informative_residues
    )
    coefficients = [0] * rank
    for column, value in zip(informative_columns, informative_solution, strict=True):
        coefficients[column] = value
    systematic_row_set = set(systematic_rows)
    kernel_rows = [row for row in range(rank) if row not in systematic_row_set]
    kernel_target = [
        point[row]
        - sum(basis[row][column] * coefficients[column] for column in informative_columns)
        for row in kernel_rows
    ]
    certificate_prime = 1_000_000_007
    kernel_residues = _solve_modular_square_echelon(
        [[basis[row][column] for column in zero_columns] for row in kernel_rows],
        kernel_target,
        modulus=certificate_prime,
    )
    kernel_solution = tuple(
        value if value <= certificate_prime // 2 else value - certificate_prime
        for value in kernel_residues
    )
    for column, value in zip(zero_columns, kernel_solution, strict=True):
        coefficients[column] = value
    evaluation = evaluate_coefficients(public_instance, coefficients)
    if not evaluation.within_radius:
        raise ValueError("public C05 recovery exceeds the radius")
    return tuple(coefficients)


def solve_public_c05(public_instance: Mapping[str, Any]) -> tuple[int, ...]:
    """Recover and decode C05's hidden tensor evaluation lattice."""

    return solve_tensor_evaluation_lattice(public_instance, grid_size=16, component_dimension=12)


def _decode_boolean_polynomial(
    symbols: Mapping[tuple[int, ...], int], *, degree: int, modulus: int
) -> dict[tuple[int, ...], int]:
    """Majority-decode a low-degree multilinear polynomial on a Boolean cube."""

    if not symbols:
        raise ValueError("Boolean evaluation word is empty")
    cube_dimension = len(next(iter(symbols)))
    residual = dict(symbols)
    coefficients: dict[tuple[int, ...], int] = {}
    axes = tuple(range(cube_dimension))
    for size in range(degree, -1, -1):
        for monomial in combinations(axes, size):
            complement = tuple(axis for axis in axes if axis not in monomial)
            derivatives = []
            for complement_values in product((0, 1), repeat=len(complement)):
                fixed = dict(zip(complement, complement_values, strict=True))
                derivative = 0
                for face_values in product((0, 1), repeat=size):
                    point = [0] * cube_dimension
                    for axis, value in fixed.items():
                        point[axis] = value
                    for axis, value in zip(monomial, face_values, strict=True):
                        point[axis] = value
                    sign = -1 if (size - sum(face_values)) % 2 else 1
                    derivative += sign * residual[tuple(point)]
                derivatives.append(derivative % modulus)
            counts = Counter(derivatives)
            value, count = counts.most_common(1)[0]
            if count * 2 <= len(derivatives):
                raise ValueError("Boolean word exceeds its majority-decoding radius")
            coefficients[monomial] = value
            if value:
                for point in residual:
                    if all(point[axis] for axis in monomial):
                        residual[point] = (residual[point] - value) % modulus
    return coefficients


def solve_boolean_cube_lattice(
    public_instance: Mapping[str, Any], *, cube_dimension: int, degree: int
) -> tuple[int, ...]:
    """Recover a Boolean-cube quotient, majority-decode it, and lift."""

    from math import comb, gcd

    basis, target, rank, denominator = _public_matrix_fields(public_instance)
    dimension = sum(comb(cube_dimension, size) for size in range(degree + 1))
    if rank != 1 << cube_dimension or rank != len(basis):
        raise ValueError("public Boolean-cube lattice dimensions are malformed")
    column_gcds = {abs(gcd(*(row[column] for row in basis))) for column in range(rank)}
    candidates = []
    for candidate in sorted(value for value in column_gcds if value > 1):
        zero_columns = [
            column for column in range(rank) if all(row[column] % candidate == 0 for row in basis)
        ]
        if len(zero_columns) == rank - dimension:
            candidates.append((candidate, zero_columns))
    if len(candidates) != 1:
        raise ValueError("public Boolean-cube modulus is not uniquely recoverable")
    modulus, zero_columns = candidates[0]
    zero_column_set = set(zero_columns)
    informative_columns = [column for column in range(rank) if column not in zero_column_set]
    modular_rows = [[value % modulus for value in row] for row in basis]
    constant_columns = [
        column
        for column in informative_columns
        if all(row[column] in (1, modulus - 1) for row in modular_rows)
    ]
    if len(constant_columns) != 1:
        raise ValueError("public Boolean constant column is not unique")
    constant_column = constant_columns[0]
    row_signs = [1 if row[constant_column] == 1 else -1 for row in modular_rows]
    normalized_rows = [
        [row[column] * row_signs[index] % modulus for column in informative_columns]
        for index, row in enumerate(modular_rows)
    ]
    axis_candidates: list[tuple[int, int]] = []
    for offset, _column in enumerate(informative_columns):
        values = [row[offset] for row in normalized_rows]
        if values.count(1) == rank // 2 and values.count(0) == rank // 2:
            axis_candidates.append((offset, 1))
        elif values.count(modulus - 1) == rank // 2 and values.count(0) == rank // 2:
            axis_candidates.append((offset, -1))
    if len(axis_candidates) != cube_dimension:
        raise ValueError("public Boolean axes are not uniquely recoverable")
    coordinates = [
        tuple(sign * row[offset] % modulus for offset, sign in axis_candidates)
        for row in normalized_rows
    ]
    if set(coordinates) != set(product((0, 1), repeat=cube_dimension)):
        raise ValueError("public Boolean coordinates are malformed")

    rounded = []
    for raw in target:
        lower = raw // denominator
        rounded.append(
            min(
                (lower - 1, lower, lower + 1, lower + 2),
                key=lambda value: (abs(denominator * value - raw), abs(value), value),
            )
        )
    symbols = {
        coordinate: rounded[row] * row_signs[row] % modulus
        for row, coordinate in enumerate(coordinates)
    }
    polynomial = _decode_boolean_polynomial(symbols, degree=degree, modulus=modulus)
    normalized_codeword = [
        sum(
            value
            for monomial, value in polynomial.items()
            if all(coordinate[axis] for axis in monomial)
        )
        % modulus
        for coordinate in coordinates
    ]
    codeword = [value * row_signs[row] % modulus for row, value in enumerate(normalized_codeword)]
    point = [
        _nearest_congruent_integer(raw, denominator, residue, modulus)
        for raw, residue in zip(target, codeword, strict=True)
    ]

    systematic_rows = [
        row for row in range(rank) if all(basis[row][column] == 0 for column in zero_columns)
    ]
    if len(systematic_rows) != dimension:
        raise ValueError("public Boolean information set is malformed")
    informative_residues = _solve_modular_square_echelon(
        [[basis[row][column] for column in informative_columns] for row in systematic_rows],
        [point[row] for row in systematic_rows],
        modulus=modulus,
    )
    coefficients = [0] * rank
    for column, residue in zip(informative_columns, informative_residues, strict=True):
        coefficients[column] = residue if residue <= modulus // 2 else residue - modulus
    systematic_set = set(systematic_rows)
    kernel_rows = [row for row in range(rank) if row not in systematic_set]
    kernel_target = [
        point[row]
        - sum(basis[row][column] * coefficients[column] for column in informative_columns)
        for row in kernel_rows
    ]
    certificate_prime = 1_000_000_007
    kernel_residues = _solve_modular_square_echelon(
        [[basis[row][column] for column in zero_columns] for row in kernel_rows],
        kernel_target,
        modulus=certificate_prime,
    )
    for column, residue in zip(zero_columns, kernel_residues, strict=True):
        coefficients[column] = (
            residue if residue <= certificate_prime // 2 else residue - certificate_prime
        )
    evaluation = evaluate_coefficients(public_instance, coefficients)
    if not evaluation.within_radius:
        raise ValueError("public C06 recovery exceeds the radius")
    return tuple(coefficients)


def solve_public_c06(public_instance: Mapping[str, Any]) -> tuple[int, ...]:
    """Recover and decode C06's hidden Boolean-cube evaluation lattice."""

    return solve_boolean_cube_lattice(public_instance, cube_dimension=8, degree=3)


def solve_public(public_instance: Mapping[str, Any]) -> tuple[int, ...]:
    """Dispatch by a validated public structural invariant."""

    basis, _target, _rank, _denominator = _public_matrix_fields(public_instance)
    supports = [sum(value != 0 for value in row) for row in basis]
    maximum_support = max(supports)
    if maximum_support > 25:
        from math import gcd

        divisible_columns = sum(
            abs(gcd(*(row[column] for row in basis))) > 1 for column in range(len(basis[0]))
        )
        return (
            solve_public_c06(public_instance)
            if divisible_columns > 130
            else solve_public_c05(public_instance)
        )
    if maximum_support > 20:
        return solve_public_c04(public_instance)
    if maximum_support == 3 and 0 not in supports:
        return solve_public_c03(public_instance)
    return (
        solve_public_c02(public_instance)
        if maximum_support == 2
        else solve_public_c01(public_instance)
    )


def _participant_instance(client: ParticipantClient) -> Mapping[str, Any]:
    response = client.get_instance()
    nested = response.get("public_instance")
    return nested if isinstance(nested, Mapping) else response


class HonestNewClosestVectorAgent:
    agent_id = "virtual-honest"

    def run(self, *, client: ParticipantClient, workspace: Path) -> None:
        del workspace
        coefficients = solve_public(_participant_instance(client))
        client.submit_event(
            sequence=0,
            kind=COEFFICIENTS_EVENT_KIND,
            payload={"coefficients": list(coefficients)},
        )


_VIRTUAL_AGENT_LIST: Final[tuple[VirtualAgent, ...]] = (
    HonestNewClosestVectorAgent(),
    *SHARED_VIRTUAL_AGENTS.values(),
)
VIRTUAL_AGENTS: Final[Mapping[str, VirtualAgent]] = {
    agent.agent_id: agent for agent in _VIRTUAL_AGENT_LIST
}


@dataclass(frozen=True)
class NewStructuredClosestVectorTaskPlugin:
    manifest: Mapping[str, Any]
    case_parameters: Mapping[str, Mapping[str, Any]]
    generator: NewStructuredClosestVectorGenerator
    protocol: NewStructuredClosestVectorProtocol


def create_task() -> NewStructuredClosestVectorTaskPlugin:
    return NewStructuredClosestVectorTaskPlugin(
        manifest=TASK_MANIFEST,
        case_parameters=CASE_PARAMETERS,
        generator=NewStructuredClosestVectorGenerator(),
        protocol=NewStructuredClosestVectorProtocol(),
    )


__all__ = [
    "CASE_IDS",
    "CASE_PARAMETERS",
    "COEFFICIENTS_EVENT_KIND",
    "CoefficientEvaluation",
    "ClosestVectorProtocolState",
    "ClosestVectorReason",
    "NewStructuredClosestVectorGenerator",
    "NewStructuredClosestVectorProtocol",
    "TASK_ID",
    "TASK_MANIFEST",
    "TASK_VERSION",
    "VIRTUAL_AGENTS",
    "create_task",
    "evaluate_coefficients",
    "recover_paired_equations",
    "berlekamp_welch_decode",
    "solve_path_equations",
    "solve_low_width_tree_equations",
    "solve_integer_linear_system",
    "solve_construction_a_evaluation",
    "solve_modular_linear_system",
    "solve_modular_overdetermined_system",
    "solve_tensor_evaluation_lattice",
    "solve_boolean_cube_lattice",
    "solve_public",
    "solve_public_c01",
    "solve_public_c02",
    "solve_public_c03",
    "solve_public_c04",
    "solve_public_c05",
    "solve_public_c06",
]
