from __future__ import annotations

import hashlib
import itertools
import json
import math
import subprocess
from pathlib import Path
from typing import Any

import pytest

from aipbench.core.errors import ErrorCode
from aipbench.core.models import GeneratedCase, ParticipantEvent, SessionMode, TerminalStatus
from aipbench.registry import load_manifest, validate_manifest
from aipbench.tasks import machine_checked_mathematics as lean_task
from aipbench.tasks.machine_checked_mathematics import (
    CASE_IDS,
    CASE_PARAMETERS,
    CASE_TITLES,
    LEAN_TOOLCHAIN,
    PROOF_EVENT_KIND,
    TASK_MANIFEST,
    LeanReason,
    MachineCheckedMathematicsProtocol,
    create_task,
    find_lean_executable,
    solve_public_instance,
    verify_lean_solution,
)
from aipbench.tasks.machine_checked_mathematics_cases import c01, c02, c03, c04, c05, c06, c07, c08
from aipbench.tasks.machine_checked_mathematics_cases.common import lean_nat_list


class FakeContext:
    def __init__(self, artifacts: dict[str, Path] | None = None) -> None:
        self.artifacts = artifacts or {}

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
        return self.artifacts[artifact_id]


def generated_case(case_id: str = "c01", seed: bytes = b"t3.1-unit") -> GeneratedCase:
    return create_task().generator.generate(
        instance_seed=seed,
        case_id=case_id,
        case_parameters={},
    )


def test_lean_subprocess_uses_only_platform_supported_creation_flags(
    monkeypatch: Any,
    tmp_path: Path,
) -> None:
    captured: dict[str, Any] = {}

    def fake_run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        captured.update(kwargs)
        return subprocess.CompletedProcess(args[0], 0, "", "")

    monkeypatch.setattr(lean_task.subprocess, "run", fake_run)
    lean_task._run_checked(
        Path("lean"),
        ["--version"],
        cwd=tmp_path,
        timeout_seconds=1.0,
    )

    expected = lean_task._WINDOWS_CREATE_NO_WINDOW if lean_task.os.name == "nt" else 0
    assert captured["creationflags"] == expected


def test_manifest_and_all_eight_case_contracts_are_frozen() -> None:
    task = create_task()
    assert CASE_IDS == ("c01", "c02", "c03", "c04", "c05", "c06", "c07", "c08")
    assert tuple(task.case_parameters) == CASE_IDS
    assert tuple(CASE_TITLES) == CASE_IDS
    assert task.manifest["id"] == "t3.machine_checked_mathematics"
    assert task.manifest["resources"]["wall_time_seconds"] == 600
    assert task.manifest["resources"]["max_artifact_bytes"] == 262_144
    assert task.manifest["protocol"]["mode"] == "one_shot"
    assert validate_manifest(TASK_MANIFEST).id == "t3.machine_checked_mathematics"
    yaml_manifest = load_manifest("tasks/tier3_applied/machine_checked_mathematics/task.yaml")
    yaml_data = yaml_manifest.as_dict()
    plugin_data = validate_manifest(TASK_MANIFEST).as_dict()
    yaml_instance = yaml_data.pop("instance")
    plugin_instance = plugin_data.pop("instance")
    assert yaml_data == plugin_data
    assert plugin_instance["public_schema"].endswith(yaml_instance["public_schema"])
    assert plugin_instance["private_schema"].endswith(yaml_instance["private_schema"])


@pytest.mark.parametrize("case_id", CASE_IDS)
def test_generator_is_deterministic_public_and_solved_from_public_data(case_id: str) -> None:
    first = generated_case(case_id, b"same-seed")
    second = generated_case(case_id, b"same-seed")
    assert first == second
    assert first.public_instance["toolchain"] == LEAN_TOOLCHAIN
    assert first.public_instance["target_name"] == "Challenge.Target"
    assert first.public_instance["proof_name"] == "AMBenchSolution.proof"
    assert "reference" not in json.dumps(first.public_instance, sort_keys=True).lower()
    source = solve_public_instance(first.public_instance, case_id)
    assert source == first.private_instance["reference_solution"]
    assert "theorem proof : Challenge.Target" in source


def test_redesigned_c01_has_a_unique_nontrivial_public_binary_certificate() -> None:
    case = generated_case("c01", b"redesigned-c01-profile")
    problem = case.public_instance["problem"]
    dimension = problem["dimension"]
    rows = problem["rows"]
    rhs = problem["rhs"]
    certificate = tuple(case.private_instance["reference_certificate"])

    assert dimension == 80
    assert len(rows) == len(rhs) == len(certificate) == dimension
    assert set(certificate) == {0, 1}
    assert dimension // 3 <= sum(certificate) <= 2 * dimension // 3
    assert all(
        len(row) == len(set(row)) and all(0 <= column < dimension for column in row) for row in rows
    )
    assert 2_000 <= sum(map(len, rows)) <= 4_500
    assert all(
        sum(certificate[column] for column in row) % 2 == value
        for row, value in zip(rows, rhs, strict=True)
    )
    assert c01.solve(problem) == certificate
    other = generated_case("c01", b"redesigned-c01-profile-other")
    assert other.public_instance["problem"] != problem


def test_redesigned_c01_public_solver_matches_a_small_exhaustive_oracle() -> None:
    case = create_task().generator.generate(
        instance_seed=b"redesigned-c01-small-oracle",
        case_id="c01",
        case_parameters={"dimension": 8},
    )
    problem = case.public_instance["problem"]
    satisfying = [
        bits
        for bits in itertools.product((0, 1), repeat=problem["dimension"])
        if all(
            sum(bits[column] for column in row) % 2 == value
            for row, value in zip(problem["rows"], problem["rhs"], strict=True)
        )
    ]
    assert satisfying == [c01.solve(problem)]


