from __future__ import annotations

from collections import deque
from dataclasses import replace
from itertools import combinations
from pathlib import Path
from typing import Any

import yaml

from aipbench.core.models import ParticipantEvent, SessionMode, TerminalStatus
from aipbench.tasks.new_rooted_group_steiner_tree import (
    CASE_IDS,
    EDGE_SET_EVENT_KIND,
    TASK_ID,
    TASK_VERSION,
    VIRTUAL_AGENTS,
    create_task,
    evaluate_edge_set,
    solve_public,
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
    seed: bytes = b"new-rooted-group-steiner-c01-test",
    *,
    parameters: dict[str, Any] | None = None,
    case_id: str = "c01",
) -> Any:
    task = create_task()
    return task.generator.generate(
        instance_seed=seed,
        case_id=case_id,
        case_parameters=parameters or task.case_parameters[case_id],
    )


def submit(generated: Any, edge_ids: list[int]) -> Any:
    task = create_task()
    context = FakeContext()
    state = task.protocol.initialize(generated_case=generated, context=context)
    return task.protocol.handle_event(
        state=state,
        event=ParticipantEvent(0, EDGE_SET_EVENT_KIND, {"edge_ids": edge_ids}),
        generated_case=generated,
        context=context,
    )


def _reachable(public: dict[str, Any], selected: set[int]) -> set[int]:
    adjacency: dict[int, list[int]] = {}
    for edge in public["edges"]:
        if edge["edge_id"] not in selected:
            continue
        adjacency.setdefault(edge["u"], []).append(edge["v"])
        adjacency.setdefault(edge["v"], []).append(edge["u"])
    reached = {public["root"]}
    queue = deque(reached)
    while queue:
        vertex = queue.popleft()
        for neighbor in adjacency.get(vertex, []):
            if neighbor not in reached:
                reached.add(neighbor)
                queue.append(neighbor)
    return reached


def test_manifest_yaml_resources_and_private_virtual_agents() -> None:
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
    for case_id in CASE_IDS:
        profile = yaml.safe_load(
            (ROOT / f"tasks/tier1_np/new_rooted_group_steiner_tree/cases/{case_id}.yaml").read_text(
                encoding="utf-8"
            )
        )
        assert profile["parameters"] == task.case_parameters[case_id]
    assert tuple(VIRTUAL_AGENTS) == (
        "virtual-honest",
        "virtual-empty-edge-set",
        "virtual-invalid-edge-id",
    )


def test_c01_is_deterministic_scaled_unique_and_publicly_recoverable() -> None:
    generated = generate()
    assert generated == generate()
    assert generated.public_instance != generate(b"new-rooted-group-other").public_instance
    public = generated.public_instance
    assert public["num_vertices"] == 1_365
    assert len(public["edges"]) == 2_964
    assert len(public["groups"]) == 1_024
    assert all(len(group["vertices"]) == 1 for group in public["groups"])

    affordable = [edge for edge in public["edges"] if edge["weight"] <= public["budget"]]
    unaffordable = [edge for edge in public["edges"] if edge["weight"] > public["budget"]]
    assert len(affordable) == 1_364
    assert len(unaffordable) == 1_600
    assert sum(edge["weight"] for edge in affordable) == public["budget"]

    solved = solve_public_c01(public)
    assert set(solved) == set(generated.private_instance["reference_edge_ids"])
    evaluation = evaluate_edge_set(public, list(solved))
    assert evaluation.cost == public["budget"]
    assert evaluation.connected and evaluation.groups_hit
    assert submit(generated, list(solved)).terminal_status == TerminalStatus.ACCEPT


def test_every_reference_edge_is_forced_by_a_public_group_cut() -> None:
    generated = generate(b"new-rooted-group-cut-proof")
    public = generated.public_instance
    reference = set(generated.private_instance["reference_edge_ids"])
    grouped_vertices = {group["vertices"][0] for group in public["groups"]}
    for edge_id in reference:
        reached = _reachable(public, reference - {edge_id})
        assert grouped_vertices - reached


