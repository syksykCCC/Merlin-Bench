from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

import yaml

from aipbench.core.models import GeneratedCase, ParticipantEvent, SessionMode, TerminalStatus
from aipbench.tasks.new_weighted_partial_maxsat import (
    ASSIGNMENT_EVENT_KIND,
    CASE_IDS,
    TASK_ID,
    TASK_VERSION,
    create_task,
    evaluate_assignment,
)

ROOT = Path(__file__).resolve().parents[2]
SEED = bytes.fromhex("34" * 32)


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


def generate(seed: bytes = SEED, case_id: str = "c01") -> GeneratedCase:
    task = create_task()
    return task.generator.generate(
        instance_seed=seed,
        case_id=case_id,
        case_parameters=task.case_parameters[case_id],
    )


def submit(generated: GeneratedCase, assignment: list[int]) -> Any:
    task = create_task()
    context = FakeContext()
    state = task.protocol.initialize(generated_case=generated, context=context)
    return task.protocol.handle_event(
        state=state,
        event=ParticipantEvent(
            sequence=0,
            kind=ASSIGNMENT_EVENT_KIND,
            payload={"assignment": assignment},
            artifact_refs=(),
        ),
        generated_case=generated,
        context=context,
    )


def recover_from_public_hard_clauses(instance: dict[str, Any]) -> list[int]:
    values: list[int | None] = [None] * instance["num_variables"]
    units = [clause for clause in instance["hard_clauses"] if len(clause["literals"]) == 1]
    assert len(units) == 1
    unit = units[0]["literals"][0]
    values[abs(unit) - 1] = int(unit > 0)

    progress = True
    while progress:
        progress = False
        for clause in instance["hard_clauses"]:
            unknown: list[int] = []
            satisfied = False
            for literal in clause["literals"]:
                value = values[abs(literal) - 1]
                if value is None:
                    unknown.append(literal)
                elif bool(value) == (literal > 0):
                    satisfied = True
                    break
            if satisfied:
                continue
            assert unknown
            if len(unknown) == 1:
                literal = unknown[0]
                index = abs(literal) - 1
                forced = int(literal > 0)
                if values[index] is None:
                    values[index] = forced
                    progress = True
                else:
                    assert values[index] == forced
    assert all(value is not None for value in values)
    return [int(value) for value in values]


def test_manifest_yaml_registry_and_case_profiles_include_c01_c06() -> None:
    task = create_task()
    assert task.manifest["id"] == TASK_ID
    assert task.manifest["version"] == TASK_VERSION
    assert task.manifest["resources"] == {
        "wall_time_seconds": 600,
        "cpu_cores": 4,
        "memory_mb": 4096,
        "disk_mb": 4096,
        "max_artifact_bytes": 8_388_608,
        "max_events": 1,
    }
    assert CASE_IDS == ("c01", "c02", "c03", "c04", "c05", "c06")
    assert tuple(task.case_parameters) == ("c01", "c02", "c03", "c04", "c05", "c06")
    for case_id in CASE_IDS:
        case_yaml = yaml.safe_load(
            (ROOT / f"tasks/tier1_np/new_weighted_partial_maxsat/cases/{case_id}.yaml").read_text(
                encoding="utf-8"
            )
        )
        assert case_yaml["parameters"] == task.case_parameters[case_id]


def test_c01_is_deterministic_domain_separated_and_structurally_complete() -> None:
    first = generate()
    second = generate()
    different = generate(bytes.fromhex("35" * 32))
    assert first == second
    assert first.public_instance != different.public_instance
    assert first.task_id == TASK_ID
    assert first.task_version == TASK_VERSION

    public = first.public_instance
    assert public["num_variables"] == 160
    assert len(public["hard_clauses"]) == 319
    assert len(public["soft_clauses"]) == 240
    assert sorted(len(clause["literals"]) for clause in public["hard_clauses"]) == [
        1,
        *([2] * 318),
    ]
    assert {len(clause["literals"]) for clause in public["soft_clauses"]} == {2, 3}
    clause_ids = [
        clause["clause_id"] for clause in [*public["hard_clauses"], *public["soft_clauses"]]
    ]
    assert len(clause_ids) == len(set(clause_ids))