def test_redesigned_c02_has_a_unique_nontrivial_public_crt_certificate() -> None:
    case = generated_case("c02", b"redesigned-c02-profile")
    problem = case.public_instance["problem"]
    moduli = tuple(problem["moduli"])
    residues = tuple(problem["residues"])
    product = problem["modulus_product"]
    certificate = tuple(case.private_instance["reference_certificate"])
    solution, *quotients = certificate

    assert len(moduli) == len(residues) == len(quotients) == 12
    assert product == math.prod(moduli)
    assert 235 <= product.bit_length() <= 250
    assert product // 3 <= solution <= (2 * product) // 3
    assert len(str(solution)) >= 70
    assert all(
        math.gcd(modulus, previous) == 1
        for index, modulus in enumerate(moduli)
        for previous in moduli[:index]
    )
    assert all(
        solution == residue + quotient * modulus
        for modulus, residue, quotient in zip(moduli, residues, quotients, strict=True)
    )
    assert c02.solve(problem) == certificate
    assert "theorem submit" in case.public_instance["challenge_source"]
    assert "planted" not in json.dumps(case.public_instance).lower()


def test_redesigned_c02_public_solver_matches_a_small_exhaustive_oracle() -> None:
    case = create_task().generator.generate(
        instance_seed=b"redesigned-c02-small-oracle",
        case_id="c02",
        case_parameters={"num_congruences": 3, "prime_floor": 3, "prime_window": 8},
    )
    problem = case.public_instance["problem"]
    satisfying = [
        candidate
        for candidate in range(problem["modulus_product"])
        if all(
            candidate % modulus == residue
            for modulus, residue in zip(problem["moduli"], problem["residues"], strict=True)
        )
    ]
    assert satisfying == [c02.solve(problem)[0]]


def test_participant_specification_does_not_disclose_c01_through_c08_methods() -> None:
    specification = (
        Path("tasks/tier3_applied/machine_checked_mathematics/TASK_SPECIFICATION.md")
        .read_text(encoding="utf-8")
        .lower()
    )
    for leaked_hint in (
        "binary linear",
        "gaussian",
        "row reduction",
        "gf(2)",
        "full-rank",
        "finite-field irreducibility",
        "chinese remainder",
        "crt",
        "modular inverse",
        "pairwise-coprime",
        "line graph",
        "four-clique",
        "bron--kerbosch",
        "root graph",
        "double line",
        "affine synchronization",
        "berlekamp",
        "welch",
        "error locator",
        "reed-solomon",
        "noisy polynomial",
        "transition path",
        "affine plane",
        "coordinatization",
        "parallel line",
        "parallel class",
        "bivariate",
        "fiberwise",
        "product code",
        "generalized reed",
        "reed--muller",
        "unlabeled distance",
        "distance geometry",
        "pairwise distance",
        "turnpike",
        "parabola",
        "parabolic",
        "spectral factor",
        "latin operation",
        "latin square",
        "quasigroup",
        "isotopy",
        "cayley table",
        "group normalization",
        "symmetric group",
        "dihedral",
        "rotation_order",
        "group isotope",
        "word tree",
        "row permutation",
        "column permutation",
        "symbol permutation",
        "generating pair",
        "projective conic",
        "veronese",
        "mobius",
        "möbius",
        "rational normal curve",
        "quadratic curve",
        "pgl(2)",
        "pgl(3)",
        "four-anchor",
        "parameter pencil",
        "factorization",
        "factorisation",
        "rsa",
        "cube root",
        "sixth root",
        "latent integer",
        "structured prime",
        "miller--rabin",
        "fermat method",
        "pollard",
        "subset sum",
        "superincreasing",
        "merkle--hellman",
        "merkle-hellman",
        "knapsack",
        "greedy decode",
        "hidden weights",
        "secret multiplier",
        "syndrome decoding",
        "bch code",
        "berlekamp",
        "massey",
        "chien search",
        "parity-check code",
        "hidden code",
    ):
        assert leaked_hint not in specification


def test_redesigned_c02_public_submit_helper_has_a_simple_kernel_checked_route() -> None:
    executable = find_lean_executable()
    if executable is None:
        pytest.skip("pinned Lean toolchain is unavailable")
    case = generated_case("c02", b"redesigned-c02-helper-kernel")
    certificate = tuple(case.private_instance["reference_certificate"])
    source = f"""import Challenge

namespace AMBenchSolution
theorem proof : Challenge.Target :=
  Challenge.submit {lean_nat_list(certificate)} (by decide)
end AMBenchSolution
"""
    result = verify_lean_solution(
        public_instance=case.public_instance,
        solution_content=source.encode("utf-8"),
        lean_executable=executable,
    )
    assert "does not depend on any axioms" in result.stdout_tail


