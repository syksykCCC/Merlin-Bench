"""Shared primitives used by the current Merlin-Bench tasks."""

from __future__ import annotations

from collections.abc import Mapping
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
from aipbench.tasks.field61 import MODULUS, decode_field, encode_field, evaluate_polynomial
from aipbench.tasks.shared.boolean_hypercube_sumcheck_cases.common import (
    evaluate_product,
    parse_public_instance,
)

TASK_ID: Final = "t2.new_boolean_hypercube_sumcheck"

TASK_VERSION: Final = "0.1.0"

CLAIM_EVENT_KIND: Final = "sumcheck.claim"

READY_REPLY_KIND: Final = "sumcheck.ready"

POLY_EVENT_KIND: Final = "sumcheck.poly"

CHALLENGE_REPLY_KIND: Final = "sumcheck.challenge"

DEGREE_BOUND: Final = 5

COEFFICIENT_COUNT: Final = DEGREE_BOUND + 1

_CLAIM_FIELDS: Final = frozenset({"variable_order", "claimed_sum"})

_POLY_FIELDS: Final = frozenset({"round_index", "coefficients"})


class SumCheckReason:
    MALFORMED_EVENT = "SUMCHECK_MALFORMED_EVENT"
    ANCHOR_FAILED = "SUMCHECK_ANCHOR_FAILED"
    FINAL_CHECK_FAILED = "SUMCHECK_FINAL_CHECK_FAILED"


def _is_integer(value: object) -> TypeGuard[int]:
    return isinstance(value, int) and not isinstance(value, bool)


@dataclass(frozen=True)
class SumCheckProtocolState:
    phase: str = "awaiting_claim"
    variable_order: tuple[int, ...] = ()
    prefix_points: tuple[int, ...] = ()
    current_claim: int = 0
    round_index: int = 0
    terminal_status: TerminalStatus | None = None
    reason_code: str | None = None
    events_processed: int = 0


def _parse_claim(payload: object, num_variables: int) -> tuple[tuple[int, ...], int] | None:
    if not isinstance(payload, Mapping) or set(payload) != _CLAIM_FIELDS:
        return None
    raw_order = payload.get("variable_order")
    if not isinstance(raw_order, list) or len(raw_order) != num_variables:
        return None
    if not all(_is_integer(variable) for variable in raw_order):
        return None
    order = tuple(raw_order)
    if sorted(order) != list(range(num_variables)):
        return None
    try:
        claimed_sum = decode_field(payload.get("claimed_sum"))
    except ValueError:
        return None
    return order, claimed_sum


def _parse_polynomial(payload: object, expected_round: int) -> tuple[int, ...] | None:
    if not isinstance(payload, Mapping) or set(payload) != _POLY_FIELDS:
        return None
    raw_round = payload.get("round_index")
    if not _is_integer(raw_round) or raw_round != expected_round:
        return None
    raw_coefficients = payload.get("coefficients")
    if not isinstance(raw_coefficients, list) or len(raw_coefficients) != COEFFICIENT_COUNT:
        return None
    try:
        return tuple(decode_field(value) for value in raw_coefficients)
    except ValueError:
        return None