def test_public_unit_propagation_recovers_exact_accepted_optimum() -> None:
    generated = generate()
    public = dict(generated.public_instance)
    recovered = recover_from_public_hard_clauses(public)
    private_reference = list(generated.private_instance["reference_assignment"])
    assert recovered == private_reference
    assert 0 < sum(recovered) < len(recovered)
    hard_satisfied, cost = evaluate_assignment(public, recovered)
    assert hard_satisfied
    assert cost == public["threshold"] == generated.private_instance["reference_cost"]
    assert submit(generated, recovered).terminal_status == TerminalStatus.ACCEPT


def test_hard_assignment_is_unique_and_private_reference_is_not_an_acceptance_oracle() -> None:
    generated = generate()
    reference = list(generated.private_instance["reference_assignment"])
    for index in range(len(reference)):
        changed = reference.copy()
        changed[index] ^= 1
        hard_satisfied, _ = evaluate_assignment(generated.public_instance, changed)
        assert not hard_satisfied

    mutated = replace(
        generated,
        private_instance={"reference_assignment": [0] * len(reference), "reference_cost": 0},
    )
    assert submit(mutated, reference).terminal_status == TerminalStatus.ACCEPT


def test_c02_scaled_profile_public_reference_and_formal_acceptance() -> None:
    from aipbench.tasks.new_maxsat_cases.reference import solve_public_implication_closure

    generated = generate(case_id="c02")
    public = generated.public_instance
    assert public["num_variables"] == 12_000
    assert len(public["hard_clauses"]) == 118_200
    assert len(public["soft_clauses"]) == 12_000
    assert all(len(clause["literals"]) == 2 for clause in public["hard_clauses"])
    assert all(len(clause["literals"]) == 1 for clause in public["soft_clauses"])
    assignment, optimum = solve_public_implication_closure(public)
    hard_satisfied, cost = evaluate_assignment(public, assignment)
    assert hard_satisfied
    assert optimum == cost == public["threshold"]
    assert generated.private_instance["reference_cost"] == optimum
    assert submit(generated, assignment).terminal_status == TerminalStatus.ACCEPT


def test_c02_small_public_reference_matches_exhaustive_optimum() -> None:
    from aipbench.tasks.new_maxsat_cases.reference import solve_public_implication_closure

    task = create_task()
    parameters = {
        **task.case_parameters["c02"],
        "num_layers": 3,
        "layer_width": 4,
        "adjacent_degree": 2,
        "skip_degree": 1,
    }
    generated = task.generator.generate(
        instance_seed=b"c02-exhaustive-oracle",
        case_id="c02",
        case_parameters=parameters,
    )
    public = generated.public_instance
    assignment, optimum = solve_public_implication_closure(public)
    brute_force_costs = [
        cost
        for mask in range(1 << public["num_variables"])
        for hard_satisfied, cost in [
            evaluate_assignment(
                public,
                [(mask >> index) & 1 for index in range(public["num_variables"])],
            )
        ]
        if hard_satisfied
    ]
    assert optimum == min(brute_force_costs)
    assert evaluate_assignment(public, assignment) == (True, optimum)


def test_c03_bounded_window_profile_reference_and_formal_acceptance() -> None:
    generated = generate(seed=b"c03-profile-test", case_id="c03")
    public = generated.public_instance
    assert public["num_variables"] == 2_400
    assert len(public["hard_clauses"]) == 7_197
    assert len(public["soft_clauses"]) == 9_600
    reference = list(generated.private_instance["reference_assignment"])
    assert 0 < sum(reference) < len(reference)
    hard_satisfied, cost = evaluate_assignment(public, reference)
    assert hard_satisfied
    assert cost == public["threshold"] == generated.private_instance["reference_cost"]
    assert submit(generated, reference).terminal_status == TerminalStatus.ACCEPT


