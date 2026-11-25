from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

import yaml

from aipbench.core.models import ParticipantEvent, SessionMode, TerminalStatus
from aipbench.tasks.new_structured_closest_vector import (
    CASE_IDS,
    COEFFICIENTS_EVENT_KIND,
    TASK_ID,
    TASK_VERSION,
    create_task,
    evaluate_coefficients,
    recover_paired_equations,
    solve_boolean_cube_lattice,
    solve_construction_a_evaluation,
    solve_low_width_tree_equations,
    solve_path_equations,
    solve_public_c01,
    solve_public_c02,
    solve_public_c03,
    solve_public_c04,
    solve_public_c05,
    solve_public_c06,
    solve_tensor_evaluation_lattice,
)

ROOT = Path(__file__).resolve().parents[2]


class FakeContext:
    @property
    def mode(self) -> SessionMode:
        return SessionMode.DEV

    def random_bytes(self, *, tag: str, length: int) -> bytes:
        del tag
        return b"\x00" * length

    def random_int(self, *, tag: str, lower_inclusive: int, upper_exclusive: int) -> int:
        del tag, upper_exclusive
        return lower_inclusive

    def random_field_element(self, *, tag: str, modulus: int) -> int:
        del tag, modulus
        return 0

    def get_artifact_path(self, artifact_id: str) -> Path:
        return Path(artifact_id)


def generate(
    seed: bytes = b"new-closest-vector-c01-test",
    *,
    case_id: str = "c01",
    parameters: dict[str, Any] | None = None,
) -> Any:
    task = create_task()
    return task.generator.generate(
        instance_seed=seed,
        case_id=case_id,
        case_parameters=parameters or task.case_parameters[case_id],
    )


def submit(generated: Any, coefficients: list[int]) -> Any:
    task = create_task()
    context = FakeContext()
    state = task.protocol.initialize(generated_case=generated, context=context)
    return task.protocol.handle_event(
        state=state,
        event=ParticipantEvent(
            sequence=0,
            kind=COEFFICIENTS_EVENT_KIND,
            payload={"coefficients": coefficients},
        ),
        generated_case=generated,
        context=context,
    )


def test_manifest_yaml_and_case_registration_match() -> None:
    task = create_task()
    assert task.manifest["id"] == TASK_ID
    assert task.manifest["version"] == TASK_VERSION
    assert task.manifest["resources"]["wall_time_seconds"] == 600
    assert task.manifest["resources"]["cpu_cores"] == 4
    assert task.manifest["resources"]["memory_mb"] == 4096
    assert CASE_IDS == ("c01", "c02", "c03", "c04", "c05", "c06")
    for case_id in CASE_IDS:
        case_yaml = yaml.safe_load(
            (ROOT / f"tasks/tier1_np/new_structured_closest_vector/cases/{case_id}.yaml").read_text(
                encoding="utf-8"
            )
        )
        assert case_yaml["parameters"] == task.case_parameters[case_id]


def test_c01_is_deterministic_exact_and_publicly_recoverable() -> None:
    generated = generate()
    assert generated == generate()
    assert generated.public_instance != generate(b"new-cvp-other-seed").public_instance
    public = generated.public_instance
    assert public["ambient_dimension"] == 48
    assert public["rank"] == 24
    assert len(public["basis"]) == 48
    assert all(len(row) == 24 for row in public["basis"])
    assert sum(sum(value != 0 for value in row) for row in public["basis"]) == 24
    assert public["radius_squared_numerator"] > 0

    coefficients = solve_public_c01(public)
    assert len(coefficients) == 24
    assert all(coefficient != 0 for coefficient in coefficients)
    evaluation = evaluate_coefficients(public, list(coefficients))
    assert evaluation.within_radius
    assert evaluation.distance_numerator == public["radius_squared_numerator"]
    assert (
        evaluation.distance_numerator == generated.private_instance["reference_distance_numerator"]
    )
    assert submit(generated, list(coefficients)).terminal_status == TerminalStatus.ACCEPT


def test_any_single_coefficient_change_strictly_exceeds_the_exact_radius() -> None:
    generated = generate()
    coefficients = list(solve_public_c01(generated.public_instance))
    for index in range(len(coefficients)):
        changed = list(coefficients)
        changed[index] += 1
        evaluation = evaluate_coefficients(generated.public_instance, changed)
        assert evaluation.distance_numerator > evaluation.radius_squared_numerator
        assert submit(generated, changed).terminal_status == TerminalStatus.REJECT


def test_private_reference_is_not_an_acceptance_oracle() -> None:
    generated = generate()
    coefficients = list(solve_public_c01(generated.public_instance))
    mutated = replace(
        generated,
        private_instance={
            "reference_coefficients": [0] * generated.public_instance["rank"],
            "reference_distance_numerator": 0,
        },
    )
    assert submit(mutated, coefficients).terminal_status == TerminalStatus.ACCEPT


