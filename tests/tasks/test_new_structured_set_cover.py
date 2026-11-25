from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

import yaml

from aipbench.core.models import GeneratedCase, ParticipantEvent, SessionMode, TerminalStatus
from aipbench.tasks.new_set_cover_cases.c02 import minimum_weight_cycle_vertex_cover
from aipbench.tasks.new_set_cover_cases.c04 import solve_weighted_bag_path
from aipbench.tasks.new_set_cover_cases.c06 import solve_weighted_bag_tree
from aipbench.tasks.new_structured_set_cover import (
    CASE_IDS,
    SELECTION_EVENT_KIND,
    TASK_ID,
    TASK_VERSION,
    create_task,
    evaluate_selection,
    solve_public_c01,
    solve_public_c02,
    solve_public_c03,
    solve_public_c04,
    solve_public_c05,
    solve_public_c06,
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
    seed: bytes = b"new-set-cover-c01-test",
    *,
    case_id: str = "c01",
    parameters: dict[str, Any] | None = None,
) -> GeneratedCase:
    task = create_task()
    return task.generator.generate(
        instance_seed=seed,
        case_id=case_id,
        case_parameters=parameters or task.case_parameters[case_id],
    )


def submit(generated: GeneratedCase, set_ids: list[int]) -> Any:
    task = create_task()
    context = FakeContext()
    state = task.protocol.initialize(generated_case=generated, context=context)
    return task.protocol.handle_event(
        state=state,
        event=ParticipantEvent(0, SELECTION_EVENT_KIND, {"set_ids": set_ids}),
        generated_case=generated,
        context=context,
    )


def incidence_components(public: dict[str, Any]) -> list[tuple[set[int], list[dict[str, Any]]]]:
    by_element: dict[int, list[dict[str, Any]]] = {}
    for candidate in public["sets"]:
        for element in candidate["elements"]:
            by_element.setdefault(element, []).append(candidate)
    unseen = set(range(1, public["num_elements"] + 1))
    components = []
    while unseen:
        elements = {unseen.pop()}
        sets_by_id: dict[int, dict[str, Any]] = {}
        frontier = list(elements)
        while frontier:
            element = frontier.pop()
            for candidate in by_element[element]:
                sets_by_id[candidate["set_id"]] = candidate
                for neighbor in candidate["elements"]:
                    if neighbor in unseen:
                        unseen.remove(neighbor)
                        elements.add(neighbor)
                        frontier.append(neighbor)
        components.append((elements, list(sets_by_id.values())))
    return components


def test_manifest_yaml_registry_and_resources() -> None:
    task = create_task()
    assert task.manifest["id"] == TASK_ID
    assert task.manifest["version"] == TASK_VERSION
    assert task.manifest["resources"]["wall_time_seconds"] == 600
    assert task.manifest["resources"]["cpu_cores"] == 4
    assert task.manifest["resources"]["memory_mb"] == 4096
    assert CASE_IDS == ("c01", "c02", "c03", "c04", "c05", "c06")
    for case_id in CASE_IDS:
        case_yaml = yaml.safe_load(
            (ROOT / f"tasks/tier1_np/new_structured_set_cover/cases/{case_id}.yaml").read_text(
                encoding="utf-8"
            )
        )
        assert case_yaml["parameters"] == task.case_parameters[case_id]


def test_c01_is_deterministic_scaled_and_has_exact_group_lower_bounds() -> None:
    generated = generate()
    assert generated == generate()
    assert generated.public_instance != generate(b"new-set-cover-c01-other").public_instance
    public = generated.public_instance
    assert public["num_elements"] == 144
    assert len(public["sets"]) == 216
    components = incidence_components(public)
    assert len(components) == 24
    selected: list[int] = []
    optimum = 0
    for elements, candidates in components:
        assert len(elements) == 6
        assert len(candidates) == 9
        full = [candidate for candidate in candidates if set(candidate["elements"]) == elements]
        assert len(full) == 1
        assert all(
            candidate["weight"] > full[0]["weight"]
            for candidate in candidates
            if candidate != full[0]
        )
        selected.append(full[0]["set_id"])
        optimum += full[0]["weight"]
    assert optimum == public["budget"]
    evaluation = evaluate_selection(public, selected)
    assert evaluation.covers_universe and evaluation.total_weight == optimum
    assert submit(generated, selected).terminal_status == TerminalStatus.ACCEPT
    assert set(solve_public_c01(public)) == set(selected)


