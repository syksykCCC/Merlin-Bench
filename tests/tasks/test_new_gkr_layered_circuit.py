from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from aipbench.tasks.new_gkr_layered_circuit import (
    CASE_IDS,
    CASE_PARAMETERS,
    TASK_ID,
    TASK_MANIFEST,
    VIRTUAL_AGENTS,
    create_task,
)
from aipbench.tasks.shared.gkr_layered_circuit_cases.common import (
    evaluate_circuit,
    parse_public_instance,
)

ROOT = Path(__file__).resolve().parents[2]
EXPECTED_CASES = ("c01", "c02", "c03", "c04", "c05", "c06", "c07")
EXPECTED_PARAMETERS = {
    "c01": {"vector_length": 64},
    "c02": {"batch_size": 8, "time_steps": 6},
    "c03": {"batch_size": 1, "matrix_order": 8},
    "c04": {"vector_length": 128},
    "c05": {"records": 8, "payload_fields": 4, "expansion_width": 524_288},
    "c06": {"ring_length": 256, "time_steps": 4, "expansion_width": 524_288},
    "c07": {"num_vertices": 16, "squarings": 4, "expansion_width": 262_144},
}
EXPECTED_PROFILES = {
    "c01": (7, 255, 63),
    "c02": (16, 847, 184),
    "c03": (11, 2_303, 137),
    "c04": (24, 6_655, 368),
    "c05": (37, 527_039, 499),
    "c06": (25, 533_247, 419),
    "c07": (28, 290_303, 512),
}
EXPECTED_PUBLIC_BYTES = {
    "c01": 14_619,
    "c02": 73_844,
    "c03": 194_142,
    "c04": 581_815,
    "c05": 48_319_545,
    "c06": 49_876_409,
    "c07": 27_057_216,
}


def _generate(case_id: str, seed: bytes = b"new-gkr-tests"):
    return create_task().generator.generate(
        instance_seed=seed,
        case_id=case_id,
        case_parameters={},
    )


def test_manifest_defaults_and_bundle_are_consistent() -> None:
    assert TASK_ID == "t2.new_gkr_layered_circuit"
    assert CASE_IDS == EXPECTED_CASES
    assert CASE_PARAMETERS == EXPECTED_PARAMETERS
    assert TASK_MANIFEST["resources"]["wall_time_seconds"] == 600
    assert TASK_MANIFEST["protocol"]["max_events"] == 513
    assert VIRTUAL_AGENTS == {}
    bundle = ROOT / "tasks" / "tier2_interactive" / "new_gkr_layered_circuit"
    task_yaml = yaml.safe_load((bundle / "task.yaml").read_text(encoding="utf-8"))
    assert task_yaml["id"] == TASK_ID
    assert task_yaml["resources"]["wall_time_seconds"] == 600
    for case_id, parameters in EXPECTED_PARAMETERS.items():
        case_yaml = yaml.safe_load(
            (bundle / "cases" / f"{case_id}.yaml").read_text(encoding="utf-8")
        )
        assert case_yaml["parameters"] == parameters
    for schema_path in (bundle / "schemas").glob("*.json"):
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        assert schema["$id"].startswith("aipbench://t2.new_gkr_layered_circuit/")


@pytest.mark.parametrize("case_id", EXPECTED_CASES)
def test_scaled_generators_are_deterministic_valid_and_match_frozen_profiles(
    case_id: str,
) -> None:
    generated = _generate(case_id)
    assert generated == _generate(case_id)
    assert generated.public_instance != _generate(case_id, b"new-gkr-different").public_instance
    assert generated.task_id == TASK_ID
    assert generated.private_instance == {}
    circuit = parse_public_instance(generated.public_instance)
    assert len(evaluate_circuit(circuit)[0]) == 1
    metadata = generated.generation_metadata
    assert (
        metadata["depth"],
        metadata["total_positions"],
        metadata["barriers"],
    ) == EXPECTED_PROFILES[case_id]
    # Layer permutations change the decimal digit lengths of numeric child indices slightly.
    assert abs(metadata["public_bytes"] - EXPECTED_PUBLIC_BYTES[case_id]) < 2_000
    assert circuit.barriers <= 512


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
    assert all("/new_gkr_layered_circuit/" in ref for ref in refs)
    assert description["public_parameters"]["total_barriers"] == EXPECTED_PROFILES[case_id][2]


def test_participant_spec_has_no_case_or_solver_hints() -> None:
    spec = (
        ROOT / "tasks" / "tier2_interactive" / "new_gkr_layered_circuit" / "TASK_SPECIFICATION.md"
    ).read_text(encoding="utf-8")
    lowered = spec.lower()
    forbidden = (
        "inner product",
        "recurrence",
        "matrix triple",
        "hadamard",
        "bitonic",
        "rule 110",
        "transitive closure",
        "sparse folding",
        "persistent prover",
        "case c01",
    )
    assert not any(term in lowered for term in forbidden)
