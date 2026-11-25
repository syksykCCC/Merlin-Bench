from __future__ import annotations

import hashlib
from dataclasses import replace
from functools import cache
from pathlib import Path
from typing import Any

import pytest
import yaml

from aipbench.core.errors import ErrorCode
from aipbench.core.models import GeneratedCase, ParticipantEvent, SessionMode, TerminalStatus
from aipbench.tasks.image_size_lower_bound import (
    BEGIN_EVENT_KIND,
    CASE_IDS,
    CASE_PARAMETERS,
    CHALLENGE_REPLY_KIND,
    HASH_LANES,
    REQUIRED_SUCCESSES,
    RESPONSE_EVENT_KIND,
    TASK_MANIFEST,
    TASK_VERSION,
    VIRTUAL_AGENTS,
    ImageSizeReason,
    create_task,
    solve_public_hashes,
)
from aipbench.tasks.image_size_lower_bound_cases.c06 import count_grid_independent_sets
from aipbench.tasks.image_size_lower_bound_cases.common import (
    decode_gf2_bits,
    encode_gf2_bits,
    enumerate_image,
    evaluate_circuit,
    parse_public_circuit,
)

ROOT = Path(__file__).resolve().parents[2]
EXPECTED_CASE_IDS = ("c01", "c02", "c03", "c04", "c05", "c06")
EXPECTED_CASE_TITLES = {
    "c01": "Systematic subcube image",
    "c02": "Hidden affine image",
    "c03": "Hamming ball via truncation",
    "c04": "Separable nonlinear product code",
    "c05": "Rank-one binary matrix variety",
    "c06": "Grid independent-set image",
}
EXPECTED_IMAGE_SIZES = {
    "c01": 256,
    "c02": 256,
    "c03": 299,
    "c04": 4096,
    "c05": 466,
    "c06": 227,
}


@cache
def _case(case_id: str, seed: bytes = b"image-size-default-tests") -> GeneratedCase:
    return create_task().generator.generate(
        instance_seed=seed,
        case_id=case_id,
        case_parameters=CASE_PARAMETERS[case_id],
    )


class HashContext:
    def __init__(self, suffix: bytes = b"") -> None:
        self.suffix = suffix
        self.calls: list[tuple[str, int]] = []

    @property
    def mode(self) -> SessionMode:
        return SessionMode.EVAL

    def random_bytes(self, *, tag: str, length: int) -> bytes:
        call = (tag, length)
        if call in self.calls:
            raise AssertionError(f"duplicate random tag: {tag}")
        self.calls.append(call)
        return hashlib.sha256(tag.encode() + self.suffix).digest()[:length]

    def random_int(self, *, tag: str, lower_inclusive: int, upper_exclusive: int) -> int:
        raise AssertionError((tag, lower_inclusive, upper_exclusive))

    def random_field_element(self, *, tag: str, modulus: int) -> int:
        raise AssertionError((tag, modulus))

    def get_artifact_path(self, artifact_id: str) -> Path:
        raise AssertionError(artifact_id)


def _begin(generated: GeneratedCase, context: HashContext) -> tuple[Any, Any]:
    task = create_task()
    state = task.protocol.initialize(generated_case=generated, context=context)
    transition = task.protocol.handle_event(
        state=state,
        event=ParticipantEvent(sequence=0, kind=BEGIN_EVENT_KIND, payload={}),
        generated_case=generated,
        context=context,
    )
    return task, transition


def test_registry_yaml_manifest_and_schema_are_uniform() -> None:
    assert TASK_VERSION == "0.1.0"
    assert CASE_IDS == EXPECTED_CASE_IDS
    assert tuple(CASE_PARAMETERS) == EXPECTED_CASE_IDS
    assert TASK_MANIFEST["protocol"]["public_coin"] is True
    assert TASK_MANIFEST["protocol"]["max_events"] == 2
    assert TASK_MANIFEST["resources"]["wall_time_seconds"] == 600
    task_yaml = yaml.safe_load(
        (ROOT / "tasks" / "tier2_interactive" / "image_size_lower_bound" / "task.yaml").read_text(
            encoding="utf-8"
        )
    )
    assert task_yaml["resources"]["wall_time_seconds"] == 600
    case_root = ROOT / "tasks" / "tier2_interactive" / "image_size_lower_bound" / "cases"
    for case_id in EXPECTED_CASE_IDS:
        raw = yaml.safe_load((case_root / f"{case_id}.yaml").read_text(encoding="utf-8"))
        assert raw["id"] == case_id
        assert raw["title"] == EXPECTED_CASE_TITLES[case_id]
        assert raw["parameters"] == dict(CASE_PARAMETERS[case_id])

    schema_path = (
        ROOT
        / "tasks"
        / "tier2_interactive"
        / "image_size_lower_bound"
        / "schemas"
        / "public_instance.schema.json"
    )
    import json

    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    assert schema["properties"]["format_version"]["const"] == "aip-image-size/1"
    assert schema["properties"]["hash_lanes"]["const"] == HASH_LANES
    assert set(schema["required"]) == {
        "format_version",
        "circuit",
        "threshold_exponent",
        "hash_lanes",
    }