def test_c04_exact_dp_profile_and_public_reference() -> None:
    generated = generate(b"new-set-cover-c04-test", case_id="c04")
    assert generated == generate(b"new-set-cover-c04-test", case_id="c04")
    public = generated.public_instance
    assert public["num_elements"] == 3_968
    assert len(public["sets"]) == 1_124
    assert sum(candidate["weight"] > public["budget"] for candidate in public["sets"]) == 124
    assert not any(len(candidate["elements"]) == 1 for candidate in public["sets"])
    selected = list(solve_public_c04(public))
    evaluation = evaluate_selection(public, selected)
    assert evaluation.covers_universe
    assert evaluation.total_weight == public["budget"]
    assert submit(generated, selected).terminal_status == TerminalStatus.ACCEPT


def test_c04_small_dp_matches_exhaustive_hitting_set() -> None:
    weights = (5, 9, 4, 8, 3, 7, 6, 2)
    bags = ((0, 1, 2, 3), (2, 3, 4, 5), (4, 5, 6, 7))
    clauses = (
        ((0, 1), (2, 3), (0, 2, 3)),
        ((2, 4), (3, 5), (2, 3, 4)),
        ((4, 6), (5, 7), (4, 5, 7)),
    )
    selected = solve_weighted_bag_path(bags=bags, clauses_by_bag=clauses, weights=weights)
    exact = min(
        sum(weights[index] for index in range(len(weights)) if (mask >> index) & 1)
        for mask in range(1 << len(weights))
        if all(
            any((mask >> variable) & 1 for variable in clause)
            for group in clauses
            for clause in group
        )
    )
    assert sum(weights[index] for index in selected) == exact


def test_c05_width18_profile_and_public_reference() -> None:
    generated = generate(b"new-set-cover-c05-test", case_id="c05")
    public = generated.public_instance
    assert public["num_elements"] == 3_968
    assert len(public["sets"]) == 1_249
    assert 17_850 <= sum(len(candidate["elements"]) for candidate in public["sets"]) <= 17_950
    assert sum(candidate["weight"] > public["budget"] for candidate in public["sets"]) == 124
    assert not any(len(candidate["elements"]) == 1 for candidate in public["sets"])
    selected = list(solve_public_c05(public))
    evaluation = evaluate_selection(public, selected)
    assert evaluation.covers_universe
    assert evaluation.total_weight == public["budget"]
    assert submit(generated, selected).terminal_status == TerminalStatus.ACCEPT


def test_c06_tree_profile_and_public_reference() -> None:
    generated = generate(b"new-set-cover-c06-test", case_id="c06")
    public = generated.public_instance
    assert public["num_elements"] == 3_706
    assert len(public["sets"]) == 1_205
    assert sum(len(candidate["elements"]) for candidate in public["sets"]) > 16_800
    assert sum(candidate["weight"] > public["budget"] for candidate in public["sets"]) == 109
    assert not any(len(candidate["elements"]) == 1 for candidate in public["sets"])
    selected = list(solve_public_c06(public))
    evaluation = evaluate_selection(public, selected)
    assert evaluation.covers_universe
    assert evaluation.total_weight == public["budget"]
    assert submit(generated, selected).terminal_status == TerminalStatus.ACCEPT


def test_c06_small_tree_dp_matches_exhaustive_hitting_set() -> None:
    weights = (5, 9, 4, 8, 3, 7, 6, 2)
    bags = ((0, 1, 2, 3), (0, 1, 4, 5), (2, 3, 6, 7))
    clauses = (
        ((0, 1), (2, 3), (0, 2, 3)),
        ((0, 4), (1, 5), (0, 1, 4)),
        ((2, 6), (3, 7), (2, 3, 6)),
    )
    selected = solve_weighted_bag_tree(
        bags=bags,
        clauses_by_bag=clauses,
        parents=(-1, 0, 0),
        weights=weights,
    )
    exact = min(
        sum(weights[index] for index in range(len(weights)) if (mask >> index) & 1)
        for mask in range(1 << len(weights))
        if all(
            any((mask >> variable) & 1 for variable in clause)
            for group in clauses
            for clause in group
        )
    )
    assert sum(weights[index] for index in selected) == exact


def test_private_reference_is_valid_but_not_acceptance_oracle() -> None:
    generated = generate()
    reference = list(generated.private_instance["reference_set_ids"])
    assert submit(generated, reference).terminal_status == TerminalStatus.ACCEPT
    mutated = replace(
        generated,
        private_instance={"reference_set_ids": [0], "reference_weight": 1},
    )
    assert submit(mutated, reference).terminal_status == TerminalStatus.ACCEPT


def test_local_group_optimum_matches_exhaustive_selection() -> None:
    public = generate().public_instance
    elements, candidates = incidence_components(public)[0]
    feasible_weights = []
    for mask in range(1 << len(candidates)):
        covered: set[int] = set()
        weight = 0
        for index, candidate in enumerate(candidates):
            if (mask >> index) & 1:
                covered.update(candidate["elements"])
                weight += candidate["weight"]
        if covered == elements:
            feasible_weights.append(weight)
    full_weight = next(
        candidate["weight"] for candidate in candidates if set(candidate["elements"]) == elements
    )
    assert min(feasible_weights) == full_weight
    assert feasible_weights.count(full_weight) == 1