def test_c03_reference_dp_matches_exhaustive_optimum_on_small_instance() -> None:
    task = create_task()
    parameters = {
        **task.case_parameters["c03"],
        "num_variables": 12,
        "window_width": 5,
        "hard_clauses_per_step": 2,
        "soft_clauses_per_step": 2,
    }
    generated = task.generator.generate(
        instance_seed=b"c03-exhaustive-oracle",
        case_id="c03",
        case_parameters=parameters,
    )
    public = generated.public_instance
    feasible_costs = [
        cost
        for mask in range(1 << public["num_variables"])
        for hard_satisfied, cost in [
            evaluate_assignment(
                public,
                [(mask >> index) & 1 for index in range(public["num_variables"])],
            )
        ]
        if hard_satisfied
    ]
    assert generated.private_instance["reference_cost"] == min(feasible_costs)


def test_c04_gadget_truth_table_is_exact_implication_compilation() -> None:
    def clause(literals: tuple[int, ...], values: tuple[bool, bool, bool, bool]) -> bool:
        return any(values[abs(literal) - 1] == (literal > 0) for literal in literals)

    clauses = ((-1, -4, 3), (1, -3), (4, -3), (-3, 2))
    for antecedent in (False, True):
        for consequent in (False, True):
            feasible_auxiliaries = [
                auxiliary
                for auxiliary in (False, True)
                if all(clause(item, (antecedent, consequent, auxiliary, True)) for item in clauses)
            ]
            assert feasible_auxiliaries == ([antecedent] if (not antecedent or consequent) else [])


def test_c04_scaled_gadgets_public_reference_and_formal_acceptance() -> None:
    from aipbench.tasks.new_maxsat_cases.reference import solve_public_gadget_closure

    generated = generate(seed=b"c04-profile-test", case_id="c04")
    public = generated.public_instance
    assert public["num_variables"] == 36_289
    assert len(public["hard_clauses"]) == 120_577
    assert len(public["soft_clauses"]) == 6_144
    assert sum(len(clause["literals"]) == 1 for clause in public["hard_clauses"]) == 1
    assert {len(clause["literals"]) for clause in public["hard_clauses"]} == {1, 2, 3}
    assignment, optimum = solve_public_gadget_closure(public)
    assert evaluate_assignment(public, assignment) == (True, optimum)
    assert optimum == public["threshold"] == generated.private_instance["reference_cost"]
    assert submit(generated, assignment).terminal_status == TerminalStatus.ACCEPT


def test_c05_parity_reference_matches_small_exhaustive_oracle() -> None:
    from aipbench.tasks.new_maxsat_cases.reference import solve_parity_components

    factors = [
        ((1, 2, 3), False, True, 7),
        ((2, 4), True, False, 11),
        ((1, 4, 5), True, True, 5),
        ((3, 5), False, False, 13),
    ]
    assignment, optimum = solve_parity_components(num_free_variables=5, factors=factors)

    def cost(values: tuple[bool, ...]) -> int:
        return sum(
            weight
            for variables, rhs, prefer_true, weight in factors
            if (rhs ^ (sum(values[variable - 1] for variable in variables) % 2 == 1)) != prefer_true
        )

    exhaustive = [
        cost(tuple(bool((mask >> index) & 1) for index in range(5))) for mask in range(1 << 5)
    ]
    assert optimum == min(exhaustive) == cost(assignment)


