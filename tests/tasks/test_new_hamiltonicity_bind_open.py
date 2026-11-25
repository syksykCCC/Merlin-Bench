from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from aipbench.tasks.new_hamiltonicity_bind_open import (
    CASE_IDS,
    CASE_PARAMETERS,
    TASK_ID,
    TASK_MANIFEST,
    VIRTUAL_AGENTS,
    create_task,
)
from aipbench.tasks.new_hamiltonicity_cases import build_case
from aipbench.tasks.shared.hamiltonicity_bind_open_cases.common import (
    DeterministicStream,
    adjacency,
    validate_hamilton_cycle,
)

ROOT = Path(__file__).resolve().parents[2]
EXPECTED_CASES = ("c01", "c02", "c03", "c04", "c05", "c06", "c07")
EXPECTED_PARAMETERS = {
    "c01": {"num_vertices": 1_000},
    "c02": {"part_size": 128},
    "c03": {"num_variables": 64, "num_clauses": 272},
    "c04": {"num_variables": 80, "num_equations": 80},
    "c05": {"num_variables": 40, "num_clauses": 320},
    "c06": {"num_variables": 160},
    "c07": {"num_variables": 23, "num_equations": 23},
}
EXPECTED_PROFILES = {
    "c01": (1_000, 1_998),
    "c02": (256, 16_384),
    "c03": (3_462, 5_829),
    "c04": (4_086, 6_885),
    "c05": (3_966, 6_645),
    "c06": (3_372, 5_453),
    "c07": (4_008, 6_721),
}


def _generate(case_id: str, seed: bytes = b"new-hamiltonicity-tests"):
    return create_task().generator.generate(
        instance_seed=seed,
        case_id=case_id,
        case_parameters={},
    )


def test_manifest_defaults_and_bundle_are_consistent() -> None:
    assert TASK_ID == "t2.new_hamiltonicity_bind_open"
    assert CASE_IDS == EXPECTED_CASES
    assert CASE_PARAMETERS == EXPECTED_PARAMETERS
    assert TASK_MANIFEST["resources"]["wall_time_seconds"] == 600
    assert TASK_MANIFEST["protocol"]["max_events"] == 2
    assert VIRTUAL_AGENTS == {}
    bundle = ROOT / "tasks" / "tier2_interactive" / "new_hamiltonicity_bind_open"
    task_yaml = yaml.safe_load((bundle / "task.yaml").read_text(encoding="utf-8"))
    assert task_yaml["id"] == TASK_ID
    assert task_yaml["resources"]["wall_time_seconds"] == 600
    for case_id, parameters in EXPECTED_PARAMETERS.items():
        case_yaml = yaml.safe_load(
            (bundle / "cases" / f"{case_id}.yaml").read_text(encoding="utf-8")
        )
        assert case_yaml["parameters"] == parameters


@pytest.mark.parametrize("case_id", EXPECTED_CASES)
def test_scaled_generators_are_deterministic_valid_and_fit_artifact_cap(case_id: str) -> None:
    generated = _generate(case_id)
    assert generated == _generate(case_id)
    assert (
        generated.public_instance
        != _generate(case_id, b"new-hamiltonicity-different").public_instance
    )
    assert generated.task_id == TASK_ID
    assert generated.private_instance == {}
    public = generated.public_instance
    assert (public["num_vertices"], len(public["edges"])) == EXPECTED_PROFILES[case_id]
    assert len(json.dumps(public, separators=(",", ":")).encode()) * 24 < 67_108_864

    blueprint = build_case(
        case_id,
        DeterministicStream(b"new-hamiltonicity-blueprint"),
        EXPECTED_PARAMETERS[case_id],
    )
    validate_hamilton_cycle(blueprint.graph, blueprint.cycle)


@pytest.mark.parametrize("case_id", EXPECTED_CASES)
def test_protocol_uses_only_new_schema_root(case_id: str) -> None:
    generated = _generate(case_id)
    description = create_task().protocol.public_protocol_description(generated_case=generated)
    refs = [
        entry["schema_ref"]
        for group in (description["event_schemas"], description["reply_schemas"])
        for entry in group.values()
    ]
    assert refs
    assert all("/new_hamiltonicity_bind_open/" in ref for ref in refs)