def test_c02_is_deterministic_connected_overlapping_and_exact() -> None:
    generated = generate(b"new-set-cover-c02-test", case_id="c02")
    assert generated == generate(b"new-set-cover-c02-test", case_id="c02")
    assert (
        generated.public_instance
        != generate(b"new-set-cover-c02-other", case_id="c02").public_instance
    )
    public = generated.public_instance
    assert public["num_elements"] == 3_072
    assert len(public["sets"]) == 3_072
    assert all(len(candidate["elements"]) == 2 for candidate in public["sets"])
    assert len(incidence_components(public)) == 1
    degree: dict[int, int] = {}
    for candidate in public["sets"]:
        for element in candidate["elements"]:
            degree[element] = degree.get(element, 0) + 1
    assert set(degree.values()) == {2}
    reference = list(generated.private_instance["reference_set_ids"])
    solved = list(solve_public_c02(public))
    assert evaluate_selection(public, solved).total_weight == public["budget"]
    assert submit(generated, solved).terminal_status == TerminalStatus.ACCEPT
    assert submit(generated, reference).terminal_status == TerminalStatus.ACCEPT


def test_c02_small_oracle_matches_exhaustive_search() -> None:
    weights = (8, 3, 9, 4, 6, 2, 7, 5, 11)
    selected = minimum_weight_cycle_vertex_cover(weights)
    exact = min(
        sum(weights[index] for index in range(len(weights)) if (mask >> index) & 1)
        for mask in range(1 << len(weights))
        if all(
            ((mask >> edge) & 1) or ((mask >> ((edge + 1) % len(weights))) & 1)
            for edge in range(len(weights))
        )
    )
    assert sum(weights[index] for index in selected) == exact


def test_c03_hidden_width_profile_and_public_reference() -> None:
    generated = generate(b"new-set-cover-c03-test", case_id="c03")
    assert generated == generate(b"new-set-cover-c03-test", case_id="c03")
    assert (
        generated.public_instance
        != generate(b"new-set-cover-c03-other", case_id="c03").public_instance
    )
    public = generated.public_instance
    assert public["num_elements"] == 3_899
    assert len(public["sets"]) == 1_091
    assert sum(len(candidate["elements"]) for candidate in public["sets"]) == 14_339
    selected = list(solve_public_c03(public))
    evaluation = evaluate_selection(public, selected)
    assert len(selected) == 587
    assert evaluation.covers_universe
    assert evaluation.total_weight == public["budget"]
    assert submit(generated, selected).terminal_status == TerminalStatus.ACCEPT


def test_c03_small_oracle_enumerates_the_exact_threshold() -> None:
    task = create_task()
    parameters = {
        **task.case_parameters["c03"],
        "num_blocks": 3,
        "block_width": 6,
        "local_clauses": 4,
        "boundary_clauses": 4,
    }
    generated = generate(b"new-set-cover-c03-oracle", case_id="c03", parameters=parameters)
    public = generated.public_instance
    weights: dict[int, int] = {}
    by_element: dict[int, list[int]] = {}
    for candidate in public["sets"]:
        weights[candidate["set_id"]] = candidate["weight"]
        for element in candidate["elements"]:
            by_element.setdefault(element, []).append(candidate["set_id"])
    mandatory = sorted(ids[0] for ids in by_element.values() if len(ids) == 1)
    pairs = sorted(
        tuple(sorted(ids))
        for ids in by_element.values()
        if len(ids) == 2 and weights[ids[0]] == weights[ids[1]]
    )
    assert len(pairs) == 18
    optimum = None
    for mask in range(1 << len(pairs)):
        selected = [pair[(mask >> index) & 1] for index, pair in enumerate(pairs)] + mandatory
        evaluation = evaluate_selection(public, selected)
        if evaluation.covers_universe:
            optimum = (
                evaluation.total_weight
                if optimum is None
                else min(optimum, evaluation.total_weight)
            )
    assert optimum == public["budget"]


def test_participant_spec_has_no_construction_or_size_leaks() -> None:
    text = (
        (ROOT / "tasks/tier1_np/new_structured_set_cover/TASK_SPECIFICATION.md")
        .read_text(encoding="utf-8")
        .lower()
    )
    for forbidden in (
        "c01",
        "c02",
        "c03",
        "c04",
        "c05",
        "c06",
        "group",
        "component",
        "decoy",
        "cycle",
        "dynamic program",
        "width",
        "width-12",
        "marker",
        "boolean",
        "hitting",
        "bag",
        "separator",
        "width-18",
        "tree",
        "cactus",
        "family",
        "generator",
        "algorithm",
        "worked",
        "144",
        "216",
        "24 groups",
    ):
        assert forbidden not in text
