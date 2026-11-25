from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

import yaml

from aipbench.core.models import ParticipantEvent, SessionMode, TerminalStatus
from aipbench.tasks.new_list_graph_homomorphism import (
    CASE_IDS,
    MAPPING_EVENT_KIND,
    TASK_ID,
    TASK_VERSION,
    VIRTUAL_AGENTS,
    create_task,
    evaluate_mapping,
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
    seed: bytes = b"new-list-hom-c01-test",
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


def submit(generated: Any, mapping: list[int]) -> Any:
    task = create_task()
    context = FakeContext()
    state = task.protocol.initialize(generated_case=generated, context=context)
    return task.protocol.handle_event(
        state=state,
        event=ParticipantEvent(
            sequence=0,
            kind=MAPPING_EVENT_KIND,
            payload={"mapping": mapping},
        ),
        generated_case=generated,
        context=context,
    )


def test_manifest_yaml_and_single_registration_match() -> None:
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
            (ROOT / f"tasks/tier1_np/new_list_graph_homomorphism/cases/{case_id}.yaml").read_text(
                encoding="utf-8"
            )
        )
        assert profile["parameters"] == task.case_parameters[case_id]
    assert tuple(VIRTUAL_AGENTS) == (
        "virtual-honest",
        "virtual-wrong-length",
        "virtual-invalid-target",
    )


def test_c01_is_deterministic_unique_and_publicly_recoverable() -> None:
    generated = generate()
    assert generated == generate()
    assert generated.public_instance != generate(b"new-list-hom-other").public_instance
    public = generated.public_instance
    assert public["source_num_vertices"] == 1_024
    assert len(public["source_edges"]) == 960
    assert public["target_num_vertices"] == 3
    assert len(public["target_edges"]) == 3
    assert sum(len(item["allowed_targets"]) == 1 for item in public["lists"]) == 64
    assert sum(len(item["allowed_targets"]) == 2 for item in public["lists"]) == 960

    mapping = solve_public_c01(public)
    assert mapping == tuple(generated.private_instance["reference_mapping"])
    assert evaluate_mapping(public, list(mapping)) == (True, True)
    assert submit(generated, list(mapping)).terminal_status == TerminalStatus.ACCEPT

    changed = list(mapping)
    changed[0] = next(
        target
        for target in range(1, 4)
        if target
        not in next(
            item["allowed_targets"] for item in public["lists"] if item["source_vertex"] == 1
        )
    )
    assert submit(generated, changed).terminal_status == TerminalStatus.REJECT


def test_acceptance_is_independent_of_private_reference() -> None:
    generated = generate(b"new-list-hom-private-independence")
    mapping = list(solve_public_c01(generated.public_instance))
    corrupted = replace(
        generated,
        private_instance={"reference_mapping": [1] * len(mapping)},
    )
    assert submit(corrupted, mapping).terminal_status == TerminalStatus.ACCEPT


def test_c02_is_a_unique_publicly_recoverable_tree_csp() -> None:
    generated = generate(b"new-list-hom-c02-test", case_id="c02")
    assert generated == generate(b"new-list-hom-c02-test", case_id="c02")
    public = generated.public_instance
    assert public["source_num_vertices"] == 1_365
    assert len(public["source_edges"]) == 1_364
    assert public["target_num_vertices"] == 8_190
    assert len(public["target_edges"]) == 8_184
    assert sum(len(item["allowed_targets"]) == 1 for item in public["lists"]) == 1
    assert sum(len(item["allowed_targets"]) == 6 for item in public["lists"]) == 1_364

    mapping = solve_public_c02(public)
    assert mapping == tuple(generated.private_instance["reference_mapping"])
    assert evaluate_mapping(public, list(mapping)) == (True, True)
    assert submit(generated, list(mapping)).terminal_status == TerminalStatus.ACCEPT


def test_c02_toy_matches_exhaustive_mapping_oracle() -> None:
    generated = generate(
        b"new-list-hom-c02-oracle",
        case_id="c02",
        parameters={"branching_factor": 2, "depth": 2, "domain_size": 2},
    )
    public = generated.public_instance
    mapping = solve_public_c02(public)
    allowed = {item["source_vertex"]: item["allowed_targets"] for item in public["lists"]}
    import itertools

    solutions = [
        candidate
        for candidate in itertools.product(*(allowed[vertex] for vertex in range(1, 8)))
        if evaluate_mapping(public, list(candidate)) == (True, True)
    ]
    assert solutions == [mapping]


def test_c03_switched_cfi_profile_and_public_reference() -> None:
    generated = generate(b"formal-c03", case_id="c03")
    public = generated.public_instance
    assert public["source_num_vertices"] == 2_400
    assert len(public["source_edges"]) == 3_600
    assert public["target_num_vertices"] == 2_400
    assert len(public["target_edges"]) == 3_600
    assert set(len(item["allowed_targets"]) for item in public["lists"]) == {480, 720}
    mapping = solve_public_c03(public)
    assert evaluate_mapping(public, list(mapping)) == (True, True)
    assert submit(generated, list(mapping)).terminal_status == TerminalStatus.ACCEPT


def test_c03_toy_private_witness_is_an_independently_checked_isomorphism() -> None:
    generated = generate(
        b"new-list-hom-c03-toy",
        case_id="c03",
        parameters={"lift_factor": 2},
    )
    mapping = generated.private_instance["reference_mapping"]
    assert sorted(mapping) == list(range(1, len(mapping) + 1))
    assert evaluate_mapping(generated.public_instance, mapping) == (True, True)