def test_acceptance_is_independent_of_private_reference() -> None:
    generated = generate(b"new-rooted-group-private-independence")
    answer = list(solve_public_c01(generated.public_instance))
    corrupted = replace(
        generated,
        private_instance={"reference_edge_ids": [0], "reference_cost": 1},
    )
    assert submit(corrupted, answer).terminal_status == TerminalStatus.ACCEPT


def test_toy_exhaustive_oracle_finds_exactly_one_accepted_subset() -> None:
    generated = generate(
        b"new-rooted-group-toy-oracle",
        parameters={
            "branching_factor": 2,
            "depth": 2,
            "minimum_tree_weight": 2,
            "maximum_tree_weight": 5,
            "num_extra_edges": 5,
        },
    )
    public = generated.public_instance
    edge_ids = [edge["edge_id"] for edge in public["edges"]]
    accepted: list[frozenset[int]] = []
    for size in range(len(edge_ids) + 1):
        for subset in combinations(edge_ids, size):
            evaluation = evaluate_edge_set(public, list(subset))
            if (
                evaluation.cost <= public["budget"]
                and evaluation.connected
                and evaluation.groups_hit
            ):
                accepted.append(frozenset(subset))
    assert accepted == [frozenset(generated.private_instance["reference_edge_ids"])]


def test_c02_is_deterministic_scaled_cactus_and_publicly_recoverable() -> None:
    generated = generate(b"new-rooted-group-c02-test", case_id="c02")
    assert generated == generate(b"new-rooted-group-c02-test", case_id="c02")
    assert (
        generated.public_instance
        != generate(b"new-rooted-group-c02-other", case_id="c02").public_instance
    )
    public = generated.public_instance
    assert public["num_vertices"] == 2_305
    assert len(public["edges"]) == 3_072
    assert len(public["groups"]) == 1_535
    assert sum(len(group["vertices"]) == 1 for group in public["groups"]) == 1
    assert sum(len(group["vertices"]) == 2 for group in public["groups"]) == 1_534
    assert all(edge["weight"] <= public["budget"] for edge in public["edges"])

    solved = solve_public_c02(public)
    evaluation = evaluate_edge_set(public, list(solved))
    assert evaluation.cost == public["budget"]
    assert evaluation.connected and evaluation.groups_hit
    private_evaluation = evaluate_edge_set(
        public, list(generated.private_instance["reference_edge_ids"])
    )
    assert private_evaluation.cost == public["budget"]
    assert private_evaluation.connected and private_evaluation.groups_hit
    assert submit(generated, list(solved)).terminal_status == TerminalStatus.ACCEPT


def test_c02_toy_dp_matches_exhaustive_public_edge_set_oracle() -> None:
    generated = generate(
        b"new-rooted-group-c02-oracle",
        case_id="c02",
        parameters={
            "num_cells": 3,
            "minimum_edge_weight": 1,
            "maximum_edge_weight": 5,
            "constraints_per_boundary": 2,
        },
    )
    public = generated.public_instance
    edge_ids = [edge["edge_id"] for edge in public["edges"]]
    feasible_costs = []
    for mask in range(1 << len(edge_ids)):
        selected = [edge_id for index, edge_id in enumerate(edge_ids) if (mask >> index) & 1]
        evaluation = evaluate_edge_set(public, selected)
        if evaluation.connected and evaluation.groups_hit:
            feasible_costs.append(evaluation.cost)
    assert min(feasible_costs) == public["budget"]
    solved = solve_public_c02(public)
    assert evaluate_edge_set(public, list(solved)).cost == min(feasible_costs)