@pytest.mark.parametrize("case_id", EXPECTED_CASE_IDS)
def test_generation_recounts_final_public_image_and_is_seed_deterministic(case_id: str) -> None:
    generated = _case(case_id)
    repeated = create_task().generator.generate(
        instance_seed=b"image-size-default-tests",
        case_id=case_id,
        case_parameters=CASE_PARAMETERS[case_id],
    )
    different = _case(case_id, b"image-size-different-seed")
    assert repeated == generated
    assert different.public_instance != generated.public_instance
    assert generated.private_instance == {}
    assert set(generated.public_instance) == {
        "format_version",
        "circuit",
        "threshold_exponent",
        "hash_lanes",
    }
    assert generated.public_instance["hash_lanes"] == HASH_LANES
    assert "mathematical_family" not in generated.public_instance

    circuit = parse_public_circuit(generated.public_instance["circuit"])
    image = enumerate_image(circuit)
    expected = EXPECTED_IMAGE_SIZES[case_id]
    assert len(image) == expected == generated.generation_metadata["exact_image_size"]
    threshold = 1 << generated.public_instance["threshold_exponent"]
    assert 16 * threshold <= len(image) < 32 * threshold


def test_c03_image_is_exact_shifted_hamming_ball() -> None:
    generated = _case("c03")
    circuit = parse_public_circuit(generated.public_instance["circuit"])
    image = set(enumerate_image(circuit))
    center = evaluate_circuit(circuit, 0)
    offsets = {word ^ center for word in image}
    assert len(offsets) == sum(
        1 for word in range(1 << circuit.num_outputs) if word.bit_count() <= 3
    )
    assert all(word.bit_count() <= 3 for word in offsets)


def test_c06_transfer_count_matches_direct_grid_enumeration() -> None:
    rows, columns = 3, 4
    brute = 0
    for word in range(1 << (rows * columns)):
        valid = True
        for row in range(rows):
            for column in range(columns):
                vertex = row * columns + column
                if not (word >> vertex) & 1:
                    continue
                if column + 1 < columns and (word >> (vertex + 1)) & 1:
                    valid = False
                if row + 1 < rows and (word >> (vertex + columns)) & 1:
                    valid = False
        brute += valid
    assert count_grid_independent_sets(rows, columns) == brute == 227


@pytest.mark.parametrize(
    ("word", "length", "encoded"),
    [(0, 0, ""), (5, 4, "05"), (257, 9, "0101"), (1023, 10, "ff03")],
)
def test_gf2_codec_round_trips(word: int, length: int, encoded: str) -> None:
    assert encode_gf2_bits(word, length) == encoded
    assert decode_gf2_bits(encoded, length) == word


@pytest.mark.parametrize("raw", ["0", "0A", "0x00", "0004", "zz"])
def test_gf2_codec_rejects_noncanonical_strings(raw: str) -> None:
    with pytest.raises(ValueError):
        decode_gf2_bits(raw, 10)


@pytest.mark.parametrize(
    "circuit",
    [
        {"num_inputs": True, "num_outputs": 1, "gates": [], "outputs": [0]},
        {
            "num_inputs": 1,
            "num_outputs": 1,
            "gates": [{"op": "const", "value": False}],
            "outputs": [1],
        },
        {
            "num_inputs": 1,
            "num_outputs": 1,
            "gates": [{"op": "xor", "left": 0, "right": 1}],
            "outputs": [1],
        },
        {"num_inputs": 1, "num_outputs": 1, "gates": [], "outputs": [1]},
    ],
)
def test_circuit_parser_rejects_boolean_aliases_and_forward_references(circuit: object) -> None:
    with pytest.raises(ValueError):
        parse_public_circuit(circuit)


def test_generator_rejects_unknown_cases_and_bad_parameters() -> None:
    generator = create_task().generator
    with pytest.raises(ValueError, match="unsupported"):
        generator.generate(instance_seed=b"x", case_id="c07", case_parameters={})
    with pytest.raises(ValueError, match="integer"):
        generator.generate(
            instance_seed=b"x",
            case_id="c03",
            case_parameters={"dimension": True},
        )
    with pytest.raises(ValueError, match="unsupported Image-Size case parameter"):
        generator.generate(
            instance_seed=b"x",
            case_id="c01",
            case_parameters={"stale_parameter": 1},
        )
    with pytest.raises(TypeError, match="bytes"):
        generator.generate(  # type: ignore[arg-type]
            instance_seed="x", case_id="c01", case_parameters={}
        )


