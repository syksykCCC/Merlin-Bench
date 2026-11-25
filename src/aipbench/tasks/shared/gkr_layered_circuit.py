"""Shared primitives used by the current Merlin-Bench tasks."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final, TypeGuard

from aipbench.core.errors import ErrorCode
from aipbench.core.models import (
    GeneratedCase,
    ParticipantEvent,
    ProtocolReply,
    TerminalStatus,
    Transition,
)
from aipbench.core.protocol import ArthurContext
from aipbench.tasks.field61 import (
    CODEC_NAME,
    MODULUS,
    decode_field,
    encode_field,
    evaluate_polynomial,
)
from aipbench.tasks.shared.gkr_layered_circuit_cases.common import (
    Gate,
    ParsedCircuit,
    parse_public_instance,
    width_bits,
)

TASK_ID: Final = "t2.new_gkr_layered_circuit"

TASK_VERSION: Final = "0.1.0"

CLAIM_EVENT_KIND: Final = "gkr.claim"

POLY_EVENT_KIND: Final = "gkr.poly"

REDUCE_EVENT_KIND: Final = "gkr.reduce"

READY_REPLY_KIND: Final = "gkr.ready"

CHALLENGE_REPLY_KIND: Final = "gkr.challenge"

LINE_CHALLENGE_REPLY_KIND: Final = "gkr.line_challenge"


class GKRReason:
    """Stable participant-visible rejection reasons."""

    MALFORMED_EVENT = "GKR_MALFORMED_EVENT"
    CHECK_FAILED = "GKR_CHECK_FAILED"


def _is_integer(value: object) -> TypeGuard[int]:
    return isinstance(value, int) and not isinstance(value, bool)


def _bit(index: int, coordinate: int) -> int:
    return (index >> coordinate) & 1


def equality_basis(point: Sequence[int], index: int) -> int:
    """Evaluate ``eq(point, bits_lsb(index))``."""

    result = 1
    for coordinate, value in enumerate(point):
        result = result * (value if _bit(index, coordinate) else 1 - value) % MODULUS
    return result


def multilinear_evaluation(values: Sequence[int], point: Sequence[int]) -> int:
    if len(values) != 1 << len(point):
        raise ValueError("table width and multilinear point dimension disagree")
    return sum(value * equality_basis(point, index) for index, value in enumerate(values)) % MODULUS


def wiring_evaluation(
    gates: Sequence[Gate],
    current_point: Sequence[int],
    left_point: Sequence[int],
    right_point: Sequence[int],
) -> tuple[int, int, int]:
    """Evaluate the three sparse wiring MLEs from the public gate table."""

    a_value = b_value = c_value = 0
    for index, gate in enumerate(gates):
        weight = equality_basis(current_point, index)
        weight = weight * equality_basis(left_point, gate.left) % MODULUS
        weight = weight * equality_basis(right_point, gate.right) % MODULUS
        a_value = (a_value + weight * gate.a) % MODULUS
        b_value = (b_value + weight * gate.b) % MODULUS
        c_value = (c_value + weight * gate.c) % MODULUS
    return a_value, b_value, c_value


@dataclass(frozen=True)
class GKRProtocolState:
    phase: str = "awaiting_claim"
    layer: int = 0
    round: int = 0
    current_point: tuple[int, ...] = ()
    current_claim: int = 0
    prefix: tuple[int, ...] = ()
    left_point: tuple[int, ...] = ()
    right_point: tuple[int, ...] = ()
    terminal_status: TerminalStatus | None = None
    reason_code: str | None = None
    events_processed: int = 0
    total_events: int = 1


def _decode_field_or_none(value: object) -> int | None:
    try:
        return decode_field(value)
    except ValueError:
        return None


def _parse_claim(payload: object) -> int | None:
    if not isinstance(payload, Mapping) or set(payload) != {"value"}:
        return None
    return _decode_field_or_none(payload.get("value"))


def _parse_poly(payload: object, layer: int, round_index: int) -> tuple[int, int, int] | None:
    if not isinstance(payload, Mapping) or set(payload) != {
        "layer",
        "round",
        "coefficients",
    }:
        return None
    if payload.get("layer") != layer or payload.get("round") != round_index:
        return None
    if not _is_integer(payload.get("layer")) or not _is_integer(payload.get("round")):
        return None
    raw = payload.get("coefficients")
    if not isinstance(raw, list) or len(raw) != 3:
        return None
    decoded = tuple(_decode_field_or_none(value) for value in raw)
    if any(value is None for value in decoded):
        return None
    return decoded  # type: ignore[return-value]


def _parse_reduce(
    payload: object, layer: int, expected_coefficients: int
) -> tuple[int, int, tuple[int, ...]] | None:
    if not isinstance(payload, Mapping) or set(payload) != {
        "layer",
        "left_value",
        "right_value",
        "line_coefficients",
    }:
        return None
    if not _is_integer(payload.get("layer")) or payload.get("layer") != layer:
        return None
    left = _decode_field_or_none(payload.get("left_value"))
    right = _decode_field_or_none(payload.get("right_value"))
    raw_coefficients = payload.get("line_coefficients")
    if (
        left is None
        or right is None
        or not isinstance(raw_coefficients, list)
        or len(raw_coefficients) != expected_coefficients
    ):
        return None
    coefficients = tuple(_decode_field_or_none(value) for value in raw_coefficients)
    if any(value is None for value in coefficients):
        return None
    return left, right, coefficients  # type: ignore[return-value]


class GKRLayeredCircuitProtocol:
    task_id = TASK_ID
    task_version = TASK_VERSION
    schema_root = "tasks/tier2_interactive/new_gkr_layered_circuit/schemas"
    randomness_domain = TASK_ID

    def initialize(
        self, *, generated_case: GeneratedCase, context: ArthurContext
    ) -> GKRProtocolState:
        del context
        self._validate_identity(generated_case)
        circuit = parse_public_instance(generated_case.public_instance)
        return GKRProtocolState(total_events=circuit.barriers + 1)

    def public_protocol_description(self, *, generated_case: GeneratedCase) -> Mapping[str, Any]:
        self._validate_identity(generated_case)
        circuit = parse_public_instance(generated_case.public_instance)
        root = self.schema_root
        return {
            "api_version": "aip/1",
            "mode": "interactive",
            "public_coin": True,
            "initial_event_kinds": [CLAIM_EVENT_KIND],
            "event_schemas": {
                CLAIM_EVENT_KIND: {"schema_ref": f"{root}/claim.schema.json"},
                POLY_EVENT_KIND: {"schema_ref": f"{root}/poly.schema.json"},
                REDUCE_EVENT_KIND: {"schema_ref": f"{root}/reduce.schema.json"},
            },
            "reply_schemas": {
                READY_REPLY_KIND: {"schema_ref": f"{root}/ready.schema.json"},
                CHALLENGE_REPLY_KIND: {"schema_ref": f"{root}/challenge.schema.json"},
                LINE_CHALLENGE_REPLY_KIND: {"schema_ref": f"{root}/line_challenge.schema.json"},
            },
            "public_parameters": {
                "field_modulus_hex": "1fffffffffffffff",
                "element_codec": CODEC_NAME,
                "index_bits": "lsb_first",
                "depth": circuit.depth,
                "total_positions": circuit.total_positions,
                "total_barriers": circuit.barriers,
                "total_merlin_events": circuit.barriers + 1,
                "soundness_error_bound": "<2^-49",
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
        if not isinstance(state, GKRProtocolState):
            raise TypeError("state is not a GKRProtocolState")
        self._validate_identity(generated_case)
        circuit = parse_public_instance(generated_case.public_instance)
        if state.terminal_status is not None or event.artifact_refs:
            return self._reject(state, GKRReason.MALFORMED_EVENT)

        if state.phase == "awaiting_claim":
            if event.kind != CLAIM_EVENT_KIND:
                return self._reject(state, GKRReason.MALFORMED_EVENT)
            claim = _parse_claim(event.payload)
            if claim is None:
                return self._reject(state, GKRReason.MALFORMED_EVENT)
            first_dimension = width_bits(circuit.layer_widths[1])
            next_state = GKRProtocolState(
                phase="awaiting_reduce" if first_dimension == 0 else "awaiting_poly",
                current_claim=claim,
                events_processed=1,
                total_events=state.total_events,
            )
            return Transition(
                new_state=next_state,
                reply=ProtocolReply(READY_REPLY_KIND, {"layer": 0, "round": 0}),
                milestones={"completed_protocol_fraction": 1 / state.total_events},
                public_state=self._public_state(next_state, circuit),
            )

        if state.phase == "awaiting_poly":
            if event.kind != POLY_EVENT_KIND:
                return self._reject(state, GKRReason.MALFORMED_EVENT)
            coefficients = _parse_poly(event.payload, state.layer, state.round)
            if coefficients is None:
                return self._reject(state, GKRReason.MALFORMED_EVENT)
            endpoints = (coefficients[0] + evaluate_polynomial(coefficients, 1)) % MODULUS
            if endpoints != state.current_claim:
                return self._reject(state, GKRReason.CHECK_FAILED)
            challenge = context.random_field_element(
                tag=(
                    f"{self.randomness_domain}/{generated_case.case_id}/gkr/"
                    f"layer-{state.layer}/round-{state.round}"
                ),
                modulus=MODULUS,
            )
            prefix = (*state.prefix, challenge)
            dimension = width_bits(circuit.layer_widths[state.layer + 1])
            rounds = 2 * dimension
            next_round = state.round + 1
            next_state = GKRProtocolState(
                phase="awaiting_reduce" if next_round == rounds else "awaiting_poly",
                layer=state.layer,
                round=next_round,
                current_point=state.current_point,
                current_claim=evaluate_polynomial(coefficients, challenge),
                prefix=prefix,
                left_point=tuple(prefix[:dimension]) if next_round == rounds else (),
                right_point=tuple(prefix[dimension:]) if next_round == rounds else (),
                events_processed=state.events_processed + 1,
                total_events=state.total_events,
            )
            return Transition(
                new_state=next_state,
                reply=ProtocolReply(
                    CHALLENGE_REPLY_KIND,
                    {
                        "layer": state.layer,
                        "round": state.round,
                        "point": encode_field(challenge),
                    },
                ),
                milestones=self._milestones(next_state),
                public_state=self._public_state(next_state, circuit),
            )

        if state.phase != "awaiting_reduce" or event.kind != REDUCE_EVENT_KIND:
            return self._reject(state, GKRReason.MALFORMED_EVENT)
        dimension = width_bits(circuit.layer_widths[state.layer + 1])
        reduction = _parse_reduce(event.payload, state.layer, dimension + 1)
        if reduction is None:
            return self._reject(state, GKRReason.MALFORMED_EVENT)
        left_value, right_value, line_coefficients = reduction
        a_value, b_value, c_value = wiring_evaluation(
            circuit.layers[state.layer],
            state.current_point,
            state.left_point,
            state.right_point,
        )
        expected = (
            a_value * left_value + b_value * right_value + c_value * left_value * right_value
        ) % MODULUS
        if (
            expected != state.current_claim
            or evaluate_polynomial(line_coefficients, 0) != left_value
            or evaluate_polynomial(line_coefficients, 1) != right_value
        ):
            return self._reject(state, GKRReason.CHECK_FAILED)

        line_challenge = context.random_field_element(
            tag=(f"{self.randomness_domain}/{generated_case.case_id}/gkr/layer-{state.layer}/line"),
            modulus=MODULUS,
        )
        next_point = tuple(
            (left + line_challenge * (right - left)) % MODULUS
            for left, right in zip(state.left_point, state.right_point, strict=True)
        )
        next_claim = evaluate_polynomial(line_coefficients, line_challenge)
        reply = ProtocolReply(
            LINE_CHALLENGE_REPLY_KIND,
            {"layer": state.layer, "point": encode_field(line_challenge)},
        )
        events_processed = state.events_processed + 1
        if state.layer == circuit.depth - 1:
            input_claim = multilinear_evaluation(circuit.input_values, next_point)
            if input_claim != next_claim:
                rejected = GKRProtocolState(
                    phase="terminal",
                    layer=state.layer,
                    current_point=next_point,
                    current_claim=next_claim,
                    terminal_status=TerminalStatus.REJECT,
                    reason_code=GKRReason.CHECK_FAILED,
                    events_processed=events_processed,
                    total_events=state.total_events,
                )
                return Transition(
                    new_state=rejected,
                    reply=reply,
                    terminal_status=TerminalStatus.REJECT,
                    reason_code=GKRReason.CHECK_FAILED,
                    milestones={"completed_protocol_fraction": self._completed_fraction(rejected)},
                    public_state=self._public_state(rejected, circuit),
                )
            accepted = GKRProtocolState(
                phase="terminal",
                layer=state.layer,
                current_point=next_point,
                current_claim=next_claim,
                terminal_status=TerminalStatus.ACCEPT,
                reason_code=ErrorCode.PROTOCOL_ACCEPT,
                events_processed=events_processed,
                total_events=state.total_events,
            )
            return Transition(
                new_state=accepted,
                reply=reply,
                terminal_status=TerminalStatus.ACCEPT,
                reason_code=ErrorCode.PROTOCOL_ACCEPT,
                milestones={"completed_protocol_fraction": 1.0},
                public_state=self._public_state(accepted, circuit),
            )

        next_layer = state.layer + 1
        next_dimension = width_bits(circuit.layer_widths[next_layer + 1])
        next_state = GKRProtocolState(
            phase="awaiting_reduce" if next_dimension == 0 else "awaiting_poly",
            layer=next_layer,
            current_point=next_point,
            current_claim=next_claim,
            events_processed=events_processed,
            total_events=state.total_events,
        )
        return Transition(
            new_state=next_state,
            reply=reply,
            milestones=self._milestones(next_state),
            public_state=self._public_state(next_state, circuit),
        )

    def terminal_metrics(self, *, state: Any) -> Mapping[str, int | float | str]:
        if not isinstance(state, GKRProtocolState):
            raise TypeError("state is not a GKRProtocolState")
        metrics: dict[str, int | float | str] = {
            "events_processed": state.events_processed,
            "accepted": int(state.terminal_status == TerminalStatus.ACCEPT),
            "completed_protocol_fraction": self._completed_fraction(state),
        }
        if state.reason_code is not None:
            metrics["reason_code"] = state.reason_code
        return metrics

    def _validate_identity(self, generated_case: GeneratedCase) -> None:
        if (
            generated_case.task_id != self.task_id
            or generated_case.task_version != self.task_version
        ):
            raise ValueError("generated case does not belong to the GKR task plugin")

    @staticmethod
    def _milestones(state: GKRProtocolState) -> Mapping[str, float]:
        return {"completed_protocol_fraction": GKRLayeredCircuitProtocol._completed_fraction(state)}

    @staticmethod
    def _completed_fraction(state: GKRProtocolState) -> float:
        successful_events = state.events_processed
        if state.terminal_status == TerminalStatus.REJECT:
            successful_events = max(0, successful_events - 1)
        return min(successful_events / state.total_events, 1.0)

    @staticmethod
    def _public_state(state: GKRProtocolState, circuit: ParsedCircuit) -> Mapping[str, Any]:
        successful_events = state.events_processed
        if state.terminal_status == TerminalStatus.REJECT:
            successful_events = max(0, successful_events - 1)
        completed_barriers = max(0, successful_events - 1)
        result: dict[str, Any] = {
            "phase": state.phase,
            "layer": state.layer,
            "completed_barriers": completed_barriers,
            "total_barriers": circuit.barriers,
        }
        if state.phase == "awaiting_poly":
            result["round"] = state.round
        return result

    @staticmethod
    def _reject(state: GKRProtocolState, reason: str) -> Transition:
        rejected = GKRProtocolState(
            phase="terminal",
            layer=state.layer,
            round=state.round,
            terminal_status=TerminalStatus.REJECT,
            reason_code=reason,
            events_processed=state.events_processed + 1,
            total_events=state.total_events,
        )
        return Transition(
            new_state=rejected,
            terminal_status=TerminalStatus.REJECT,
            reason_code=reason,
            milestones={
                "completed_protocol_fraction": GKRLayeredCircuitProtocol._completed_fraction(
                    rejected
                )
            },
            public_state={"phase": "terminal"},
        )