def test_c03_is_deterministic_scaled_frontier_and_publicly_recoverable() -> None:
    generated = generate(b"new-rooted-group-c03-test", case_id="c03")
    assert generated == generate(b"new-rooted-group-c03-test", case_id="c03")
    assert (
        generated.public_instance
        != generate(b"new-rooted-group-c03-other", case_id="c03").public_instance
    )
    public = generated.public_instance
    assert public["num_vertices"] == 4_609
    assert len(public["edges"]) == 4_608
    assert len(public["groups"]) == 18_386
    assert sum(len(group["vertices"]) == 1 for group in public["groups"]) == 1_536
    assert sum(len(group["vertices"]) == 2 for group in public["groups"]) == 16_850
    assert all(edge["weight"] <= public["budget"] for edge in public["edges"])

    solved = solve_public_c03(public)
    evaluation = evaluate_edge_set(public, list(solved))
    assert evaluation.cost == public["budget"]
    assert evaluation.connected and evaluation.groups_hit
    assert submit(generated, list(solved)).terminal_status == TerminalStatus.ACCEPT


def test_c03_toy_frontier_matches_exhaustive_assignment_oracle() -> None:
    generated = generate(
        b"new-rooted-group-c03-oracle",
        case_id="c03",
        parameters={
            "num_variables": 8,
            "window_width": 3,
            "constraints_per_variable": 2,
            "minimum_edge_weight": 1,
            "maximum_edge_weight": 7,
        },
    )
    public = generated.public_instance
    root = public["root"]
    edge_by_pair = {tuple(sorted((edge["u"], edge["v"]))): edge for edge in public["edges"]}
    centers = sorted(
        group["vertices"][0] for group in public["groups"] if len(group["vertices"]) == 1
    )
    choices = []
    for center in centers:
        leaves = sorted(
            vertex
            for vertex in range(1, public["num_vertices"] + 1)
            if tuple(sorted((center, vertex))) in edge_by_pair and vertex != root
        )
        choices.append((center, leaves))
    feasible_costs = []
    for mask in range(1 << len(choices)):
        selected = []
        for index, (center, leaves) in enumerate(choices):
            selected.append(edge_by_pair[tuple(sorted((root, center)))]["edge_id"])
            selected.append(
                edge_by_pair[tuple(sorted((center, leaves[(mask >> index) & 1])))]["edge_id"]
            )
        evaluation = evaluate_edge_set(public, selected)
        if evaluation.connected and evaluation.groups_hit:
            feasible_costs.append(evaluation.cost)
    assert min(feasible_costs) == public["budget"]
    solved = solve_public_c03(public)
    assert evaluate_edge_set(public, list(solved)).cost == min(feasible_costs)


def test_c04_is_non_bijunctive_scaled_and_publicly_recoverable() -> None:
    generated = generate(b"new-rooted-group-c04-test", case_id="c04")
    assert generated == generate(b"new-rooted-group-c04-test", case_id="c04")
    assert (
        generated.public_instance
        != generate(b"new-rooted-group-c04-other", case_id="c04").public_instance
    )
    public = generated.public_instance
    assert public["num_vertices"] == 3_841
    assert len(public["edges"]) == 3_840
    assert len(public["groups"]) == 12_781
    sizes = {len(group["vertices"]) for group in public["groups"]}
    assert sizes == {1, 2, 3, 4}
    assert sum(len(group["vertices"]) >= 3 for group in public["groups"]) == 10_221
    assert all(edge["weight"] <= public["budget"] for edge in public["edges"])

    solved = solve_public_c04(public)
    evaluation = evaluate_edge_set(public, list(solved))
    assert evaluation.cost == public["budget"]
    assert evaluation.connected and evaluation.groups_hit
    assert submit(generated, list(solved)).terminal_status == TerminalStatus.ACCEPT