class BooleanHypercubeSumCheckProtocol:
    """One common public-coin Sum-Check state machine for all seven cases."""

    task_id = TASK_ID
    task_version = TASK_VERSION
    schema_root = "tasks/tier2_interactive/new_boolean_hypercube_sumcheck/schemas"
    randomness_domain = TASK_ID

    def initialize(
        self, *, generated_case: GeneratedCase, context: ArthurContext
    ) -> SumCheckProtocolState:
        del context
        self._validate_task_identity(generated_case)
        parse_public_instance(generated_case.public_instance)
        return SumCheckProtocolState()

    def public_protocol_description(self, *, generated_case: GeneratedCase) -> Mapping[str, Any]:
        self._validate_task_identity(generated_case)
        model = parse_public_instance(generated_case.public_instance)
        return {
            "api_version": "aip/1",
            "mode": "interactive",
            "public_coin": True,
            "initial_event_kinds": [CLAIM_EVENT_KIND],
            "event_schemas": {
                CLAIM_EVENT_KIND: {"schema_ref": f"{self.schema_root}/claim.schema.json"},
                POLY_EVENT_KIND: {"schema_ref": f"{self.schema_root}/poly.schema.json"},
            },
            "reply_schemas": {
                READY_REPLY_KIND: {"schema_ref": f"{self.schema_root}/ready.schema.json"},
                CHALLENGE_REPLY_KIND: {"schema_ref": f"{self.schema_root}/challenge.schema.json"},
            },
            "public_parameters": {
                "num_rounds": model.num_variables,
                "degree_bound": DEGREE_BOUND,
                "field_modulus": "1fffffffffffffff",
                "field_codec": "field61/hex-v1",
                "poly_event_kind": POLY_EVENT_KIND,
                "soundness_error": "5m/(2^61-1)",
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
        if not isinstance(state, SumCheckProtocolState):
            raise TypeError("state is not a SumCheckProtocolState")
        self._validate_task_identity(generated_case)
        model = parse_public_instance(generated_case.public_instance)
        if state.terminal_status is not None or event.artifact_refs:
            return self._rejection(state, SumCheckReason.MALFORMED_EVENT)

        if state.phase == "awaiting_claim":
            if event.kind != CLAIM_EVENT_KIND:
                return self._rejection(state, SumCheckReason.MALFORMED_EVENT)
            parsed = _parse_claim(event.payload, model.num_variables)
            if parsed is None:
                return self._rejection(state, SumCheckReason.MALFORMED_EVENT)
            order, claimed_sum = parsed
            next_state = SumCheckProtocolState(
                phase="awaiting_poly",
                variable_order=order,
                current_claim=claimed_sum,
                events_processed=state.events_processed + 1,
            )
            return Transition(
                new_state=next_state,
                reply=ProtocolReply(
                    kind=READY_REPLY_KIND,
                    payload={"num_rounds": model.num_variables, "degree_bound": DEGREE_BOUND},
                ),
                milestones={"completed_protocol_fraction": 1 / (model.num_variables + 1)},
                public_state={
                    "phase": "awaiting_poly",
                    "rounds_completed": 0,
                    "num_rounds": model.num_variables,
                },
            )

        if state.phase != "awaiting_poly" or event.kind != POLY_EVENT_KIND:
            return self._rejection(state, SumCheckReason.MALFORMED_EVENT)
        coefficients = _parse_polynomial(event.payload, state.round_index)
        if coefficients is None:
            return self._rejection(state, SumCheckReason.MALFORMED_EVENT)
        if (coefficients[0] + sum(coefficients)) % MODULUS != state.current_claim:
            return self._rejection(state, SumCheckReason.ANCHOR_FAILED)

        point = context.random_field_element(
            tag=(
                f"{self.randomness_domain}/{generated_case.case_id}/sumcheck/"
                f"round-{state.round_index}/challenge"
            ),
            modulus=MODULUS,
        )
        prefix_points = (*state.prefix_points, point)
        next_claim = evaluate_polynomial(coefficients, point)
        completed_rounds = state.round_index + 1
        challenge = ProtocolReply(
            kind=CHALLENGE_REPLY_KIND,
            payload={"round_index": state.round_index, "point": encode_field(point)},
        )
        events_processed = state.events_processed + 1
        if completed_rounds < model.num_variables:
            next_state = SumCheckProtocolState(
                phase="awaiting_poly",
                variable_order=state.variable_order,
                prefix_points=prefix_points,
                current_claim=next_claim,
                round_index=completed_rounds,
                events_processed=events_processed,
            )
            return Transition(
                new_state=next_state,
                reply=challenge,
                milestones={
                    "completed_protocol_fraction": events_processed / (model.num_variables + 1)
                },
                public_state={
                    "phase": "awaiting_poly",
                    "rounds_completed": completed_rounds,
                    "num_rounds": model.num_variables,
                },
            )

        public_point = [0] * model.num_variables
        for index, variable in enumerate(state.variable_order):
            public_point[variable] = prefix_points[index]
        expected = evaluate_product(model, public_point)
        if next_claim != expected:
            return self._rejection(
                state,
                SumCheckReason.FINAL_CHECK_FAILED,
                reply=challenge,
                events_processed=events_processed,
                prefix_points=prefix_points,
                current_claim=next_claim,
                round_index=completed_rounds,
            )
        accepted = SumCheckProtocolState(
            phase="terminal",
            variable_order=state.variable_order,
            prefix_points=prefix_points,
            current_claim=next_claim,
            round_index=completed_rounds,
            terminal_status=TerminalStatus.ACCEPT,
            reason_code=ErrorCode.PROTOCOL_ACCEPT,
            events_processed=events_processed,
        )
        return Transition(
            new_state=accepted,
            reply=challenge,
            terminal_status=TerminalStatus.ACCEPT,
            reason_code=ErrorCode.PROTOCOL_ACCEPT,
            milestones={"completed_protocol_fraction": 1.0},
            public_state={
                "phase": "terminal",
                "rounds_completed": model.num_variables,
                "num_rounds": model.num_variables,
            },
        )

    def terminal_metrics(self, *, state: Any) -> Mapping[str, int | float | str]:
        if not isinstance(state, SumCheckProtocolState):
            raise TypeError("state is not a SumCheckProtocolState")
        metrics: dict[str, int | float | str] = {
            "events_processed": state.events_processed,
            "rounds_completed": state.round_index,
            "accepted": int(state.terminal_status == TerminalStatus.ACCEPT),
            "completed_protocol_fraction": self._completed_fraction(state),
        }
        if state.reason_code is not None:
            metrics["reason_code"] = state.reason_code
        return metrics

    def _validate_task_identity(self, generated_case: GeneratedCase) -> None:
        if (
            generated_case.task_id != self.task_id
            or generated_case.task_version != self.task_version
        ):
            raise ValueError("generated case does not belong to this task plugin")

    @staticmethod
    def _completed_fraction(state: SumCheckProtocolState) -> float:
        if not state.variable_order:
            return 0.0
        successful_events = state.events_processed
        if state.terminal_status == TerminalStatus.REJECT:
            successful_events = max(0, successful_events - 1)
        return min(successful_events / (len(state.variable_order) + 1), 1.0)

    @staticmethod
    def _rejection(
        state: SumCheckProtocolState,
        reason_code: str,
        *,
        reply: ProtocolReply | None = None,
        events_processed: int | None = None,
        prefix_points: tuple[int, ...] | None = None,
        current_claim: int | None = None,
        round_index: int | None = None,
    ) -> Transition:
        count = state.events_processed + 1 if events_processed is None else events_processed
        rejected = SumCheckProtocolState(
            phase="terminal",
            variable_order=state.variable_order,
            prefix_points=state.prefix_points if prefix_points is None else prefix_points,
            current_claim=state.current_claim if current_claim is None else current_claim,
            round_index=state.round_index if round_index is None else round_index,
            terminal_status=TerminalStatus.REJECT,
            reason_code=reason_code,
            events_processed=count,
        )
        return Transition(
            new_state=rejected,
            reply=reply,
            terminal_status=TerminalStatus.REJECT,
            reason_code=reason_code,
            milestones={
                # ``count`` includes the event that caused rejection for diagnostics,
                # while partial progress counts only successfully crossed barriers.
                "completed_protocol_fraction": (
                    BooleanHypercubeSumCheckProtocol._completed_fraction(rejected)
                )
            },
            public_state={"phase": "terminal"},
        )
