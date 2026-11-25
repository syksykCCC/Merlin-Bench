from __future__ import annotations

from collections import Counter
from functools import cache
from pathlib import Path

import pytest
import yaml

from aipbench.core.models import ParticipantEvent, SessionMode
from aipbench.tasks.field61 import encode_field
from aipbench.tasks.new_boolean_hypercube_sumcheck import (
    CASE_IDS,
    CASE_PARAMETERS,
    TASK_ID,
    TASK_MANIFEST,
    create_task,
)
from aipbench.tasks.shared.boolean_hypercube_sumcheck import CLAIM_EVENT_KIND, POLY_EVENT_KIND
from aipbench.tasks.shared.boolean_hypercube_sumcheck_cases.common import parse_public_instance

ROOT = Path(__file__).resolve().parents[2]
EXPECTED_CASE_IDS = ("c01", "c02", "c03", "c04", "c05", "c06", "c07")
EXPECTED_CASE_TITLES = {
    "c01": "Rank-One Expander",
    "c02": "Signed-Equivalence Expander",
    "c03": "Hidden Cylindrical Two-Spin Model, Width 16",
    "c04": "Hidden Cylindrical Two-Spin Model, Width 12",
    "c05": "Cylindrical Monomer-Dimer Model",
    "c06": "Six-Vertex Torus",
    "c07": "Memory-Ten Tail-Biting Enumerator",
}
EXPECTED_SHAPES = {
    "c01": (384, Counter({2: 768}), 4),
    "c02": (360, Counter({1: 360, 2: 720}), 5),
    "c03": (400, Counter({1: 400, 2: 784}), 5),
    "c04": (396, Counter({1: 396, 2: 780}), 5),
    "c05": (354, Counter({1: 354, 3: 12, 4: 168}), 3),
    "c06": (288, Counter({1: 288, 4: 144}), 3),
    "c07": (320, Counter({1: 160, 2: 160, 4: 160}), 5),
}


@cache
def _generated(case_id: str, seed: bytes = b"new-sumcheck-default-seed"):
    return create_task().generator.generate(
        instance_seed=seed,
        case_id=case_id,
        case_parameters=CASE_PARAMETERS[case_id],
    )


def test_manifest_and_case_bundles_cover_seven_600_second_cases() -> None:
    assert CASE_IDS == EXPECTED_CASE_IDS
    assert tuple(CASE_PARAMETERS) == EXPECTED_CASE_IDS
    assert TASK_MANIFEST["id"] == TASK_ID
    assert TASK_MANIFEST["resources"]["wall_time_seconds"] == 600
    assert TASK_MANIFEST["protocol"]["max_events"] == 401
    root = ROOT / "tasks" / "tier2_interactive" / "new_boolean_hypercube_sumcheck"
    for case_id in EXPECTED_CASE_IDS:
        decoded = yaml.safe_load((root / "cases" / f"{case_id}.yaml").read_text("utf-8"))
        assert decoded["id"] == case_id
        assert decoded["title"] == EXPECTED_CASE_TITLES[case_id]
        assert decoded["parameters"] == dict(CASE_PARAMETERS[case_id])


@pytest.mark.parametrize("case_id", EXPECTED_CASE_IDS)
def test_generation_is_deterministic_public_only_and_has_exact_shape(case_id: str) -> None:
    generated = _generated(case_id)
    repeated = create_task().generator.generate(
        instance_seed=b"new-sumcheck-default-seed",
        case_id=case_id,
        case_parameters=CASE_PARAMETERS[case_id],
    )
    different = _generated(case_id, b"new-sumcheck-different-seed")
    assert generated == repeated
    assert generated.public_instance != different.public_instance
    assert generated.private_instance == {}
    model = parse_public_instance(generated.public_instance)
    expected_variables, expected_arities, expected_occurrence = EXPECTED_SHAPES[case_id]
    assert model.num_variables == expected_variables
    assert Counter(len(factor.scope) for factor in model.factors) == expected_arities
    occurrence = Counter(variable for factor in model.factors for variable in factor.scope)
    assert set(occurrence) == set(range(model.num_variables))
    assert max(occurrence.values()) == expected_occurrence


def test_algebraic_and_support_invariants_survive_hiding() -> None:
    rank_one = parse_public_instance(_generated("c01").public_instance)
    assert all(
        (factor.values[0] * factor.values[3] - factor.values[1] * factor.values[2])
        % ((1 << 61) - 1)
        == 0
        for factor in rank_one.factors
    )
    signed = parse_public_instance(_generated("c02").public_instance)
    assert all(
        sum(value != 0 for value in factor.values) == 2
        for factor in signed.factors
        if len(factor.scope) == 2
    )
    ice = parse_public_instance(_generated("c06").public_instance)
    assert all(
        sum(value != 0 for value in factor.values) == 6
        for factor in ice.factors
        if len(factor.scope) == 4
    )
    code = parse_public_instance(_generated("c07").public_instance)
    assert all(
        sum(value != 0 for value in factor.values) == 8
        for factor in code.factors
        if len(factor.scope) == 4
    )


class _Context:
    def __init__(self) -> None:
        self.tags: list[str] = []

    @property
    def mode(self) -> SessionMode:
        return SessionMode.DEV

    def random_field_element(self, *, tag: str, modulus: int) -> int:
        self.tags.append(tag)
        return 17

    def random_bytes(self, *, tag: str, length: int) -> bytes:
        raise AssertionError((tag, length))

    def random_int(self, *, tag: str, lower_inclusive: int, upper_exclusive: int) -> int:
        raise AssertionError((tag, lower_inclusive, upper_exclusive))

    def get_artifact_path(self, artifact_id: str) -> Path:
        raise AssertionError(artifact_id)


def test_protocol_uses_independent_randomness_domain() -> None:
    task = create_task()
    generated = _generated("c01")
    context = _Context()
    state = task.protocol.initialize(generated_case=generated, context=context)
    claim = task.protocol.handle_event(
        state=state,
        event=ParticipantEvent(
            sequence=0,
            kind=CLAIM_EVENT_KIND,
            payload={
                "variable_order": list(range(384)),
                "claimed_sum": encode_field(0),
            },
        ),
        generated_case=generated,
        context=context,
    )
    assert claim.terminal_status is None
    first_round = task.protocol.handle_event(
        state=claim.new_state,
        event=ParticipantEvent(
            sequence=1,
            kind=POLY_EVENT_KIND,
            payload={"round_index": 0, "coefficients": [encode_field(0)] * 6},
        ),
        generated_case=generated,
        context=context,
    )
    assert first_round.terminal_status is None
    assert context.tags == [f"{TASK_ID}/c01/sumcheck/round-0/challenge"]


def test_participant_specification_has_no_case_or_solver_disclosure() -> None:
    specification = (
        ROOT
        / "tasks"
        / "tier2_interactive"
        / "new_boolean_hypercube_sumcheck"
        / "TASK_SPECIFICATION.md"
    ).read_text(encoding="utf-8")
    forbidden = (
        "Rank-One",
        "Signed-Equivalence",
        "Equality-Lift",
        "min-fill",
        "DSU",
        "transfer matrix",
        "tail-biting",
        "num_variables: 384",
    )
    assert all(term not in specification for term in forbidden)