def test_c05_scaled_public_parity_reference_and_formal_acceptance() -> None:
    from aipbench.tasks.new_maxsat_cases.reference import solve_public_parity_components

    generated = generate(seed=b"c05-profile-test", case_id="c05")
    public = generated.public_instance
    assert public["num_variables"] == 33_280
    assert len(public["hard_clauses"]) == 112_640
    assert len(public["soft_clauses"]) == 14_080
    assert all(len(clause["literals"]) == 3 for clause in public["hard_clauses"])
    assert all(len(clause["literals"]) == 1 for clause in public["soft_clauses"])
    assignment, optimum = solve_public_parity_components(public)
    assert evaluate_assignment(public, assignment) == (True, optimum)
    assert optimum == public["threshold"] == generated.private_instance["reference_cost"]
    assert submit(generated, assignment).terminal_status == TerminalStatus.ACCEPT


def test_c06_transfer_reference_matches_small_exhaustive_oracle() -> None:
    from aipbench.tasks.new_maxsat_cases.reference import solve_layered_ising

    within = [
        [(0, 1, False, 3), (0, 2, True, 5), (1, 2, False, 7)],
        [(0, 1, True, 11), (0, 2, False, 13), (1, 2, True, 17)],
        [(0, 1, False, 19), (0, 2, False, 23), (1, 2, True, 29)],
    ]
    between = [
        [(0, 1, False, 31), (1, 2, True, 37), (2, 0, False, 41)],
        [(0, 2, True, 43), (1, 0, False, 47), (2, 1, True, 53)],
    ]
    assignment, optimum = solve_layered_ising(
        layer_width=3, within_layers=within, between_layers=between
    )

    def energy(values: tuple[bool, ...]) -> int:
        result = 0
        for layer, factors in enumerate(within):
            for left, right, preferred, weight in factors:
                if values[3 * layer + left] ^ values[3 * layer + right] != preferred:
                    result += weight
        for layer, factors in enumerate(between):
            for left, right, preferred, weight in factors:
                if values[3 * layer + left] ^ values[3 * (layer + 1) + right] != preferred:
                    result += weight
        return result

    exhaustive = [
        energy(tuple(bool((mask >> index) & 1) for index in range(9))) for mask in range(1 << 9)
    ]
    assert optimum == min(exhaustive) == energy(assignment)


def test_c06_scaled_public_layer_recovery_and_formal_acceptance() -> None:
    from aipbench.tasks.new_maxsat_cases.reference import solve_public_layered_ising

    generated = generate(seed=b"c06-profile-test", case_id="c06")
    public = generated.public_instance
    assert public["num_variables"] == 3_840
    assert public["hard_clauses"] == []
    assert len(public["soft_clauses"]) == 65_248
    assert all(len(clause["literals"]) == 2 for clause in public["soft_clauses"])
    assignment, optimum = solve_public_layered_ising(public)
    assert evaluate_assignment(public, assignment) == (True, optimum)
    assert optimum == public["threshold"] == generated.private_instance["reference_cost"]
    assert submit(generated, assignment).terminal_status == TerminalStatus.ACCEPT


def test_participant_spec_has_only_relation_and_wire_contract() -> None:
    text = (ROOT / "tasks/tier1_np/new_weighted_partial_maxsat/TASK_SPECIFICATION.md").read_text(
        encoding="utf-8"
    )
    lowered = text.lower()
    assert TASK_ID in text
    assert TASK_VERSION in text
    assert "600 seconds" in text
    for forbidden in (
        "c01",
        "c02",
        "c03",
        "c04",
        "c05",
        "c06",
        "propagation",
        "chain",
        "anchor",
        "equality",
        "disequality",
        "generator",
        "family",
        "solver",
        "worked solution",
        "160 variables",
        "240 soft",
        "319 hard",
        "implication",
        "closure",
        "12000",
        "118200",
        "bounded-window",
        "treewidth",
        "2400",
        "7197",
        "9600",
        "gadget",
        "maximum-weight",
        "36289",
        "120577",
        "6144",
        "parity",
        "tseitin",
        "33280",
        "112640",
        "14080",
        "ising",
        "layered",
        "transfer",
        "3840",
        "65248",
    ):
        assert forbidden not in lowered