def test_c04_double_line_profile_and_public_reference() -> None:
    generated = generate(b"formal-c04", case_id="c04")
    public = generated.public_instance
    assert public["source_num_vertices"] == 3_600
    assert len(public["source_edges"]) == 10_800
    assert public["target_num_vertices"] == 3_600
    assert len(public["target_edges"]) == 10_800
    assert set(len(item["allowed_targets"]) for item in public["lists"]) == {360, 720}
    mapping = solve_public_c04(public)
    assert evaluate_mapping(public, list(mapping)) == (True, True)
    assert submit(generated, list(mapping)).terminal_status == TerminalStatus.ACCEPT


def test_c04_toy_private_witness_is_an_independently_checked_isomorphism() -> None:
    generated = generate(
        b"new-list-hom-c04-toy",
        case_id="c04",
        parameters={"lift_factor": 2},
    )
    mapping = generated.private_instance["reference_mapping"]
    assert sorted(mapping) == list(range(1, len(mapping) + 1))
    assert evaluate_mapping(generated.public_instance, mapping) == (True, True)


def test_c05_symmetric_cover_profile_and_public_reference() -> None:
    generated = generate(b"formal-c05-direct-cfi", case_id="c05")
    public = generated.public_instance
    assert public["source_num_vertices"] == 1_800
    assert len(public["source_edges"]) == 2_700
    assert public["target_num_vertices"] == 1_800
    assert len(public["target_edges"]) == 2_700
    assert set(len(item["allowed_targets"]) for item in public["lists"]) == {
        360,
        540,
    }
    mapping = solve_public_c05(public)
    assert evaluate_mapping(public, list(mapping)) == (True, True)
    assert submit(generated, list(mapping)).terminal_status == TerminalStatus.ACCEPT


def test_c05_local_frame_oracle_and_toy_private_witness() -> None:
    from aipbench.tasks.new_homomorphism_cases.c03 import _EVEN_TRIPLES

    for frame in _EVEN_TRIPLES:
        images = {
            tuple(bit ^ flip for bit, flip in zip(triple, frame, strict=True))
            for triple in _EVEN_TRIPLES
        }
        assert images == set(_EVEN_TRIPLES)
    generated = generate(
        b"new-list-hom-c05-toy",
        case_id="c05",
        parameters={"lift_factor": 2},
    )
    mapping = generated.private_instance["reference_mapping"]
    assert sorted(mapping) == list(range(1, len(mapping) + 1))
    assert evaluate_mapping(generated.public_instance, mapping) == (True, True)


def test_c06_double_line_replicate_profile_and_public_reference() -> None:
    generated = generate(b"formal-c06-replicate", case_id="c06")
    public = generated.public_instance
    assert public["source_num_vertices"] == 3_600
    assert len(public["source_edges"]) == 10_800
    assert public["target_num_vertices"] == 3_600
    assert len(public["target_edges"]) == 10_800
    assert set(len(item["allowed_targets"]) for item in public["lists"]) == {
        360,
        720,
    }
    assert generated.generation_metadata["difficulty_replicate_of"] == "c04"
    mapping = solve_public_c06(public)
    assert evaluate_mapping(public, list(mapping)) == (True, True)
    assert submit(generated, list(mapping)).terminal_status == TerminalStatus.ACCEPT


def test_c06_replicate_is_seed_separated_from_c04() -> None:
    seed = b"new-list-hom-c06-separation"
    c04_public = generate(seed, case_id="c04").public_instance
    c06_public = generate(seed, case_id="c06").public_instance
    assert c06_public != c04_public


def test_c06_has_no_constant_list_class_quotient_homomorphism() -> None:
    public = generate(b"formal-c06-replicate", case_id="c06").public_instance
    domains = [frozenset() for _ in range(public["source_num_vertices"])]
    for item in public["lists"]:
        domains[item["source_vertex"] - 1] = frozenset(item["allowed_targets"])
    classes = sorted(set(domains), key=lambda domain: min(domain))
    class_id = {domain: index for index, domain in enumerate(classes)}
    source_class = [class_id[domain] for domain in domains]
    quotient_edges = {
        tuple(sorted((source_class[edge["u"] - 1], source_class[edge["v"] - 1])))
        for edge in public["source_edges"]
    }
    # A loop says that two adjacent source vertices share one identical public
    # list. A class-constant map would send that edge to a target loop, but the
    # target is simple and loopless, so the complete quotient CSP is impossible.
    assert any(first == second for first, second in quotient_edges)


def test_c06_toy_private_witness_is_an_independently_checked_isomorphism() -> None:
    generated = generate(
        b"new-list-hom-c06-toy",
        case_id="c06",
        parameters={"lift_factor": 2},
    )
    mapping = generated.private_instance["reference_mapping"]
    assert sorted(mapping) == list(range(1, len(mapping) + 1))
    assert evaluate_mapping(generated.public_instance, mapping) == (True, True)


def test_participant_spec_has_relation_but_no_maintainer_hints() -> None:
    text = (ROOT / "tasks/tier1_np/new_list_graph_homomorphism/TASK_SPECIFICATION.md").read_text(
        encoding="utf-8"
    )
    lowered = text.lower()
    assert TASK_ID in text and TASK_VERSION in text
    assert "homomorphism.assignment" in text
    for forbidden in (
        "c01",
        "path",
        "anchor",
        "binary",
        "component",
        "1024",
        "solver",
        "reference_mapping",
        "worked example",
        "propagat",
        "permutation constraint",
        "branching_factor",
        "domain_size",
        "c03",
        "cfi",
        "isomorphism",
        "frame",
        "switch",
        "lift_factor",
        "c04",
        "line graph",
        "double line",
        "clique",
        "c05",
        "c06",
        "cyclic",
        "cover",
        "gq",
    ):
        assert forbidden not in lowered