def test_c02_has_a_hidden_path_system_and_public_reference() -> None:
    generated = generate(b"new-cvp-c02-test", case_id="c02")
    assert generated == generate(b"new-cvp-c02-test", case_id="c02")
    other = generate(b"new-cvp-c02-other", case_id="c02")
    assert generated.public_instance != other.public_instance
    public = generated.public_instance
    assert public["ambient_dimension"] == 256
    assert public["rank"] == 128
    supports = [sum(value != 0 for value in row) for row in public["basis"]]
    assert supports.count(0) == 128
    assert supports.count(1) == 1
    assert supports.count(2) == 127
    assert public["radius_squared_numerator"] > 0

    coefficients = solve_public_c02(public)
    evaluation = evaluate_coefficients(public, list(coefficients))
    assert evaluation.within_radius
    assert evaluation.distance_numerator == public["radius_squared_numerator"]
    assert tuple(generated.private_instance["reference_coefficients"]) == coefficients
    assert submit(generated, list(coefficients)).terminal_status == TerminalStatus.ACCEPT

    changed = list(coefficients)
    changed[len(changed) // 2] += 1
    assert not evaluate_coefficients(public, changed).within_radius


def test_c02_small_instance_matches_exhaustive_oracle() -> None:
    parameters = {
        "rank": 4,
        "minimum_scale": 2,
        "maximum_scale": 4,
        "coefficient_magnitude": 2,
        "residual_magnitude": 2,
    }
    generated = generate(b"new-cvp-c02-oracle", case_id="c02", parameters=parameters)
    public = generated.public_instance
    solved = solve_path_equations(
        basis=public["basis"],
        target=public["target_numerator"],
        denominator=public["denominator"],
    )
    candidates: list[tuple[int, tuple[int, ...]]] = []
    for first in range(-3, 4):
        for second in range(-3, 4):
            for third in range(-3, 4):
                for fourth in range(-3, 4):
                    candidate = (first, second, third, fourth)
                    distance = evaluate_coefficients(public, list(candidate)).distance_numerator
                    candidates.append((distance, candidate))
    optimum = min(distance for distance, _candidate in candidates)
    minimizers = [candidate for distance, candidate in candidates if distance == optimum]
    assert optimum == public["radius_squared_numerator"]
    assert minimizers == [solved]


def test_c03_has_paired_residual_rows_and_a_public_tree_reference() -> None:
    generated = generate(b"new-cvp-c03-test", case_id="c03")
    assert generated == generate(b"new-cvp-c03-test", case_id="c03")
    other = generate(b"new-cvp-c03-other", case_id="c03")
    assert generated.public_instance != other.public_instance
    public = generated.public_instance
    assert public["ambient_dimension"] == 256
    assert public["rank"] == 128
    supports = [sum(value != 0 for value in row) for row in public["basis"]]
    assert supports.count(0) == 0
    assert supports.count(1) == 2
    assert supports.count(2) == 6
    assert supports.count(3) == 248

    equations, targets = recover_paired_equations(
        basis=public["basis"], target=public["target_numerator"]
    )
    assert len(equations) == len(targets) == 128
    coefficients = solve_public_c03(public)
    assert coefficients == solve_low_width_tree_equations(
        basis=equations,
        target=targets,
        denominator=public["denominator"],
    )
    evaluation = evaluate_coefficients(public, list(coefficients))
    assert evaluation.within_radius
    assert evaluation.distance_numerator == public["radius_squared_numerator"]
    assert coefficients == tuple(generated.private_instance["reference_coefficients"])
    assert submit(generated, list(coefficients)).terminal_status == TerminalStatus.ACCEPT

    changed = list(coefficients)
    changed[len(changed) // 3] -= 1
    assert not evaluate_coefficients(public, changed).within_radius


def test_c03_small_instance_matches_exhaustive_oracle() -> None:
    parameters = {
        "rank": 4,
        "branching_factor": 2,
        "minimum_scale": 2,
        "maximum_scale": 4,
        "coefficient_magnitude": 2,
        "residual_magnitude": 2,
    }
    generated = generate(b"new-cvp-c03-oracle", case_id="c03", parameters=parameters)
    public = generated.public_instance
    solved = solve_public_c03(public)
    candidates: list[tuple[int, tuple[int, ...]]] = []
    for first in range(-3, 4):
        for second in range(-3, 4):
            for third in range(-3, 4):
                for fourth in range(-3, 4):
                    candidate = (first, second, third, fourth)
                    distance = evaluate_coefficients(public, list(candidate)).distance_numerator
                    candidates.append((distance, candidate))
    optimum = min(distance for distance, _candidate in candidates)
    minimizers = [candidate for distance, candidate in candidates if distance == optimum]
    assert optimum == public["radius_squared_numerator"]
    assert minimizers == [solved]


def test_c04_is_an_exact_modular_bdd_instance_with_public_decoder() -> None:
    generated = generate(b"new-cvp-c04-test", case_id="c04")
    assert generated == generate(b"new-cvp-c04-test", case_id="c04")
    other = generate(b"new-cvp-c04-other", case_id="c04")
    assert generated.public_instance != other.public_instance
    public = generated.public_instance
    assert public["ambient_dimension"] == public["rank"] == 128
    assert public["denominator"] == 5
    assert public["radius_squared_numerator"] == 672

    coefficients = solve_public_c04(public)
    evaluation = evaluate_coefficients(public, list(coefficients))
    assert evaluation.within_radius
    assert evaluation.distance_numerator == 672
    assert coefficients == tuple(generated.private_instance["reference_coefficients"])
    assert submit(generated, list(coefficients)).terminal_status == TerminalStatus.ACCEPT

    # Simulate the calibrated generic route exactly without a floating-point
    # dependency: real solve on the canonical systematic rows rounds the first
    # twenty noisy message coefficients incorrectly.
    logical_basis = generated.private_instance["reference_coefficients"]
    assert len(logical_basis) == 128
    changed = list(coefficients)
    changed[0] += 1
    assert not evaluate_coefficients(public, changed).within_radius


def test_c04_small_instance_matches_exhaustive_message_oracle() -> None:
    parameters = {
        "code_length": 8,
        "code_dimension": 2,
        "modulus": 11,
        "num_errors": 2,
        "denominator": 5,
        "coefficient_magnitude": 2,
    }
    generated = generate(b"new-cvp-c04-oracle", case_id="c04", parameters=parameters)
    public = generated.public_instance
    solved = solve_construction_a_evaluation(public, dimension=2, num_errors=2)
    optimum = None
    minimizers: list[tuple[int, int]] = []
    # Enumerate every Reed--Solomon message and choose, coordinate by
    # coordinate, the nearest integer in its modulus class. This enumerates
    # every lattice coset and minimizes exactly within each coset.
    modulus = 11
    informative_columns = [
        column
        for column in range(8)
        if any(public_row[column] % modulus for public_row in public["basis"])
    ]
    assert len(informative_columns) == 2
    for constant in range(modulus):
        for linear in range(modulus):
            distance = 0
            for raw, row in zip(public["target_numerator"], public["basis"], strict=True):
                residue = (
                    constant * row[informative_columns[0]] + linear * row[informative_columns[1]]
                ) % modulus
                lower = (raw - 5 * residue) // (5 * modulus)
                distance += min(
                    (5 * (residue + modulus * shift) - raw) ** 2
                    for shift in (lower - 1, lower, lower + 1, lower + 2)
                )
            if optimum is None or distance < optimum:
                optimum = distance
                minimizers = [(constant, linear)]
            elif distance == optimum:
                minimizers.append((constant, linear))
    assert optimum == public["radius_squared_numerator"]
    assert len(minimizers) == 1
    assert evaluate_coefficients(public, list(solved)).distance_numerator == optimum


def test_c05_is_an_exact_tensor_code_bdd_instance_with_public_decoder() -> None:
    generated = generate(b"new-cvp-c05-test", case_id="c05")
    assert generated == generate(b"new-cvp-c05-test", case_id="c05")
    other = generate(b"new-cvp-c05-other", case_id="c05")
    assert generated.public_instance != other.public_instance
    public = generated.public_instance
    assert public["ambient_dimension"] == public["rank"] == 256
    assert public["denominator"] == 13
    assert public["radius_squared_numerator"] == 1_024

    coefficients = solve_public_c05(public)
    evaluation = evaluate_coefficients(public, list(coefficients))
    assert evaluation.within_radius
    assert evaluation.distance_numerator == 1_024
    assert coefficients == tuple(generated.private_instance["reference_coefficients"])
    assert submit(generated, list(coefficients)).terminal_status == TerminalStatus.ACCEPT

    changed = list(coefficients)
    changed[0] -= 1
    assert not evaluate_coefficients(public, changed).within_radius


def test_c05_small_instance_matches_exhaustive_tensor_message_oracle() -> None:
    parameters = {
        "grid_size": 6,
        "component_dimension": 2,
        "modulus": 11,
        "num_errors": 6,
        "denominator": 5,
        "clean_offset": 1,
        "error_offset": -3,
        "coefficient_magnitude": 2,
    }
    generated = generate(b"new-cvp-c05-oracle", case_id="c05", parameters=parameters)
    public = generated.public_instance
    solved = solve_tensor_evaluation_lattice(public, grid_size=6, component_dimension=2)
    modulus = 11
    informative_columns = [
        column for column in range(36) if any(row[column] % modulus for row in public["basis"])
    ]
    assert len(informative_columns) == 4
    optimum = None
    minimizer_count = 0
    for first in range(modulus):
        for second in range(modulus):
            for third in range(modulus):
                for fourth in range(modulus):
                    message = (first, second, third, fourth)
                    distance = 0
                    for raw, row in zip(public["target_numerator"], public["basis"], strict=True):
                        residue = (
                            sum(
                                coefficient * row[column]
                                for coefficient, column in zip(
                                    message, informative_columns, strict=True
                                )
                            )
                            % modulus
                        )
                        lower = (raw - 5 * residue) // (5 * modulus)
                        distance += min(
                            (5 * (residue + modulus * shift) - raw) ** 2
                            for shift in (lower - 1, lower, lower + 1, lower + 2)
                        )
                    if optimum is None or distance < optimum:
                        optimum = distance
                        minimizer_count = 1
                    elif distance == optimum:
                        minimizer_count += 1
    assert optimum == public["radius_squared_numerator"]
    assert minimizer_count == 1
    assert evaluate_coefficients(public, list(solved)).distance_numerator == optimum


def test_c06_is_an_exact_boolean_code_bdd_instance_with_public_decoder() -> None:
    generated = generate(b"new-cvp-c06-test", case_id="c06")
    public = generated.public_instance
    assert public["ambient_dimension"] == public["rank"] == 256
    assert public["denominator"] == 13
    assert public["radius_squared_numerator"] == 976

    coefficients = solve_public_c06(public)
    evaluation = evaluate_coefficients(public, list(coefficients))
    assert evaluation.within_radius
    assert evaluation.distance_numerator == 976
    assert coefficients == tuple(generated.private_instance["reference_coefficients"])
    assert submit(generated, list(coefficients)).terminal_status == TerminalStatus.ACCEPT

    changed = list(coefficients)
    changed[0] += 1
    assert not evaluate_coefficients(public, changed).within_radius


def test_c06_small_instance_matches_exhaustive_boolean_message_oracle() -> None:
    parameters = {
        "cube_dimension": 3,
        "degree": 1,
        "modulus": 11,
        "num_errors": 1,
        "denominator": 5,
        "clean_offset": 1,
        "error_offset": -3,
        "coefficient_magnitude": 2,
        "kernel_shear_layers": 3,
        "kernel_injections_per_code_column": 2,
    }
    generated = generate(b"new-cvp-c06-oracle", case_id="c06", parameters=parameters)
    public = generated.public_instance
    solved = solve_boolean_cube_lattice(public, cube_dimension=3, degree=1)
    modulus = 11
    informative_columns = [
        column for column in range(8) if any(row[column] % modulus for row in public["basis"])
    ]
    assert len(informative_columns) == 4
    optimum = None
    minimizer_count = 0
    for message in __import__("itertools").product(range(modulus), repeat=4):
        distance = 0
        for raw, row in zip(public["target_numerator"], public["basis"], strict=True):
            residue = (
                sum(
                    coefficient * row[column]
                    for coefficient, column in zip(message, informative_columns, strict=True)
                )
                % modulus
            )
            lower = (raw - 5 * residue) // (5 * modulus)
            distance += min(
                (5 * (residue + modulus * shift) - raw) ** 2
                for shift in (lower - 1, lower, lower + 1, lower + 2)
            )
        if optimum is None or distance < optimum:
            optimum = distance
            minimizer_count = 1
        elif distance == optimum:
            minimizer_count += 1
    assert optimum == public["radius_squared_numerator"]
    assert minimizer_count == 1
    assert evaluate_coefficients(public, list(solved)).distance_numerator == optimum


def test_participant_spec_contains_relation_but_no_maintainer_hints() -> None:
    text = (ROOT / "tasks/tier1_np/new_structured_closest_vector/TASK_SPECIFICATION.md").read_text(
        encoding="utf-8"
    )
    lowered = text.lower()
    assert TASK_ID in text and TASK_VERSION in text
    assert "closest_vector.coefficients" in text
    for forbidden in (
        "c01",
        "orthogonal",
        "pivot",
        "residual",
        "rank is 24",
        "48-by-24",
        "solver",
        "worked example",
        "reference_coefficients",
        "paired",
        "tree equation",
        "leaf elimination",
        "bidiagonal",
        "128",
        "256",
        "reed",
        "construction-a",
        "modular evaluation",
        "berlekamp",
        "257",
        "tensor",
        "product code",
        "quotient",
        "grid_size",
        "reed-muller",
        "boolean cube",
        "majority decode",
    ):
        assert forbidden not in lowered