def _decode_c03_certificate(
    certificate: tuple[int, ...], *, public_vertices: int, root_vertices: int
) -> tuple[tuple[int, int], ...]:
    code_base = root_vertices * root_vertices
    codes = tuple(
        (certificate[vertex // 8] // code_base ** (vertex % 8)) % code_base
        for vertex in range(public_vertices)
    )
    return tuple((code // root_vertices, code % root_vertices) for code in codes)


def test_redesigned_c03_recovers_a_nontrivial_four_regular_line_graph_root() -> None:
    case = generated_case("c03", b"redesigned-c03-profile")
    problem = case.public_instance["problem"]
    public_vertices = problem["num_public_vertices"]
    root_vertices = problem["num_root_vertices"]
    edges = {tuple(edge) for edge in problem["edges"]}
    certificate = tuple(case.private_instance["reference_certificate"])
    pairs = _decode_c03_certificate(
        certificate,
        public_vertices=public_vertices,
        root_vertices=root_vertices,
    )

    assert (public_vertices, root_vertices, len(edges), len(certificate)) == (192, 96, 576, 24)
    assert len(set(pairs)) == public_vertices
    assert all(0 <= left < right < root_vertices for left, right in pairs)
    assert all(sum(root in pair for pair in pairs) == 4 for root in range(root_vertices))
    realized = {
        (left, right)
        for left, right in itertools.combinations(range(public_vertices), 2)
        if set(pairs[left]) & set(pairs[right])
    }
    assert realized == edges
    degrees = [0] * public_vertices
    for left, right in edges:
        degrees[left] += 1
        degrees[right] += 1
    assert set(degrees) == {6}
    assert c03.solve(problem) == certificate


def test_redesigned_c03_small_exhaustive_clique_oracle_reconstructs_public_graph() -> None:
    case = create_task().generator.generate(
        instance_seed=b"redesigned-c03-small-oracle",
        case_id="c03",
        case_parameters={"base_vertices": 8},
    )
    problem = case.public_instance["problem"]
    public_vertices = problem["num_public_vertices"]
    root_vertices = problem["num_root_vertices"]
    edges = {tuple(edge) for edge in problem["edges"]}
    adjacency = [set() for _ in range(public_vertices)]
    for left, right in edges:
        adjacency[left].add(right)
        adjacency[right].add(left)
    four_cliques = tuple(
        candidate
        for candidate in itertools.combinations(range(public_vertices), 4)
        if all(right in adjacency[left] for left, right in itertools.combinations(candidate, 2))
    )
    assert len(four_cliques) == root_vertices == 12
    memberships = [
        tuple(index for index, clique in enumerate(four_cliques) if vertex in clique)
        for vertex in range(public_vertices)
    ]
    assert {len(membership) for membership in memberships} == {2}
    realized = {
        (left, right)
        for left, right in itertools.combinations(range(public_vertices), 2)
        if set(memberships[left]) & set(memberships[right])
    }
    assert realized == edges


def test_redesigned_c03_public_submit_helper_is_kernel_checked() -> None:
    executable = find_lean_executable()
    if executable is None:
        pytest.skip("pinned Lean toolchain is unavailable")
    case = generated_case("c03", b"redesigned-c03-helper-kernel")
    certificate = tuple(case.private_instance["reference_certificate"])
    source = f"""import Challenge

namespace AMBenchSolution
theorem proof : Challenge.Target :=
  Challenge.submit {lean_nat_list(certificate)} (by decide)
end AMBenchSolution
"""
    result = verify_lean_solution(
        public_instance=case.public_instance,
        solution_content=source.encode("utf-8"),
        lean_executable=executable,
    )
    assert "does not depend on any axioms" in result.stdout_tail


def _decode_c04_certificate(
    certificate: tuple[int, ...], *, modulus: int, degree: int
) -> tuple[tuple[int, ...], tuple[int, ...], tuple[int, ...], tuple[int, ...]]:
    items = modulus * modulus
    coordinate_words = modulus
    inverse_offset = coordinate_words
    coefficient_offset = inverse_offset + modulus
    error_offset = coefficient_offset + (degree + 1) * (degree + 2) // 2
    coordinate_codes = tuple(
        (certificate[item // modulus] // items ** (item % modulus)) % items for item in range(items)
    )
    inverse_items = tuple(
        (certificate[inverse_offset + code // modulus] // items ** (code % modulus)) % items
        for code in range(items)
    )
    coefficients = certificate[coefficient_offset:error_offset]
    error_flags = tuple(
        (certificate[error_offset + item // modulus] // 2 ** (item % modulus)) % 2
        for item in range(items)
    )
    return coordinate_codes, inverse_items, coefficients, error_flags


def test_redesigned_c04_recovers_anonymous_affine_plane_and_bivariate_codeword() -> None:
    case = generated_case("c04", b"redesigned-c04-profile")
    problem = case.public_instance["problem"]
    modulus = problem["modulus"]
    items = problem["num_items"]
    degree = problem["polynomial_degree"]
    mismatch_count = problem["mismatch_count"]
    blocks = tuple(tuple(block) for block in problem["incidence_blocks"])
    readings = tuple(problem["readings"])
    certificate = tuple(case.private_instance["reference_certificate"])
    coordinate_codes, inverse_items, coefficients, error_flags = _decode_c04_certificate(
        certificate,
        modulus=modulus,
        degree=degree,
    )

    assert (modulus, items, degree, mismatch_count, len(certificate)) == (19, 361, 8, 72, 102)
    assert len(blocks) == modulus * (modulus + 1) == 380
    assert {len(block) for block in blocks} == {modulus}
    assert set(coordinate_codes) == set(range(items))
    assert all(inverse_items[code] == item for item, code in enumerate(coordinate_codes))
    origin, x_unit = blocks[0][:2]
    y_unit = next(item for item in range(items) if item not in set(blocks[0]))
    assert (coordinate_codes[origin], coordinate_codes[x_unit], coordinate_codes[y_unit]) == (
        0,
        1,
        modulus,
    )
    coordinates = tuple((code % modulus, code // modulus) for code in coordinate_codes)
    for block in blocks:
        first, second = block[:2]
        ax, ay = coordinates[first]
        bx, by = coordinates[second]
        assert all(
            ((bx - ax) * (coordinates[item][1] - ay)) % modulus
            == ((by - ay) * (coordinates[item][0] - ax)) % modulus
            for item in block
        )
    assert len(coefficients) == (degree + 1) * (degree + 2) // 2
    assert all(0 <= coefficient < modulus for coefficient in coefficients)
    top_degree_indices = [
        y * (degree + 1) - y * (y - 1) // 2 + degree - y for y in range(degree + 1)
    ]
    assert any(coefficients[index] != 0 for index in top_degree_indices)
    assert set(error_flags) == {0, 1}
    assert sum(error_flags) == mismatch_count
    actual_mismatches = tuple(
        int(c04._eval_bivariate(coefficients, x, y, degree, modulus) != reading)
        for (x, y), reading in zip(coordinates, readings, strict=True)
    )
    assert actual_mismatches == error_flags
    errors_by_row = [0] * modulus
    for (_, y), flag in zip(coordinates, error_flags, strict=True):
        errors_by_row[y] += flag
    assert sorted(errors_by_row) == [2] * 17 + [19] * 2
    assert 2 * mismatch_count < modulus * (modulus - degree)
    assert c04.solve(problem) == certificate


def test_redesigned_c04_public_solver_matches_small_exhaustive_oracle() -> None:
    case = create_task().generator.generate(
        instance_seed=b"redesigned-c04-small-oracle",
        case_id="c04",
        case_parameters={
            "field_modulus": 7,
            "polynomial_degree": 1,
            "fully_corrupted_rows": 1,
            "errors_per_other_row": 1,
        },
    )
    problem = case.public_instance["problem"]
    certificate = tuple(case.private_instance["reference_certificate"])
    coordinate_codes, inverse_items, coefficients, _ = _decode_c04_certificate(
        certificate,
        modulus=7,
        degree=1,
    )
    coordinates = tuple((code % 7, code // 7) for code in coordinate_codes)
    readings = tuple(problem["readings"])
    satisfying = [
        candidate
        for candidate in itertools.product(range(7), repeat=3)
        if (candidate[1] != 0 or candidate[2] != 0)
        and sum(
            c04._eval_bivariate(candidate, x, y, 1, 7) != reading
            for (x, y), reading in zip(coordinates, readings, strict=True)
        )
        == problem["mismatch_count"]
    ]
    assert satisfying == [coefficients]
    assert set(coordinate_codes) == set(range(49))
    assert all(inverse_items[code] == item for item, code in enumerate(coordinate_codes))
    assert 2 * problem["mismatch_count"] < 7 * (7 - 1)


def test_redesigned_c04_public_submit_helper_is_kernel_checked() -> None:
    executable = find_lean_executable()
    if executable is None:
        pytest.skip("pinned Lean toolchain is unavailable")
    case = generated_case("c04", b"redesigned-c04-helper-kernel")
    certificate = tuple(case.private_instance["reference_certificate"])
    source = c04.render_solution(certificate)
    result = verify_lean_solution(
        public_instance=case.public_instance,
        solution_content=source.encode("utf-8"),
        lean_executable=executable,
    )
    assert "does not depend on any axioms" in result.stdout_tail


def _decode_c05_certificate(
    certificate: tuple[int, ...], *, columns: int
) -> tuple[
    tuple[tuple[int, ...], ...],
    tuple[tuple[int, ...], ...],
    tuple[int, ...],
    tuple[int, ...],
    tuple[int, ...],
]:
    transform = tuple(tuple(certificate[3 * row : 3 * row + 3]) for row in range(3))
    inverse = tuple(tuple(certificate[9 + 3 * row : 12 + 3 * row]) for row in range(3))
    scales = certificate[18 : 18 + columns]
    words = (columns + 9) // 10
    permutation_offset = 18 + columns
    inverse_offset = permutation_offset + words
    permutation = tuple(
        (certificate[permutation_offset + index // 10] // columns ** (index % 10)) % columns
        for index in range(columns)
    )
    inverse_permutation = tuple(
        (certificate[inverse_offset + index // 10] // columns ** (index % 10)) % columns
        for index in range(columns)
    )
    return transform, inverse, scales, permutation, inverse_permutation


def test_redesigned_c05_recovers_anonymous_modular_column_equivalence() -> None:
    case = generated_case("c05", b"redesigned-c05-v3-profile")
    problem = case.public_instance["problem"]
    modulus = problem["modulus"]
    columns = problem["num_columns"]
    left = tuple(tuple(row) for row in problem["left_matrix"])
    right = tuple(tuple(row) for row in problem["right_matrix"])
    certificate = tuple(case.private_instance["reference_certificate"])
    transform, inverse, scales, permutation, inverse_permutation = _decode_c05_certificate(
        certificate, columns=columns
    )

    assert (modulus, columns, len(certificate)) == (1009, 80, 114)
    assert len(left) == len(right) == 3
    assert all(len(row) == columns for matrix in (left, right) for row in matrix)
    assert all(0 <= value < modulus for matrix in (left, right) for row in matrix for value in row)
    identity = ((1, 0, 0), (0, 1, 0), (0, 0, 1))
    assert c05._mat_mul(transform, inverse, modulus) == identity
    assert c05._mat_mul(inverse, transform, modulus) == identity
    assert all(0 < scale < modulus for scale in scales)
    assert set(permutation) == set(range(columns))
    assert all(inverse_permutation[permutation[index]] == index for index in range(columns))
    assert all(
        scales[column]
        * sum(transform[row][inner] * left[inner][column] for inner in range(3))
        % modulus
        == right[row][permutation[column]]
        for column in range(columns)
        for row in range(3)
    )
    assert c05.solve(problem) == certificate
    public_text = json.dumps(case.public_instance, sort_keys=True).lower()
    assert all(
        hidden not in public_text
        for hidden in (
            "conic",
            "veronese",
            "mobius",
            "möbius",
            "rational normal",
            "quadratic curve",
            "pgl",
            "parameter pencil",
        )
    )
    assert "theorem submit" in case.public_instance["challenge_source"]


def test_redesigned_c05_public_recovery_matches_a_tiny_exhaustive_oracle() -> None:
    modulus = 11
    base = tuple((1, value, value * value % modulus) for value in range(6))
    left_transform = ((1, 2, 0), (0, 1, 1), (1, 0, 1))
    right_transform = ((2, 0, 1), (1, 1, 0), (0, 1, 1))
    parameter_transform = ((2, 1), (1, 1))
    left_order = (2, 5, 1, 4, 0, 3)
    right_order = (4, 1, 5, 0, 3, 2)
    left_columns = [
        tuple(
            (index + 2) * value % modulus
            for value in c05._mat_vec(left_transform, base[index], modulus)
        )
        for index in left_order
    ]
    transformed_parameters = [
        c05._mat_vec(parameter_transform, (value, 1), modulus) for value in range(6)
    ]
    right_base = [
        (v * v % modulus, u * v % modulus, u * u % modulus) for u, v in transformed_parameters
    ]
    right_columns = [
        tuple(
            (index + 3) * value % modulus
            for value in c05._mat_vec(right_transform, right_base[index], modulus)
        )
        for index in right_order
    ]
    problem = {
        "modulus": modulus,
        "num_columns": 6,
        "left_matrix": tuple(tuple(column[row] for column in left_columns) for row in range(3)),
        "right_matrix": tuple(tuple(column[row] for column in right_columns) for row in range(3)),
    }
    certificate = c05.solve(problem)
    _, _, _, recovered, _ = _decode_c05_certificate(certificate, columns=6)
    satisfying: list[tuple[int, ...]] = []
    for candidate in itertools.permutations(range(6)):
        try:
            c05._matrix_from_correspondence(left_columns, right_columns, candidate, modulus)
        except ValueError:
            continue
        satisfying.append(candidate)
    assert satisfying
    assert recovered in satisfying


def test_redesigned_c05_public_recovery_is_seed_robust() -> None:
    for seed_index in range(4):
        case = generated_case("c05", f"redesigned-c05-v3/{seed_index}".encode())
        problem = case.public_instance["problem"]
        certificate = tuple(case.private_instance["reference_certificate"])
        assert c05.solve(problem) == certificate
        assert len(certificate) == 114


def test_redesigned_c05_public_submit_helper_is_kernel_checked() -> None:
    executable = find_lean_executable()
    if executable is None:
        pytest.skip("pinned Lean toolchain is unavailable")
    case = generated_case("c05", b"redesigned-c05-helper-kernel")
    source = c05.render_solution(tuple(case.private_instance["reference_certificate"]))
    result = verify_lean_solution(
        public_instance=case.public_instance,
        solution_content=source.encode("utf-8"),
        lean_executable=executable,
    )
    assert "does not depend on any axioms" in result.stdout_tail


def test_redesigned_c06_has_a_nontrivial_factor_and_cube_root_certificate() -> None:
    case = generated_case("c06", b"redesigned-c06-profile")
    problem = case.public_instance["problem"]
    modulus = int(problem["modulus"])
    ciphertext = int(problem["ciphertext"])
    exponent = int(problem["exponent"])
    first, second, root = (int(value) for value in case.private_instance["reference_certificate"])

    assert exponent == 3
    assert 760 <= modulus.bit_length() <= 770
    assert 1 < first < modulus and 1 < second < modulus
    assert first != second and first * second == modulus
    assert first % 3 == second % 3 == 2
    assert 0 <= root < modulus
    assert pow(root, exponent, modulus) == ciphertext
    assert c06.solve(problem) == (first, second, root)
    public_text = json.dumps(case.public_instance, sort_keys=True).lower()
    assert all(
        hidden not in public_text
        for hidden in (
            "latent",
            "quadratic_coefficient",
            "miller",
            "sixth",
            "structured_factor",
        )
    )


def test_redesigned_c06_public_recovery_matches_a_tiny_exhaustive_oracle() -> None:
    case = create_task().generator.generate(
        instance_seed=b"redesigned-c06-small-oracle",
        case_id="c06",
        case_parameters={"latent_bits": 3},
    )
    problem = case.public_instance["problem"]
    modulus = int(problem["modulus"])
    ciphertext = int(problem["ciphertext"])
    divisors = [
        candidate for candidate in range(2, math.isqrt(modulus) + 1) if modulus % candidate == 0
    ]
    assert len(divisors) == 1
    first = divisors[0]
    second = modulus // first
    totient = (first - 1) * (second - 1)
    root = pow(ciphertext, pow(3, -1, totient), modulus)
    reference = tuple(case.private_instance["reference_certificate"])
    assert {reference[0], reference[1]} == {first, second}
    assert reference[2] == root
    assert c06.solve(problem) == reference


def test_redesigned_c06_public_recovery_is_seed_robust() -> None:
    for seed_index in range(6):
        case = generated_case("c06", f"redesigned-c06/{seed_index}".encode())
        certificate = tuple(case.private_instance["reference_certificate"])
        assert c06.solve(case.public_instance["problem"]) == certificate
        assert len(certificate) == 3


def test_redesigned_c06_reference_is_kernel_checked() -> None:
    executable = find_lean_executable()
    if executable is None:
        pytest.skip("pinned Lean toolchain is unavailable")
    case = generated_case("c06", b"redesigned-c06-helper-kernel")
    result = verify_lean_solution(
        public_instance=case.public_instance,
        solution_content=str(case.private_instance["reference_solution"]).encode("utf-8"),
        lean_executable=executable,
    )
    assert "does not depend on any axioms" in result.stdout_tail


def _decode_c07_certificate(
    certificate: tuple[int, ...], *, count: int, word_bits: int
) -> tuple[tuple[int, ...], tuple[int, ...]]:
    word_count = (count + word_bits - 1) // word_bits
    bits = c07._unpack_bits(certificate[:word_count], count, word_bits)
    return bits, certificate[word_count:]


def test_redesigned_c07_is_a_nontrivial_exact_modular_subset_certificate() -> None:
    case = generated_case("c07", b"redesigned-c07-profile")
    problem = case.public_instance["problem"]
    count = int(problem["num_items"])
    word_bits = int(problem["word_bits"])
    modulus = int(problem["modulus"])
    weights = tuple(int(value) for value in problem["weights"])
    target = int(problem["target"])
    certificate = tuple(case.private_instance["reference_certificate"])
    bits, residues = _decode_c07_certificate(certificate, count=count, word_bits=word_bits)

    assert (count, word_bits, modulus.bit_length(), len(certificate)) == (256, 32, 266, 24)
    assert len(weights) == count and len(set(weights)) == count
    assert all(0 < weight < modulus for weight in weights)
    assert set(bits) == {0, 1} and sum(bits) == count // 2
    assert len(residues) == 16 and all(0 <= residue < modulus for residue in residues)
    assert residues == tuple(
        sum(weights[index] * bits[index] for index in range(offset, offset + 16)) % modulus
        for offset in range(0, count, 16)
    )
    assert sum(residues) % modulus == target
    assert c07.solve(problem) == certificate
    public_text = json.dumps(case.public_instance, sort_keys=True).lower()
    assert all(
        hidden not in public_text
        for hidden in (
            "superincreasing",
            "knapsack",
            "multiplier",
            "hidden_weight",
            "greedy",
        )
    )
    assert "theorem submit" in case.public_instance["challenge_source"]


def test_redesigned_c07_public_recovery_matches_a_small_exhaustive_oracle() -> None:
    hidden, modulus, multiplier, _ = c07._family_material()
    count = 18
    order = tuple(reversed(range(count)))
    planted_hidden = tuple(index % 3 == 1 for index in range(count))
    weights = tuple(multiplier * hidden[index] % modulus for index in order)
    planted_public = tuple(int(planted_hidden[index]) for index in order)
    target = (
        sum(weight * bit for weight, bit in zip(weights, planted_public, strict=True)) % modulus
    )
    problem = {
        "num_items": count,
        "word_bits": 32,
        "modulus": modulus,
        "weights": weights,
        "target": target,
    }
    recovered, _ = _decode_c07_certificate(c07.solve(problem), count=count, word_bits=32)
    satisfying = []
    for mask in range(1 << count):
        if sum(weights[index] for index in range(count) if mask >> index & 1) % modulus == target:
            satisfying.append(tuple((mask >> index) & 1 for index in range(count)))
    assert satisfying == [planted_public] == [recovered]


def test_redesigned_c07_public_recovery_is_seed_robust() -> None:
    for seed_index in range(6):
        case = generated_case("c07", f"redesigned-c07/{seed_index}".encode())
        certificate = tuple(case.private_instance["reference_certificate"])
        assert c07.solve(case.public_instance["problem"]) == certificate
        assert len(certificate) == 24


def test_redesigned_c07_reference_is_kernel_checked() -> None:
    executable = find_lean_executable()
    if executable is None:
        pytest.skip("pinned Lean toolchain is unavailable")
    case = generated_case("c07", b"redesigned-c07-helper-kernel")
    result = verify_lean_solution(
        public_instance=case.public_instance,
        solution_content=str(case.private_instance["reference_solution"]).encode("utf-8"),
        lean_executable=executable,
    )
    assert "does not depend on any axioms" in result.stdout_tail


def _decode_c08_certificate(
    certificate: tuple[int, ...], *, count: int
) -> tuple[tuple[int, ...], tuple[int, ...]]:
    word_count = (count + 31) // 32
    bits = c08._certificate_bits(certificate, count)
    return bits, certificate[word_count:]


def test_redesigned_c08_is_a_unique_dense_binary_syndrome_certificate() -> None:
    case = generated_case("c08", b"redesigned-c08-profile")
    problem = case.public_instance["problem"]
    count = int(problem["num_items"])
    target_weight = int(problem["target_weight"])
    columns = tuple(c08._unpack_chunks(column) for column in problem["columns"])
    syndrome = c08._unpack_chunks(problem["syndrome"])
    certificate = tuple(case.private_instance["reference_certificate"])
    bits, word_weights = _decode_c08_certificate(certificate, count=count)

    assert (count, target_weight, len(problem["syndrome"]), len(certificate)) == (
        511,
        28,
        8,
        32,
    )
    assert len(columns) == count and len(set(columns)) == count
    assert all(0 < column < 1 << 252 for column in columns)
    assert set(bits) == {0, 1} and sum(bits) == target_weight
    assert word_weights == tuple(word.bit_count() for word in certificate[:16])
    assert sum(word_weights) == target_weight
    replay = 0
    for bit, column in zip(bits, columns, strict=True):
        if bit:
            replay ^= column
    assert replay == syndrome

    basis: dict[int, int] = {}
    for column in columns:
        value = column
        while value:
            pivot = value.bit_length() - 1
            if pivot not in basis:
                basis[pivot] = value
                break
            value ^= basis[pivot]
    assert len(basis) == 234
    assert c08.solve(problem) == certificate
    public_text = json.dumps(case.public_instance, sort_keys=True).lower()
    assert all(
        hidden not in public_text
        for hidden in (
            "bch",
            "berlekamp",
            "massey",
            "chien",
            "primitive_polynomial",
            "canonical_position",
            "row_operations",
        )
    )
    assert "theorem submit" in case.public_instance["challenge_source"]


def test_redesigned_c08_matches_a_small_exhaustive_weight_three_oracle() -> None:
    _, public_columns = c08._family_columns()
    planted = (2, 9, 16)
    public_syndrome = public_columns[2] ^ public_columns[9] ^ public_columns[16]
    satisfying = [
        candidate
        for candidate in itertools.combinations(range(18), 3)
        if public_columns[candidate[0]]
        ^ public_columns[candidate[1]]
        ^ public_columns[candidate[2]]
        == public_syndrome
    ]
    raw_syndrome = c08._apply_row_operations(public_syndrome, inverse=True)
    canonical = set(c08._decode_raw_syndrome(raw_syndrome, 3))
    recovered = tuple(
        index for index, position in enumerate(c08._public_order()) if position in canonical
    )
    assert satisfying == [planted] == [recovered]


def test_redesigned_c08_public_recovery_is_seed_robust() -> None:
    for seed_index in range(6):
        case = generated_case("c08", f"redesigned-c08/{seed_index}".encode())
        certificate = tuple(case.private_instance["reference_certificate"])
        assert c08.solve(case.public_instance["problem"]) == certificate
        assert len(certificate) == 32


def test_redesigned_c08_reference_is_kernel_checked() -> None:
    executable = find_lean_executable()
    if executable is None:
        pytest.skip("pinned Lean toolchain is unavailable")
    case = generated_case("c08", b"redesigned-c08-helper-kernel")
    result = verify_lean_solution(
        public_instance=case.public_instance,
        solution_content=str(case.private_instance["reference_solution"]).encode("utf-8"),
        lean_executable=executable,
        timeout_seconds=120,
    )
    assert "does not depend on any axioms" in result.stdout_tail


def test_unknown_parameters_are_rejected_before_builder_dispatch() -> None:
    with pytest.raises(ValueError, match="unknown case parameters"):
        create_task().generator.generate(
            instance_seed=b"seed",
            case_id="c01",
            case_parameters={"max_prmie": 11},
        )


def test_frozen_defaults_generate_without_failure_across_many_seeds() -> None:
    generator = create_task().generator
    for case_id in CASE_IDS:
        for seed_index in range(16):
            case = generator.generate(
                instance_seed=hashlib.sha256(f"t3.1-fuzz/{case_id}/{seed_index}".encode()).digest(),
                case_id=case_id,
                case_parameters={},
            )
            assert (
                solve_public_instance(case.public_instance, case_id)
                == case.private_instance["reference_solution"]
            )


def test_public_protocol_description_is_unified_and_bounded() -> None:
    case = generated_case("c03")
    description = create_task().protocol.public_protocol_description(generated_case=case)
    assert description["initial_event_kinds"] == [PROOF_EVENT_KIND]
    assert description["public_parameters"]["toolchain"] == LEAN_TOOLCHAIN
    assert description["public_parameters"]["max_solution_bytes"] == 262_144
    assert description["public_parameters"]["one_shot"] is True
    assert len(case.public_instance["public_features"]) <= 2


def test_protocol_rejects_wrong_event_payload_and_instance_digest(tmp_path: Path) -> None:
    case = generated_case()
    protocol = MachineCheckedMathematicsProtocol()
    context = FakeContext()
    state = protocol.initialize(generated_case=case, context=context)

    wrong_kind = protocol.handle_event(
        state=state,
        event=ParticipantEvent(0, "lean.answer", {}, ()),
        generated_case=case,
        context=context,
    )
    extra_payload = protocol.handle_event(
        state=state,
        event=ParticipantEvent(
            0,
            PROOF_EVENT_KIND,
            {"instance_sha256": case.public_instance["instance_sha256"], "extra": 1},
            ("sha256:" + "0" * 64,),
        ),
        generated_case=case,
        context=context,
    )
    wrong_digest = protocol.handle_event(
        state=state,
        event=ParticipantEvent(
            0,
            PROOF_EVENT_KIND,
            {"instance_sha256": "0" * 64},
            ("sha256:" + "0" * 64,),
        ),
        generated_case=case,
        context=context,
    )
    assert wrong_kind.reason_code == ErrorCode.INVALID_EVENT_KIND
    assert extra_payload.reason_code == ErrorCode.INVALID_PAYLOAD
    assert wrong_digest.reason_code == LeanReason.INSTANCE_MISMATCH


def test_protocol_accepts_a_checked_artifact_without_private_reference(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    case = generated_case()
    source = solve_public_instance(case.public_instance, case.case_id).encode()
    artifact_path = tmp_path / "artifact"
    artifact_path.write_bytes(source)
    artifact_id = "sha256:" + hashlib.sha256(source).hexdigest()
    context = FakeContext({artifact_id: artifact_path})
    calls = 0

    def fake_verify(**kwargs: Any) -> lean_task.LeanCheckResult:
        nonlocal calls
        calls += 1
        assert kwargs["public_instance"] is case.public_instance
        assert kwargs["solution_content"] == source
        return lean_task.LeanCheckResult("kernel_and_axiom_audit", "empty")

    monkeypatch.setattr(lean_task, "verify_lean_solution", fake_verify)
    protocol = MachineCheckedMathematicsProtocol()
    state = protocol.initialize(generated_case=case, context=context)
    transition = protocol.handle_event(
        state=state,
        event=ParticipantEvent(
            0,
            PROOF_EVENT_KIND,
            {"instance_sha256": case.public_instance["instance_sha256"]},
            (artifact_id,),
        ),
        generated_case=case,
        context=context,
    )
    assert transition.terminal_status == TerminalStatus.ACCEPT
    assert transition.reason_code == ErrorCode.PROTOCOL_ACCEPT
    assert transition.milestones == {"proof_submitted": 1, "kernel_checked": 1}
    assert calls == 1


@pytest.mark.parametrize(
    "source",
    (
        "import Challenge\nimport Init\nnamespace AMBenchSolution\nend AMBenchSolution\n",
        "import Challenge\nimport/-hidden comment-/Init\n"
        "namespace AMBenchSolution\nend AMBenchSolution\n",
        "import Challenge\naxiom bad : False\n",
        "import Challenge\ntheorem x : True := by sorry\n",
        "import Challenge\n#eval 1 + 1\n",
        "import Challenge\n#guard true\n",
        'import Challenge\ninitialize IO.println "unexpected side effect"\n',
        'import Challenge\ndef write := IO.FS.writeFile "Verify.lean" ""\n',
        "import Challenge\n@[implemented_by bad] theorem proof : Challenge.Target := bad\n",
        "\ufeffimport Challenge\n",
        "import Challenge\r\n",
    ),
)
def test_static_source_envelope_rejects_forbidden_inputs(source: str) -> None:
    case = generated_case()
    executable = find_lean_executable()
    if executable is None:
        pytest.skip("pinned Lean toolchain is unavailable")
    with pytest.raises(lean_task._ProofRejected) as rejected:
        verify_lean_solution(
            public_instance=case.public_instance,
            solution_content=source.encode("utf-8"),
            lean_executable=executable,
        )
    assert rejected.value.reason_code in {
        LeanReason.ARTIFACT_MALFORMED,
        LeanReason.SOURCE_FORBIDDEN,
    }


def test_only_the_arthur_wrapper_can_supply_the_axiom_audit(monkeypatch: Any) -> None:
    case = generated_case()

    def fake_run(
        executable: Path,
        arguments: list[str],
        *,
        cwd: Path,
        timeout_seconds: float,
    ) -> subprocess.CompletedProcess[str]:
        del executable, cwd, timeout_seconds
        if arguments == ["--version"]:
            return subprocess.CompletedProcess(arguments, 0, "Lean (version 4.19.0)", "")
        forged = (
            "'AMBenchSolution.proof' does not depend on any axioms"
            if arguments[-1] == "Solution.lean"
            else ""
        )
        return subprocess.CompletedProcess(arguments, 0, forged, "")

    monkeypatch.setattr(lean_task, "_run_checked", fake_run)
    with pytest.raises(lean_task._ProofRejected) as rejected:
        lean_task.verify_lean_solution(
            public_instance=case.public_instance,
            solution_content=solve_public_instance(case.public_instance, case.case_id).encode(),
            lean_executable=Path("lean"),
        )
    assert rejected.value.reason_code == LeanReason.AXIOM_AUDIT_FAILED


def test_arthur_wrapper_tampering_is_rejected(monkeypatch: Any) -> None:
    case = generated_case()

    def fake_run(
        executable: Path,
        arguments: list[str],
        *,
        cwd: Path,
        timeout_seconds: float,
    ) -> subprocess.CompletedProcess[str]:
        del executable, timeout_seconds
        if arguments == ["--version"]:
            return subprocess.CompletedProcess(arguments, 0, "Lean (version 4.19.0)", "")
        if arguments[-1] == "Verify.lean":
            (cwd / "Verify.lean").write_text("import Challenge\n", encoding="utf-8")
            output = "'AMBenchSolution.proof' does not depend on any axioms"
            return subprocess.CompletedProcess(arguments, 0, output, "")
        return subprocess.CompletedProcess(arguments, 0, "", "")

    monkeypatch.setattr(lean_task, "_run_checked", fake_run)
    with pytest.raises(lean_task._ProofRejected) as rejected:
        lean_task.verify_lean_solution(
            public_instance=case.public_instance,
            solution_content=solve_public_instance(case.public_instance, case.case_id).encode(),
            lean_executable=Path("lean"),
        )
    assert rejected.value.reason_code == LeanReason.SOURCE_FORBIDDEN


@pytest.mark.parametrize("case_id", CASE_IDS)
def test_pinned_lean_kernel_accepts_every_reference(case_id: str) -> None:
    executable = find_lean_executable()
    if executable is None:
        pytest.skip("pinned Lean toolchain is unavailable")
    case = generated_case(case_id, f"kernel/{case_id}".encode())
    result = verify_lean_solution(
        public_instance=case.public_instance,
        solution_content=str(case.private_instance["reference_solution"]).encode(),
        lean_executable=executable,
    )
    assert result.elapsed_stage == "kernel_and_axiom_audit"
    assert "does not depend on any axioms" in result.stdout_tail


def test_kernel_rejects_an_invalid_proof() -> None:
    executable = find_lean_executable()
    if executable is None:
        pytest.skip("pinned Lean toolchain is unavailable")
    case = generated_case("c01")
    source = """import Challenge

namespace AMBenchSolution
theorem proof : Challenge.Target := by
  exact False.elim (by contradiction)
end AMBenchSolution
"""
    with pytest.raises(lean_task._ProofRejected) as rejected:
        verify_lean_solution(
            public_instance=case.public_instance,
            solution_content=source.encode(),
            lean_executable=executable,
        )
    assert rejected.value.reason_code == LeanReason.ELABORATION_FAILED


def test_case_yaml_defaults_equal_python_defaults() -> None:
    import yaml

    root = Path("tasks/tier3_applied/machine_checked_mathematics/cases")
    decoded = {
        path.stem: yaml.safe_load(path.read_text(encoding="utf-8"))["parameters"]
        for path in sorted(root.glob("c*.yaml"))
    }
    assert decoded == {case_id: dict(parameters) for case_id, parameters in CASE_PARAMETERS.items()}
