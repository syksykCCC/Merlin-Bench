"""Goldwasser--Sipser Image-Size Lower Bound with 128 affine-hash lanes."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from aipbench.core.errors import ErrorCode
from aipbench.core.models import (
    GeneratedCase,
    ParticipantEvent,
    ProtocolReply,
    TerminalStatus,
    Transition,
)
from aipbench.core.protocol import ArthurContext, ParticipantClient, VirtualAgent
from aipbench.tasks.image_size_lower_bound_cases import CASE_DEFINITIONS, CASE_PARAMETERS
from aipbench.tasks.image_size_lower_bound_cases.common import (
    BooleanCircuit,
    DeterministicStream,
    decode_gf2_bits,
    encode_gf2_bits,
    enumerate_image,
    evaluate_circuit,
    finalize_blueprint,
    hash_word,
    is_strict_integer,
    parse_public_circuit,
)

TASK_ID: Final = "t2.image_size_lower_bound"
TASK_VERSION: Final = "0.1.0"
CASE_ID: Final = "c01"
CASE_IDS: Final[tuple[str, ...]] = tuple(CASE_PARAMETERS)

HASH_LANES: Final = 128
REQUIRED_SUCCESSES: Final = 64
BEGIN_EVENT_KIND: Final = "image.begin"
CHALLENGE_REPLY_KIND: Final = "image.challenge"
RESPONSE_EVENT_KIND: Final = "image.response"

_PUBLIC_INSTANCE_FIELDS: Final = frozenset(
    {"format_version", "circuit", "threshold_exponent", "hash_lanes"}
)
_RESPONSE_FIELDS: Final = frozenset({"preimages"})
_HASH_FIELDS: Final = frozenset({"matrix_rows", "target"})


class ImageSizeReason:
    """Stable participant-visible terminal reasons."""

    MALFORMED_EVENT = "IMAGE_SIZE_MALFORMED_EVENT"
    INSUFFICIENT_VALID_PREIMAGES = "IMAGE_SIZE_INSUFFICIENT_VALID_PREIMAGES"


TASK_MANIFEST: Final[Mapping[str, Any]] = {
    "id": TASK_ID,
    "version": TASK_VERSION,
    "tier": 2,
    "title": "Goldwasser--Sipser Image-Size Lower Bound",
    "plugin": {"entrypoint": "aipbench.tasks.image_size_lower_bound:create_task"},
    "protocol": {
        "api_version": "aip/1",
        "mode": "interactive",
        "public_coin": True,
        "one_shot_eval": True,
        "max_events": 2,
        "participant_feedback": {"dev": "verbose", "eval": "minimal"},
    },
    "randomness": {
        "model": "committed_prg",
        "reveal_on_terminal": True,
        "domain_separation": "required",
    },
    "instance": {
        "public_schema": (
            "tasks/tier2_interactive/image_size_lower_bound/schemas/public_instance.schema.json"
        ),
        "private_schema": (
            "tasks/tier2_interactive/image_size_lower_bound/schemas/private_instance.schema.json"
        ),
    },
    "resources": {
        "wall_time_seconds": 600,
        "cpu_cores": 4,
        "memory_mb": 4096,
        "disk_mb": 4096,
        "max_artifact_bytes": 67_108_864,
        "max_events": 2,
    },
    "audit": {
        "replay_mode": "strict",
        "require_signature": True,
        "require_seed_commitment": True,
        "require_instance_digest": True,
        "require_event_chain": True,
        "require_seed_reveal": True,
    },
    "scoring": {
        "primary": "binary_accept",
        "partial_progress": "completed_protocol_fraction",
    },
    "soundness": {
        "class": "public_coin_interactive",
        "statement": "NO instances are accepted with probability below 2^-23",
        "error_bound": "<2^-23",
    },
}


def _validate_public_instance(public_instance: Mapping[str, Any]) -> tuple[BooleanCircuit, int]:
    if set(public_instance) != _PUBLIC_INSTANCE_FIELDS:
        raise ValueError("malformed generated Image-Size instance")
    if public_instance.get("format_version") != "aip-image-size/1":
        raise ValueError("unsupported Image-Size instance format")
    if public_instance.get("hash_lanes") != HASH_LANES:
        raise ValueError(f"Image-Size requires exactly {HASH_LANES} hash lanes")
    threshold_exponent = public_instance.get("threshold_exponent")
    if not is_strict_integer(threshold_exponent) or not 0 <= threshold_exponent <= 60:
        raise ValueError("threshold_exponent is outside the supported strict integer envelope")
    circuit = parse_public_circuit(public_instance.get("circuit"))
    hash_rows = threshold_exponent + 2
    if hash_rows > 62:
        raise ValueError("affine hash output exceeds the supported envelope")
    return circuit, hash_rows


class ImageSizeLowerBoundGenerator:
    """Dispatch six deterministic structural circuit distributions."""

    def generate(
        self,
        *,
        instance_seed: bytes,
        case_id: str,
        case_parameters: Mapping[str, Any],
    ) -> GeneratedCase:
        if not isinstance(instance_seed, bytes):
            raise TypeError("instance_seed must be bytes")
        definition = CASE_DEFINITIONS.get(case_id)
        if definition is None:
            raise ValueError(f"unsupported Image-Size case: {case_id}")
        unknown_parameters = set(case_parameters) - set(definition.parameters)
        if unknown_parameters:
            unknown = ", ".join(sorted(unknown_parameters))
            raise ValueError(f"unsupported Image-Size case parameter(s): {unknown}")
        parameters = dict(definition.parameters)
        parameters.update(case_parameters)
        stream = DeterministicStream(instance_seed)
        blueprint = definition.builder(stream, parameters)
        finalized = finalize_blueprint(case_id=case_id, blueprint=blueprint, stream=stream)
        _validate_public_instance(finalized.public_instance)
        return GeneratedCase(
            task_id=TASK_ID,
            task_version=TASK_VERSION,
            case_id=case_id,
            public_instance=finalized.public_instance,
            private_instance=finalized.private_instance,
            generation_metadata=finalized.generation_metadata,
        )


@dataclass(frozen=True)
class AffineChallenge:
    rows: tuple[int, ...]
    target: int


@dataclass(frozen=True)
class ImageSizeProtocolState:
    """Arthur-private state; challenges never enter public_state."""

    phase: str = "awaiting_begin"
    challenges: tuple[AffineChallenge, ...] = ()
    terminal_status: TerminalStatus | None = None
    reason_code: str | None = None
    events_processed: int = 0
    successful_lanes: int = 0


def _random_word(*, context: ArthurContext, tag: str, length: int) -> int:
    width = (length + 7) // 8
    word = int.from_bytes(context.random_bytes(tag=tag, length=width), "little")
    return word & ((1 << length) - 1)


def _make_challenges(
    *,
    circuit: BooleanCircuit,
    hash_rows: int,
    generated_case: GeneratedCase,
    context: ArthurContext,
) -> tuple[tuple[AffineChallenge, ...], list[Mapping[str, Any]]]:
    private: list[AffineChallenge] = []
    public: list[Mapping[str, Any]] = []
    for lane in range(HASH_LANES):
        rows = tuple(
            _random_word(
                context=context,
                tag=(f"{TASK_ID}/{generated_case.case_id}/image/lane-{lane}/matrix/row-{row}"),
                length=circuit.num_outputs,
            )
            for row in range(hash_rows)
        )
        target = _random_word(
            context=context,
            tag=f"{TASK_ID}/{generated_case.case_id}/image/lane-{lane}/target",
            length=hash_rows,
        )
        private.append(AffineChallenge(rows, target))
        public.append(
            {
                "matrix_rows": [encode_gf2_bits(row, circuit.num_outputs) for row in rows],
                "target": encode_gf2_bits(target, hash_rows),
            }
        )
    return tuple(private), public


def _parse_preimages(payload: object, num_inputs: int) -> tuple[int | None, ...] | None:
    if not isinstance(payload, Mapping) or set(payload) != _RESPONSE_FIELDS:
        return None
    raw_preimages = payload.get("preimages")
    if not isinstance(raw_preimages, list) or len(raw_preimages) != HASH_LANES:
        return None
    result: list[int | None] = []
    for raw in raw_preimages:
        if raw is None:
            result.append(None)
            continue
        try:
            result.append(decode_gf2_bits(raw, num_inputs))
        except ValueError:
            return None
    return tuple(result)


class ImageSizeLowerBoundProtocol:
    """Two-event public-coin affine-bucket protocol."""

    task_id = TASK_ID
    task_version = TASK_VERSION

    def initialize(
        self, *, generated_case: GeneratedCase, context: ArthurContext
    ) -> ImageSizeProtocolState:
        del context
        self._validate_task_identity(generated_case)
        _validate_public_instance(generated_case.public_instance)
        return ImageSizeProtocolState()

    def public_protocol_description(self, *, generated_case: GeneratedCase) -> Mapping[str, Any]:
        self._validate_task_identity(generated_case)
        circuit, hash_rows = _validate_public_instance(generated_case.public_instance)
        return {
            "api_version": "aip/1",
            "mode": "interactive",
            "public_coin": True,
            "initial_event_kinds": [BEGIN_EVENT_KIND],
            "event_schemas": {
                BEGIN_EVENT_KIND: {
                    "schema_ref": (
                        "tasks/tier2_interactive/image_size_lower_bound/schemas/begin.schema.json"
                    )
                },
                RESPONSE_EVENT_KIND: {
                    "schema_ref": (
                        "tasks/tier2_interactive/image_size_lower_bound/schemas/"
                        "response.schema.json"
                    )
                },
            },
            "reply_schemas": {
                CHALLENGE_REPLY_KIND: {
                    "schema_ref": (
                        "tasks/tier2_interactive/image_size_lower_bound/schemas/"
                        "challenge.schema.json"
                    )
                }
            },
            "public_parameters": {
                "num_inputs": circuit.num_inputs,
                "num_outputs": circuit.num_outputs,
                "hash_rows": hash_rows,
                "hash_lanes": HASH_LANES,
                "required_successes": REQUIRED_SUCCESSES,
                "bit_codec": "gf2-bits/hex-v1",
                "response_event_kind": RESPONSE_EVENT_KIND,
                "soundness_error": "<2^-23",
            },
        }

    def handle_event(
        self,
        *,
        state: Any,
        event: ParticipantEvent,
        generated_case: GeneratedCase,
        context: ArthurContext,
    ) -> Transition:
        if not isinstance(state, ImageSizeProtocolState):
            raise TypeError("state is not an ImageSizeProtocolState")
        self._validate_task_identity(generated_case)
        circuit, hash_rows = _validate_public_instance(generated_case.public_instance)
        if state.terminal_status is not None or event.artifact_refs:
            return self._rejection(state, ImageSizeReason.MALFORMED_EVENT)

        if state.phase == "awaiting_begin":
            if (
                event.kind != BEGIN_EVENT_KIND
                or not isinstance(event.payload, Mapping)
                or set(event.payload)
            ):
                return self._rejection(state, ImageSizeReason.MALFORMED_EVENT)
            challenges, public_hashes = _make_challenges(
                circuit=circuit,
                hash_rows=hash_rows,
                generated_case=generated_case,
                context=context,
            )
            next_state = ImageSizeProtocolState(
                phase="awaiting_response",
                challenges=challenges,
                events_processed=state.events_processed + 1,
            )
            return Transition(
                new_state=next_state,
                reply=ProtocolReply(
                    kind=CHALLENGE_REPLY_KIND,
                    payload={"hashes": public_hashes},
                ),
                milestones={"completed_protocol_fraction": 0.5},
                public_state={
                    "phase": "awaiting_response",
                    "hash_lanes": HASH_LANES,
                },
            )

        if state.phase != "awaiting_response" or event.kind != RESPONSE_EVENT_KIND:
            return self._rejection(state, ImageSizeReason.MALFORMED_EVENT)
        preimages = _parse_preimages(event.payload, circuit.num_inputs)
        if preimages is None:
            return self._rejection(state, ImageSizeReason.MALFORMED_EVENT)
        successes = 0
        for preimage, challenge in zip(preimages, state.challenges, strict=True):
            if preimage is None:
                continue
            image_word = evaluate_circuit(circuit, preimage)
            if hash_word(challenge.rows, image_word) == challenge.target:
                successes += 1
        if successes < REQUIRED_SUCCESSES:
            return self._rejection(
                state,
                ImageSizeReason.INSUFFICIENT_VALID_PREIMAGES,
                successful_lanes=successes,
            )
        accepted = ImageSizeProtocolState(
            phase="terminal",
            terminal_status=TerminalStatus.ACCEPT,
            reason_code=ErrorCode.PROTOCOL_ACCEPT,
            events_processed=state.events_processed + 1,
            successful_lanes=successes,
        )
        return Transition(
            new_state=accepted,
            terminal_status=TerminalStatus.ACCEPT,
            reason_code=ErrorCode.PROTOCOL_ACCEPT,
            milestones={"completed_protocol_fraction": 1.0},
            public_state={"phase": "terminal", "successful_lanes": successes},
        )

    def terminal_metrics(self, *, state: Any) -> Mapping[str, int | float | str]:
        if not isinstance(state, ImageSizeProtocolState):
            raise TypeError("state is not an ImageSizeProtocolState")
        metrics: dict[str, int | float | str] = {
            "events_processed": state.events_processed,
            "accepted": int(state.terminal_status == TerminalStatus.ACCEPT),
            "successful_lanes": state.successful_lanes,
            "completed_protocol_fraction": self._completed_fraction(state),
        }
        if state.reason_code is not None:
            metrics["reason_code"] = state.reason_code
        return metrics

    @staticmethod
    def _validate_task_identity(generated_case: GeneratedCase) -> None:
        if generated_case.task_id != TASK_ID or generated_case.task_version != TASK_VERSION:
            raise ValueError("generated case does not belong to this task plugin")

    @staticmethod
    def _completed_fraction(state: ImageSizeProtocolState) -> float:
        successful_events = state.events_processed
        if state.terminal_status == TerminalStatus.REJECT:
            successful_events = max(0, successful_events - 1)
        return min(successful_events / 2, 1.0)

    @staticmethod
    def _rejection(
        state: ImageSizeProtocolState, reason_code: str, *, successful_lanes: int = 0
    ) -> Transition:
        rejected = ImageSizeProtocolState(
            phase="terminal",
            terminal_status=TerminalStatus.REJECT,
            reason_code=reason_code,
            events_processed=state.events_processed + 1,
            successful_lanes=successful_lanes,
        )
        return Transition(
            new_state=rejected,
            terminal_status=TerminalStatus.REJECT,
            reason_code=reason_code,
            milestones={
                "completed_protocol_fraction": ImageSizeLowerBoundProtocol._completed_fraction(
                    rejected
                )
            },
            public_state={"phase": "terminal", "successful_lanes": successful_lanes},
        )


def _participant_instance(client: ParticipantClient) -> Mapping[str, Any]:
    response = client.get_instance()
    nested = response.get("public_instance")
    return nested if isinstance(nested, Mapping) else response


def _reply_hashes(response: Mapping[str, Any]) -> list[Any]:
    raw_reply = response.get("reply")
    if isinstance(raw_reply, Mapping):
        if raw_reply.get("kind") != CHALLENGE_REPLY_KIND:
            raise RuntimeError("Arthur returned an unexpected Image-Size reply kind")
        payload = raw_reply.get("payload")
        if isinstance(payload, Mapping):
            hashes = payload.get("hashes")
            if isinstance(hashes, list) and len(hashes) == HASH_LANES:
                return hashes
    hashes = response.get("hashes")
    if isinstance(hashes, list) and len(hashes) == HASH_LANES:
        return hashes
    raise RuntimeError("Arthur response did not contain 128 affine hashes")


def _parse_public_hashes(raw_hashes: Sequence[Any], n: int, k: int) -> list[AffineChallenge]:
    result: list[AffineChallenge] = []
    if len(raw_hashes) != HASH_LANES:
        raise RuntimeError("Arthur returned the wrong number of hash lanes")
    for raw_hash in raw_hashes:
        if not isinstance(raw_hash, Mapping) or set(raw_hash) != _HASH_FIELDS:
            raise RuntimeError("Arthur returned a malformed affine hash")
        raw_rows = raw_hash.get("matrix_rows")
        if not isinstance(raw_rows, list) or len(raw_rows) != k:
            raise RuntimeError("Arthur returned an affine matrix with the wrong shape")
        try:
            rows = tuple(decode_gf2_bits(row, n) for row in raw_rows)
            target = decode_gf2_bits(raw_hash.get("target"), k)
        except ValueError as exc:
            raise RuntimeError("Arthur returned a noncanonical GF(2) vector") from exc
        result.append(AffineChallenge(rows, target))
    return result


def solve_public_hashes(
    public_instance: Mapping[str, Any], raw_hashes: Sequence[Any]
) -> list[str | None]:
    """Correctness-scaled public-only prover used by tests and virtual runs."""

    circuit, hash_rows = _validate_public_instance(public_instance)
    image = enumerate_image(circuit)
    challenges = _parse_public_hashes(raw_hashes, circuit.num_outputs, hash_rows)
    answers: list[str | None] = []
    for challenge in challenges:
        preimage = next(
            (
                candidate
                for image_word, candidate in image.items()
                if hash_word(challenge.rows, image_word) == challenge.target
            ),
            None,
        )
        answers.append(None if preimage is None else encode_gf2_bits(preimage, circuit.num_inputs))
    return answers


class HonestImageSizeAgent:
    """Reference prover using only the final public circuit and challenge."""

    agent_id = "virtual-honest"

    def run(self, *, client: ParticipantClient, workspace: Path) -> None:
        del workspace
        public_instance = _participant_instance(client)
        begin_response = client.submit_event(sequence=0, kind=BEGIN_EVENT_KIND, payload={})
        preimages = solve_public_hashes(public_instance, _reply_hashes(begin_response))
        client.submit_event(
            sequence=1,
            kind=RESPONSE_EVENT_KIND,
            payload={"preimages": preimages},
        )


class EmptyImageSizeAgent:
    """Negative control returning no bucket preimages."""

    agent_id = "virtual-empty-response"

    def run(self, *, client: ParticipantClient, workspace: Path) -> None:
        del workspace
        client.submit_event(sequence=0, kind=BEGIN_EVENT_KIND, payload={})
        client.submit_event(
            sequence=1,
            kind=RESPONSE_EVENT_KIND,
            payload={"preimages": [None] * HASH_LANES},
        )


_VIRTUAL_AGENT_LIST: Final[tuple[VirtualAgent, ...]] = (
    HonestImageSizeAgent(),
    EmptyImageSizeAgent(),
)
VIRTUAL_AGENTS: Final[Mapping[str, VirtualAgent]] = {
    agent.agent_id: agent for agent in _VIRTUAL_AGENT_LIST
}


@dataclass(frozen=True)
class ImageSizeLowerBoundTaskPlugin:
    manifest: Mapping[str, Any]
    case_parameters: Mapping[str, Mapping[str, Any]]
    generator: ImageSizeLowerBoundGenerator
    protocol: ImageSizeLowerBoundProtocol


def create_task() -> ImageSizeLowerBoundTaskPlugin:
    return ImageSizeLowerBoundTaskPlugin(
        manifest=TASK_MANIFEST,
        case_parameters=CASE_PARAMETERS,
        generator=ImageSizeLowerBoundGenerator(),
        protocol=ImageSizeLowerBoundProtocol(),
    )


__all__ = [
    "BEGIN_EVENT_KIND",
    "CASE_ID",
    "CASE_IDS",
    "CASE_PARAMETERS",
    "CHALLENGE_REPLY_KIND",
    "HASH_LANES",
    "ImageSizeLowerBoundGenerator",
    "ImageSizeLowerBoundProtocol",
    "ImageSizeLowerBoundTaskPlugin",
    "ImageSizeProtocolState",
    "ImageSizeReason",
    "REQUIRED_SUCCESSES",
    "RESPONSE_EVENT_KIND",
    "TASK_ID",
    "TASK_MANIFEST",
    "TASK_VERSION",
    "VIRTUAL_AGENTS",
    "create_task",
    "solve_public_hashes",
]