def test_c04_toy_matches_independent_exhaustive_assignment_oracle() -> None:
    generated = generate(
        b"new-rooted-group-c04-oracle",
        case_id="c04",
        parameters={
            "num_variables": 9,
            "window_width": 4,
            "clauses_per_variable": 3,
            "minimum_clause_size": 3,
            "maximum_clause_size": 4,
            "minimum_edge_weight": 1,
            "maximum_edge_weight": 7,
        },
    )
    public = generated.public_instance
    root = public["root"]
    edge_by_pair = {tuple(sorted((edge["u"], edge["v"]))): edge for edge in public["edges"]}
    centers = sorted(
        group["vertices"][0] for group in public["groups"] if len(group["vertices"]) == 1
    )
    choices = []
    for center in centers:
        leaves = sorted(
            vertex
            for vertex in range(1, public["num_vertices"] + 1)
            if tuple(sorted((center, vertex))) in edge_by_pair and vertex != root
        )
        choices.append((center, leaves))
    feasible_costs = []
    for mask in range(1 << len(choices)):
        selected = []
        for index, (center, leaves) in enumerate(choices):
            selected.append(edge_by_pair[tuple(sorted((root, center)))]["edge_id"])
            selected.append(
                edge_by_pair[tuple(sorted((center, leaves[(mask >> index) & 1])))]["edge_id"]
            )
        evaluation = evaluate_edge_set(public, selected)
        if evaluation.connected and evaluation.groups_hit:
            feasible_costs.append(evaluation.cost)
    assert min(feasible_costs) == public["budget"]
    solved = solve_public_c04(public)
    assert evaluate_edge_set(public, list(solved)).cost == min(feasible_costs)


def test_c05_is_scaled_running_intersection_and_publicly_recoverable() -> None:
    generated = generate(b"new-rooted-group-c05-test", case_id="c05")
    public = generated.public_instance
    assert public["num_vertices"] == 3_649
    assert len(public["edges"]) == 3_648
    assert len(public["groups"]) == 3_883
    assert {len(group["vertices"]) for group in public["groups"]} == {
        1,
        2,
        3,
        4,
        6,
        16,
    }
    assert sum(len(group["vertices"]) == 16 for group in public["groups"]) == 121
    assert sum(len(group["vertices"]) == 6 for group in public["groups"]) == 120
    assert all(edge["weight"] <= public["budget"] for edge in public["edges"])

    solved = solve_public_c05(public)
    evaluation = evaluate_edge_set(public, list(solved))
    assert evaluation.cost == public["budget"]
    assert evaluation.connected and evaluation.groups_hit
    assert submit(generated, list(solved)).terminal_status == TerminalStatus.ACCEPT


def test_c05_toy_tree_dp_matches_exhaustive_assignment_oracle() -> None:
    generated = generate(
        b"new-rooted-group-c05-oracle",
        case_id="c05",
        parameters={
            "num_bags": 3,
            "bag_width": 4,
            "separator_size": 2,
            "clauses_per_bag": 2,
            "minimum_clause_size": 3,
            "maximum_clause_size": 3,
            "minimum_edge_weight": 1,
            "maximum_edge_weight": 5,
        },
    )
    public = generated.public_instance
    root = public["root"]
    edge_by_pair = {tuple(sorted((edge["u"], edge["v"]))): edge for edge in public["edges"]}
    centers = sorted(
        group["vertices"][0] for group in public["groups"] if len(group["vertices"]) == 1
    )
    choices = []
    for center in centers:
        leaves = sorted(
            vertex
            for vertex in range(1, public["num_vertices"] + 1)
            if tuple(sorted((center, vertex))) in edge_by_pair and vertex != root
        )
        choices.append((center, leaves))
    feasible_costs = []
    for mask in range(1 << len(choices)):
        selected = []
        for index, (center, leaves) in enumerate(choices):
            selected.append(edge_by_pair[tuple(sorted((root, center)))]["edge_id"])
            selected.append(
                edge_by_pair[tuple(sorted((center, leaves[(mask >> index) & 1])))]["edge_id"]
            )
        evaluation = evaluate_edge_set(public, selected)
        if evaluation.connected and evaluation.groups_hit:
            feasible_costs.append(evaluation.cost)
    assert len(choices) == 8
    assert min(feasible_costs) == public["budget"]
    solved = solve_public_c05(public)
    assert evaluate_edge_set(public, list(solved)).cost == min(feasible_costs)