def test_randomness_barrier_and_challenge_shape() -> None:
    generated = _case("c01")
    task = create_task()
    context = HashContext()
    state = task.protocol.initialize(generated_case=generated, context=context)
    assert context.calls == []
    malformed = task.protocol.handle_event(
        state=state,
        event=ParticipantEvent(sequence=0, kind=BEGIN_EVENT_KIND, payload={"extra": 1}),
        generated_case=generated,
        context=context,
    )
    assert malformed.terminal_status is TerminalStatus.REJECT
    assert malformed.reason_code == ImageSizeReason.MALFORMED_EVENT
    assert malformed.milestones["completed_protocol_fraction"] == 0.0
    assert malformed.new_state.events_processed == 1
    assert (
        task.protocol.terminal_metrics(state=malformed.new_state)["completed_protocol_fraction"]
        == 0.0
    )
    assert context.calls == []

    _, begun = _begin(generated, context)
    assert begun.reply is not None and begun.reply.kind == CHALLENGE_REPLY_KIND
    hashes = begun.reply.payload["hashes"]
    k = generated.public_instance["threshold_exponent"] + 2
    n = generated.public_instance["circuit"]["num_outputs"]
    assert len(hashes) == HASH_LANES
    assert len(context.calls) == HASH_LANES * (k + 1)
    assert set(begun.public_state) == {"phase", "hash_lanes"}
    for item in hashes:
        assert set(item) == {"matrix_rows", "target"}
        assert len(item["matrix_rows"]) == k
        assert all(len(row) == 2 * ((n + 7) // 8) for row in item["matrix_rows"])
        assert len(item["target"]) == 2 * ((k + 7) // 8)


def test_exactly_64_valid_preimages_accept_and_63_reject() -> None:
    generated = _case("c01")
    context = HashContext(b"threshold")
    task, begun = _begin(generated, context)
    assert begun.reply is not None
    answers = solve_public_hashes(generated.public_instance, begun.reply.payload["hashes"])
    non_null = [index for index, answer in enumerate(answers) if answer is not None]
    assert len(non_null) >= REQUIRED_SUCCESSES
    exact = [None] * HASH_LANES
    for index in non_null[:REQUIRED_SUCCESSES]:
        exact[index] = answers[index]
    accepted = task.protocol.handle_event(
        state=begun.new_state,
        event=ParticipantEvent(1, RESPONSE_EVENT_KIND, {"preimages": exact}),
        generated_case=generated,
        context=context,
    )
    assert accepted.terminal_status is TerminalStatus.ACCEPT
    assert accepted.reason_code == ErrorCode.PROTOCOL_ACCEPT
    assert accepted.public_state["successful_lanes"] == REQUIRED_SUCCESSES

    second_context = HashContext(b"threshold")
    second_task, second_begun = _begin(generated, second_context)
    exact[non_null[REQUIRED_SUCCESSES - 1]] = None
    rejected = second_task.protocol.handle_event(
        state=second_begun.new_state,
        event=ParticipantEvent(1, RESPONSE_EVENT_KIND, {"preimages": exact}),
        generated_case=generated,
        context=second_context,
    )
    assert rejected.terminal_status is TerminalStatus.REJECT
    assert rejected.reason_code == ImageSizeReason.INSUFFICIENT_VALID_PREIMAGES
    assert rejected.public_state["successful_lanes"] == REQUIRED_SUCCESSES - 1
    assert rejected.milestones["completed_protocol_fraction"] == 0.5
    assert (
        second_task.protocol.terminal_metrics(state=rejected.new_state)[
            "completed_protocol_fraction"
        ]
        == 0.5
    )
    assert rejected.new_state.events_processed == 2


@pytest.mark.parametrize("index", [0, HASH_LANES // 2, HASH_LANES - 1])
def test_first_middle_last_noncanonical_preimage_is_malformed(index: int) -> None:
    generated = _case("c01")
    context = HashContext()
    task, begun = _begin(generated, context)
    payload: list[str | None] = [None] * HASH_LANES
    payload[index] = "0A00"
    transition = task.protocol.handle_event(
        state=begun.new_state,
        event=ParticipantEvent(1, RESPONSE_EVENT_KIND, {"preimages": payload}),
        generated_case=generated,
        context=context,
    )
    assert transition.terminal_status is TerminalStatus.REJECT
    assert transition.reason_code == ImageSizeReason.MALFORMED_EVENT


@pytest.mark.parametrize(
    ("payload", "artifacts"),
    [
        ({}, ()),
        ({"preimages": [None] * 127}, ()),
        ({"preimages": [None] * 129}, ()),
        ({"preimages": tuple([None] * 128)}, ()),
        ({"preimages": [None] * 128, "extra": 1}, ()),
        ({"preimages": [None] * 128}, ("sha256:unused",)),
    ],
)
def test_response_parser_is_strict(payload: dict[str, Any], artifacts: tuple[str, ...]) -> None:
    generated = _case("c01")
    context = HashContext()
    task, begun = _begin(generated, context)
    transition = task.protocol.handle_event(
        state=begun.new_state,
        event=ParticipantEvent(1, RESPONSE_EVENT_KIND, payload, artifact_refs=artifacts),
        generated_case=generated,
        context=context,
    )
    assert transition.terminal_status is TerminalStatus.REJECT
    assert transition.reason_code == ImageSizeReason.MALFORMED_EVENT


def test_no_twin_is_not_preclassified_and_fails_fixed_coin_threshold() -> None:
    generated = _case("c01")
    public = {
        "format_version": "aip-image-size/1",
        "circuit": {
            "num_inputs": 1,
            "num_outputs": 1,
            "gates": [{"op": "const", "value": 0}],
            "outputs": [1],
        },
        "threshold_exponent": 0,
        "hash_lanes": 128,
    }
    no_twin = replace(generated, public_instance=public)
    context = HashContext(b"no-twin")
    task, begun = _begin(no_twin, context)
    assert begun.terminal_status is None and begun.reply is not None
    answers = solve_public_hashes(public, begun.reply.payload["hashes"])
    assert sum(answer is not None for answer in answers) < REQUIRED_SUCCESSES
    rejected = task.protocol.handle_event(
        state=begun.new_state,
        event=ParticipantEvent(1, RESPONSE_EVENT_KIND, {"preimages": answers}),
        generated_case=no_twin,
        context=context,
    )
    assert rejected.reason_code == ImageSizeReason.INSUFFICIENT_VALID_PREIMAGES


def test_all_cases_publish_one_protocol_shape() -> None:
    descriptions = [
        dict(create_task().protocol.public_protocol_description(generated_case=_case(case_id)))
        for case_id in EXPECTED_CASE_IDS
    ]
    for description in descriptions:
        assert description["initial_event_kinds"] == [BEGIN_EVENT_KIND]
        assert set(description["event_schemas"]) == {BEGIN_EVENT_KIND, RESPONSE_EVENT_KIND}
        assert set(description["reply_schemas"]) == {CHALLENGE_REPLY_KIND}
        assert description["public_parameters"]["hash_lanes"] == HASH_LANES
        assert description["public_parameters"]["required_successes"] == REQUIRED_SUCCESSES
        assert description["public_parameters"]["bit_codec"] == "gf2-bits/hex-v1"


class FakeParticipantClient:
    def __init__(self, generated: GeneratedCase) -> None:
        self.generated = generated
        self.task = create_task()
        self.context = HashContext(b"virtual")
        self.state = self.task.protocol.initialize(generated_case=generated, context=self.context)
        self.status = "CONTINUE"
        self.reason_code: str | None = None

    def get_session(self) -> dict[str, Any]:
        return {"task_id": self.generated.task_id, "status": self.status}

    def get_protocol(self) -> dict[str, Any]:
        return dict(self.task.protocol.public_protocol_description(generated_case=self.generated))

    def get_instance(self) -> dict[str, Any]:
        return dict(self.generated.public_instance)

    def upload_artifact(self, *, content: bytes, media_type: str) -> dict[str, Any]:
        raise AssertionError((content, media_type))

    def submit_event(
        self,
        *,
        sequence: int,
        kind: str,
        payload: dict[str, Any],
        artifact_refs: tuple[str, ...] = (),
    ) -> dict[str, Any]:
        transition = self.task.protocol.handle_event(
            state=self.state,
            event=ParticipantEvent(sequence, kind, payload, artifact_refs),
            generated_case=self.generated,
            context=self.context,
        )
        self.state = transition.new_state
        self.status = (
            transition.terminal_status.value
            if transition.terminal_status is not None
            else "CONTINUE"
        )
        self.reason_code = transition.reason_code
        reply = None
        if transition.reply is not None:
            reply = {"kind": transition.reply.kind, "payload": dict(transition.reply.payload)}
        return {"status": self.status, "reason_code": self.reason_code, "reply": reply}


@pytest.mark.parametrize(
    ("agent_id", "status", "reason"),
    [
        ("virtual-honest", "ACCEPT", ErrorCode.PROTOCOL_ACCEPT),
        (
            "virtual-empty-response",
            "REJECT",
            ImageSizeReason.INSUFFICIENT_VALID_PREIMAGES,
        ),
    ],
)
def test_virtual_agents_use_only_public_client(
    tmp_path: Path, agent_id: str, status: str, reason: str
) -> None:
    client = FakeParticipantClient(_case("c06"))
    VIRTUAL_AGENTS[agent_id].run(client=client, workspace=tmp_path)
    assert client.status == status
    assert client.reason_code == reason
    assert list(tmp_path.iterdir()) == []