def test_participant_spec_has_no_case_or_solver_hints() -> None:
    spec = (
        ROOT
        / "tasks"
        / "tier2_interactive"
        / "new_hamiltonicity_bind_open"
        / "TASK_SPECIFICATION.md"
    ).read_text(encoding="utf-8")
    lowered = spec.lower()
    forbidden = (
        "wheel",
        "complete bipartite",
        "line graph",
        "cartesian product",
        "halin",
        "johnson graph",
        "planted cubic",
        "3-cnf",
        "affine parity",
        "forced triple",
        "planted assignment",
        "weak-signal",
        "2-sat",
        "implication",
        "five-xor",
        "xor gate",
        "gaussian elimination",
        "auxiliary",
        "affine",
        "case c01",
    )
    assert not any(term in lowered for term in forbidden)


def test_c05_reference_lift_has_forced_middle_vertices_and_exact_profile() -> None:
    blueprint = build_case(
        "c05",
        DeterministicStream(b"new-hamiltonicity-c05-reference"),
        EXPECTED_PARAMETERS["c05"],
    )
    validate_hamilton_cycle(blueprint.graph, blueprint.cycle)
    assert (blueprint.graph.num_vertices, len(blueprint.graph.edges)) == EXPECTED_PROFILES["c05"]
    assert blueprint.metadata == {
        "mathematical_family": "weakly_biased_planted_3cnf_directed_lift",
        "num_variables": 40,
        "num_clauses": 320,
        "planted_true_literal_probability": "5/8",
        "logical_directed_vertices": 1_322,
    }
    neighbors = adjacency(blueprint.graph)
    assert all(len(neighbors[3 * vertex + 1]) == 2 for vertex in range(1_322))
    assert all(
        chunk[1] == chunk[0] + 1 and chunk[2] == chunk[0] + 2 and chunk[0] % 3 == 0
        for chunk in (
            blueprint.cycle[index : index + 3] for index in range(0, len(blueprint.cycle), 3)
        )
    )


def test_c06_reference_lift_encodes_one_anchor_and_forced_triples() -> None:
    blueprint = build_case(
        "c06",
        DeterministicStream(b"new-hamiltonicity-c06-reference"),
        EXPECTED_PARAMETERS["c06"],
    )
    validate_hamilton_cycle(blueprint.graph, blueprint.cycle)
    assert (blueprint.graph.num_vertices, len(blueprint.graph.edges)) == EXPECTED_PROFILES["c06"]
    assert blueprint.metadata == {
        "mathematical_family": "anchored_2cnf_implication_ring_directed_lift",
        "num_variables": 160,
        "num_clauses": 321,
        "binary_clauses": 320,
        "unit_clauses": 1,
        "logical_directed_vertices": 1_124,
    }
    neighbors = adjacency(blueprint.graph)
    assert all(len(neighbors[3 * vertex + 1]) == 2 for vertex in range(1_124))
    assert all(
        chunk[1] == chunk[0] + 1 and chunk[2] == chunk[0] + 2 and chunk[0] % 3 == 0
        for chunk in (
            blueprint.cycle[index : index + 3] for index in range(0, len(blueprint.cycle), 3)
        )
    )


def test_c07_reference_lift_cloaks_a_full_rank_five_xor_system() -> None:
    blueprint = build_case(
        "c07",
        DeterministicStream(b"new-hamiltonicity-c07-reference"),
        EXPECTED_PARAMETERS["c07"],
    )
    validate_hamilton_cycle(blueprint.graph, blueprint.cycle)
    assert (blueprint.graph.num_vertices, len(blueprint.graph.edges)) == EXPECTED_PROFILES["c07"]
    assert blueprint.metadata == {
        "mathematical_family": "auxiliary_cloaked_full_rank_five_xor_directed_lift",
        "original_variables": 23,
        "auxiliary_variables": 69,
        "num_equations": 23,
        "num_clauses": 322,
        "logical_directed_vertices": 1_336,
    }
    neighbors = adjacency(blueprint.graph)
    assert all(len(neighbors[3 * vertex + 1]) == 2 for vertex in range(1_336))
    assert all(
        chunk[1] == chunk[0] + 1 and chunk[2] == chunk[0] + 2 and chunk[0] % 3 == 0
        for chunk in (
            blueprint.cycle[index : index + 3] for index in range(0, len(blueprint.cycle), 3)
        )
    )