def test_c06_is_a_deep_shared_routing_tree_and_publicly_recoverable() -> None:
    generated = generate(b"new-rooted-group-c06-test", case_id="c06")
    assert generated == generate(b"new-rooted-group-c06-test", case_id="c06")
    public = generated.public_instance
    assert public["num_vertices"] == 12_285
    assert len(public["edges"]) == 12_284
    assert len(public["groups"]) == 20_475
    assert {len(group["vertices"]) for group in public["groups"]} == {1, 2, 3}
    assert all(edge["weight"] <= public["budget"] for edge in public["edges"])

    solved = solve_public_c06(public)
    assert set(solve_public(public)) == set(solved)
    evaluation = evaluate_edge_set(public, list(solved))
    assert len(solved) == 8_189
    assert evaluation.cost == public["budget"]
    assert evaluation.connected and evaluation.groups_hit
    assert submit(generated, list(solved)).terminal_status == TerminalStatus.ACCEPT


def test_c06_toy_ancestor_dp_matches_exhaustive_assignment_oracle() -> None:
    generated = generate(
        b"new-rooted-group-c06-oracle",
        case_id="c06",
        parameters={
            "branching_factor": 2,
            "depth": 2,
            "terminals_per_node": 2,
            "ancestor_window": 3,
            "groups_per_node": 3,
            "minimum_edge_weight": 1,
            "maximum_edge_weight": 5,
        },
    )
    public = generated.public_instance
    adjacency: dict[int, list[dict[str, int]]] = {}
    for edge in public["edges"]:
        adjacency.setdefault(edge["u"], []).append(edge)
        adjacency.setdefault(edge["v"], []).append(edge)
    terminal_pairs = [
        tuple(sorted(group["vertices"]))
        for group in public["groups"]
        if len(group["vertices"]) == 2
        and all(len(adjacency[vertex]) == 1 for vertex in group["vertices"])
        and next(
            endpoint
            for endpoint in (
                adjacency[group["vertices"][0]][0]["u"],
                adjacency[group["vertices"][0]][0]["v"],
            )
            if endpoint != group["vertices"][0]
        )
        == next(
            endpoint
            for endpoint in (
                adjacency[group["vertices"][1]][0]["u"],
                adjacency[group["vertices"][1]][0]["v"],
            )
            if endpoint != group["vertices"][1]
        )
    ]
    terminal_pairs.sort()
    terminal_vertices = {vertex for pair in terminal_pairs for vertex in pair}
    routing_edge_ids = {
        edge["edge_id"]
        for edge in public["edges"]
        if edge["u"] not in terminal_vertices and edge["v"] not in terminal_vertices
    }
    feasible_costs = []
    for mask in range(1 << len(terminal_pairs)):
        selected = set(routing_edge_ids)
        for index, pair in enumerate(terminal_pairs):
            terminal = pair[(mask >> index) & 1]
            selected.add(adjacency[terminal][0]["edge_id"])
        evaluation = evaluate_edge_set(public, list(selected))
        if evaluation.connected and evaluation.groups_hit:
            feasible_costs.append(evaluation.cost)
    assert len(terminal_pairs) == 7
    assert min(feasible_costs) == public["budget"]
    solved = solve_public_c06(public)
    assert evaluate_edge_set(public, list(solved)).cost == min(feasible_costs)


def test_participant_spec_has_relation_but_no_maintainer_hints() -> None:
    text = (ROOT / "tasks/tier1_np/new_rooted_group_steiner_tree/TASK_SPECIFICATION.md").read_text(
        encoding="utf-8"
    )
    lowered = text.lower()
    assert TASK_ID in text and TASK_VERSION in text
    assert "group_steiner.edge_set" in text
    for forbidden in (
        "c01",
        "c02",
        "c03",
        "c04",
        "c05",
        "c06",
        "spanning tree",
        "4-ary",
        "leaf",
        "singleton",
        "decoy",
        "branching",
        "depth",
        "1365",
        "1600",
        "1024",
        "solver",
        "algorithm",
        "family",
        "reference_edge_ids",
        "worked example",
        "cut proof",
    ):
        assert forbidden not in lowered
