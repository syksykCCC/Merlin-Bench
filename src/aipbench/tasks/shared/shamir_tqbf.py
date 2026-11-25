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

TASK_ID: Final = "t2.new_shamir_tqbf"

TASK_VERSION: Final = "0.1.0"

CLAIM_EVENT_KIND: Final = "tqbf.claim"

POLYNOMIAL_EVENT_KIND: Final = "tqbf.polynomial"

ROUND_REPLY_KIND: Final = "tqbf.round"

CHALLENGE_REPLY_KIND: Final = "tqbf.challenge"

MAX_VARIABLES: Final = 8

MAX_GATES: Final = 256

MAX_ROUND_DEGREE: Final = 64

MAX_COEFFICIENT_CELLS: Final = 4096


class TQBFReason:
    MALFORMED_EVENT = "TQBF_MALFORMED_EVENT"
    CLAIM_NOT_TRUE = "TQBF_CLAIM_NOT_TRUE"
    ANCHOR_FAILED = "TQBF_ANCHOR_FAILED"
    FINAL_ORACLE_MISMATCH = "TQBF_FINAL_ORACLE_MISMATCH"


def _is_integer(value: object) -> TypeGuard[int]:
    return isinstance(value, int) and not isinstance(value, bool)


def _syntactic_output_degrees(circuit: ParsedTQBFCircuit) -> tuple[int, ...]:
    """Compute a public syntactic individual-degree envelope without expansion."""

    zero = (0,) * circuit.num_inputs
    wires: list[tuple[int, ...]] = [
        tuple(int(index == variable) for index in range(circuit.num_inputs))
        for variable in range(circuit.num_inputs)
    ]

    def add_degrees(left: Sequence[int], right: Sequence[int]) -> tuple[int, ...]:
        return tuple(a + b for a, b in zip(left, right, strict=True))

    def max_degrees(*values: Sequence[int]) -> tuple[int, ...]:
        return tuple(max(items) for items in zip(*values, strict=True))

    for gate in circuit.gates:
        op = gate["op"]
        if op == "const":
            degree = zero
        elif op == "not":
            degree = wires[int(gate["input"])]
        elif op in ("and", "or", "xor"):
            left = wires[int(gate["left"])]
            right = wires[int(gate["right"])]
            degree = add_degrees(left, right)
        else:
            condition = wires[int(gate["condition"])]
            zero_branch = wires[int(gate["zero"])]
            one_branch = wires[int(gate["one"])]
            degree = max_degrees(
                zero_branch,
                add_degrees(condition, zero_branch),
                add_degrees(condition, one_branch),
            )
        wires.append(degree)
    return wires[circuit.output]


@dataclass(frozen=True)
class ParsedTQBFCircuit:
    num_inputs: int
    quantifiers: tuple[str, ...]
    gates: tuple[Mapping[str, Any], ...]
    output: int


def _parse_public_instance(
    public_instance: Mapping[str, Any],
    *,
    max_variables: int = MAX_VARIABLES,
    max_gates: int = MAX_GATES,
) -> ParsedTQBFCircuit:
    if set(public_instance) != {"format_version", "field_codec", "quantifiers", "circuit"}:
        raise ValueError("malformed TQBF public instance")
    if public_instance.get("format_version") != "aip-tqbf/1":
        raise ValueError("unsupported TQBF instance format")
    if public_instance.get("field_codec") != CODEC_NAME:
        raise ValueError("unsupported TQBF field codec")
    raw_quantifiers = public_instance.get("quantifiers")
    if not isinstance(raw_quantifiers, list) or not 1 <= len(raw_quantifiers) <= max_variables:
        raise ValueError("invalid TQBF quantifier prefix")
    if not all(value in ("forall", "exists") for value in raw_quantifiers):
        raise ValueError("invalid TQBF quantifier")
    raw_circuit = public_instance.get("circuit")
    if not isinstance(raw_circuit, Mapping) or set(raw_circuit) != {
        "num_inputs",
        "gates",
        "output",
    }:
        raise ValueError("malformed TQBF circuit")
    num_inputs = raw_circuit.get("num_inputs")
    raw_gates = raw_circuit.get("gates")
    output = raw_circuit.get("output")
    if num_inputs != len(raw_quantifiers) or not _is_integer(num_inputs):
        raise ValueError("TQBF input count does not match the quantifier prefix")
    if not isinstance(raw_gates, list) or not raw_gates or len(raw_gates) > max_gates:
        raise ValueError("invalid TQBF gate table")
    gates: list[Mapping[str, Any]] = []
    for gate_index, raw_gate in enumerate(raw_gates):
        if not isinstance(raw_gate, Mapping):
            raise ValueError("TQBF gate must be an object")
        gate = dict(raw_gate)
        op = gate.get("op")
        current_wire = num_inputs + gate_index
        if op == "const":
            if (
                set(gate) != {"op", "value"}
                or not _is_integer(gate.get("value"))
                or gate["value"] not in (0, 1)
            ):
                raise ValueError("malformed TQBF const gate")
        elif op == "not":
            if (
                set(gate) != {"op", "input"}
                or not _is_integer(gate.get("input"))
                or not 0 <= gate["input"] < current_wire
            ):
                raise ValueError("malformed TQBF not gate")
        elif op in ("and", "or", "xor"):
            if set(gate) != {"op", "left", "right"}:
                raise ValueError("malformed TQBF binary gate")
            if not all(
                _is_integer(gate.get(field)) and 0 <= gate[field] < current_wire
                for field in ("left", "right")
            ):
                raise ValueError("TQBF binary gate is not topological")
        elif op == "ite":
            if set(gate) != {"op", "condition", "zero", "one"}:
                raise ValueError("malformed TQBF ITE gate")
            if not all(
                _is_integer(gate.get(field)) and 0 <= gate[field] < current_wire
                for field in ("condition", "zero", "one")
            ):
                raise ValueError("TQBF ITE gate is not topological")
        else:
            raise ValueError("unsupported TQBF gate operation")
        gates.append(gate)
    if not _is_integer(output) or not 0 <= output < num_inputs + len(gates):
        raise ValueError("invalid TQBF output wire")
    return ParsedTQBFCircuit(
        num_inputs=num_inputs,
        quantifiers=tuple(str(value) for value in raw_quantifiers),
        gates=tuple(gates),
        output=output,
    )


def _evaluate_circuit(circuit: ParsedTQBFCircuit, assignment: Sequence[int]) -> int:
    if len(assignment) != circuit.num_inputs:
        raise ValueError("wrong TQBF assignment length")
    wires = [value % MODULUS for value in assignment]
    for gate in circuit.gates:
        op = gate["op"]
        if op == "const":
            value = int(gate["value"])
        elif op == "not":
            value = 1 - wires[int(gate["input"])]
        elif op == "and":
            value = wires[int(gate["left"])] * wires[int(gate["right"])]
        elif op == "or":
            left, right = wires[int(gate["left"])], wires[int(gate["right"])]
            value = left + right - left * right
        elif op == "xor":
            left, right = wires[int(gate["left"])], wires[int(gate["right"])]
            value = left + right - 2 * left * right
        else:
            condition = wires[int(gate["condition"])]
            zero = wires[int(gate["zero"])]
            one = wires[int(gate["one"])]
            value = (1 - condition) * zero + condition * one
        wires.append(value % MODULUS)
    return wires[circuit.output]


@dataclass(frozen=True)
class TQBFRoundPlan:
    round_index: int
    stage: int
    operator: str
    variable: int
    degree_bound: int


def _build_round_plan(circuit: ParsedTQBFCircuit) -> tuple[TQBFRoundPlan, ...]:
    """Build the verifier's metadata-only public degree schedule.

    This function deliberately does not construct any target polynomial.  For
    stages below the circuit stage, the preceding multilinearization gives the
    canonical bounds 2 (reduction) and 1 (quantifier).  Only the final stage
    depends on the public circuit's syntactic individual-degree envelope.
    """

    output_degrees = _syntactic_output_degrees(circuit)
    num_variables = circuit.num_inputs
    plans: list[TQBFRoundPlan] = []
    for stage in range(1, num_variables + 1):
        for variable in range(stage - 1):
            degree_bound = 2 if stage < num_variables else 2 * output_degrees[variable]
            plans.append(
                TQBFRoundPlan(
                    round_index=len(plans),
                    stage=stage,
                    operator="reduce",
                    variable=variable,
                    degree_bound=degree_bound,
                )
            )
        variable = stage - 1
        degree_bound = 1 if stage < num_variables else output_degrees[variable]
        plans.append(
            TQBFRoundPlan(
                round_index=len(plans),
                stage=stage,
                operator=circuit.quantifiers[variable],
                variable=variable,
                degree_bound=degree_bound,
            )
        )
    if max((plan.degree_bound for plan in plans), default=0) > MAX_ROUND_DEGREE:
        raise ValueError("TQBF round degree exceeds the supported envelope")
    if sum(plan.degree_bound + 1 for plan in plans) > MAX_COEFFICIENT_CELLS:
        raise ValueError("TQBF coefficient-cell count exceeds the supported envelope")
    if sum(plan.degree_bound for plan in plans) >= MODULUS // (1 << 24):
        raise ValueError("TQBF round-degree sum exceeds the soundness envelope")
    return tuple(plans)


def _round_payload(plan: TQBFRoundPlan, *, total_rounds: int) -> Mapping[str, Any]:
    return {
        "round_index": plan.round_index,
        "stage": plan.stage,
        "operator": plan.operator,
        "variable": plan.variable,
        "degree_bound": plan.degree_bound,
        "remaining_barriers": total_rounds - plan.round_index,
    }


@dataclass(frozen=True)
class TQBFProtocolState:
    phase: str = "awaiting_claim"
    round_index: int = 0
    claim: int = 0
    assignment: tuple[int, ...] = ()
    events_processed: int = 0
    terminal_status: TerminalStatus | None = None
    reason_code: str | None = None


def _parse_polynomial_payload(
    payload: object, *, expected_round: int, degree_bound: int
) -> tuple[int, ...] | None:
    if not isinstance(payload, Mapping) or set(payload) != {"round_index", "coefficients"}:
        return None
    round_index = payload.get("round_index")
    raw_coefficients = payload.get("coefficients")
    if not _is_integer(round_index) or round_index != expected_round:
        return None
    if not isinstance(raw_coefficients, list) or len(raw_coefficients) != degree_bound + 1:
        return None
    try:
        return tuple(decode_field(value) for value in raw_coefficients)
    except ValueError:
        return None


class ShamirTQBFProtocol:
    task_id = TASK_ID
    task_version = TASK_VERSION
    schema_root = "tasks/tier2_interactive/new_shamir_tqbf/schemas"
    randomness_domain = TASK_ID
    max_variables = MAX_VARIABLES
    max_gates = MAX_GATES

    def _parse_instance(self, public_instance: Mapping[str, Any]) -> ParsedTQBFCircuit:
        return _parse_public_instance(
            public_instance,
            max_variables=self.max_variables,
            max_gates=self.max_gates,
        )

    def initialize(
        self, *, generated_case: GeneratedCase, context: ArthurContext
    ) -> TQBFProtocolState:
        del context
        self._validate_identity(generated_case)
        circuit = self._parse_instance(generated_case.public_instance)
        _build_round_plan(circuit)
        return TQBFProtocolState(assignment=(0,) * circuit.num_inputs)

    def public_protocol_description(self, *, generated_case: GeneratedCase) -> Mapping[str, Any]:
        self._validate_identity(generated_case)
        circuit = self._parse_instance(generated_case.public_instance)
        plans = _build_round_plan(circuit)
        return {
            "api_version": "aip/1",
            "mode": "interactive",
            "public_coin": True,
            "initial_event_kinds": [CLAIM_EVENT_KIND],
            "event_schemas": {
                CLAIM_EVENT_KIND: {"schema_ref": f"{self.schema_root}/claim.schema.json"},
                POLYNOMIAL_EVENT_KIND: {"schema_ref": f"{self.schema_root}/polynomial.schema.json"},
            },
            "reply_schemas": {
                ROUND_REPLY_KIND: {"schema_ref": f"{self.schema_root}/round.schema.json"},
                CHALLENGE_REPLY_KIND: {"schema_ref": f"{self.schema_root}/challenge.schema.json"},
            },
            "public_parameters": {
                "field_prime_decimal": str(MODULUS),
                "field_codec": CODEC_NAME,
                "num_variables": circuit.num_inputs,
                "num_rounds": len(plans),
                "max_events": len(plans) + 1,
                "polynomial_event_kind": POLYNOMIAL_EVENT_KIND,
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
        if not isinstance(state, TQBFProtocolState):
            raise TypeError("state is not a TQBFProtocolState")
        self._validate_identity(generated_case)
        circuit = self._parse_instance(generated_case.public_instance)
        plans = _build_round_plan(circuit)
        if state.terminal_status is not None or event.artifact_refs:
            return self._reject(state, TQBFReason.MALFORMED_EVENT, len(plans))

        if state.phase == "awaiting_claim":
            if (
                event.kind != CLAIM_EVENT_KIND
                or not isinstance(event.payload, Mapping)
                or set(event.payload) != {"value"}
            ):
                return self._reject(state, TQBFReason.MALFORMED_EVENT, len(plans))
            try:
                claim = decode_field(event.payload.get("value"))
            except ValueError:
                return self._reject(state, TQBFReason.MALFORMED_EVENT, len(plans))
            if claim != 1:
                return self._reject(state, TQBFReason.CLAIM_NOT_TRUE, len(plans))
            next_state = TQBFProtocolState(
                phase="awaiting_polynomial",
                claim=claim,
                assignment=state.assignment,
                events_processed=state.events_processed + 1,
            )
            return Transition(
                new_state=next_state,
                reply=ProtocolReply(
                    kind=ROUND_REPLY_KIND,
                    payload={"round": _round_payload(plans[0], total_rounds=len(plans))},
                ),
                milestones={"completed_protocol_fraction": 1 / (len(plans) + 1)},
                public_state={"phase": "awaiting_polynomial", "round_index": 0},
            )

        if (
            state.phase != "awaiting_polynomial"
            or state.round_index >= len(plans)
            or event.kind != POLYNOMIAL_EVENT_KIND
        ):
            return self._reject(state, TQBFReason.MALFORMED_EVENT, len(plans))
        plan = plans[state.round_index]
        coefficients = _parse_polynomial_payload(
            event.payload,
            expected_round=state.round_index,
            degree_bound=plan.degree_bound,
        )
        if coefficients is None:
            return self._reject(state, TQBFReason.MALFORMED_EVENT, len(plans))
        at_zero = coefficients[0]
        at_one = sum(coefficients) % MODULUS
        if plan.operator == "reduce":
            point = state.assignment[plan.variable]
            anchor = ((1 - point) * at_zero + point * at_one) % MODULUS
        elif plan.operator == "forall":
            anchor = at_zero * at_one % MODULUS
        else:
            anchor = (at_zero + at_one - at_zero * at_one) % MODULUS
        if anchor != state.claim:
            return self._reject(state, TQBFReason.ANCHOR_FAILED, len(plans))

        challenge = context.random_field_element(
            tag=(f"{self.randomness_domain}/{generated_case.case_id}/round-{state.round_index}"),
            modulus=MODULUS,
        )
        assignment = list(state.assignment)
        assignment[plan.variable] = challenge
        next_claim = evaluate_polynomial(coefficients, challenge)
        next_round = state.round_index + 1
        events_processed = state.events_processed + 1
        if next_round == len(plans):
            oracle = _evaluate_circuit(circuit, assignment)
            if next_claim != oracle:
                return self._reject(
                    TQBFProtocolState(
                        phase=state.phase,
                        round_index=next_round,
                        claim=next_claim,
                        assignment=tuple(assignment),
                        events_processed=events_processed,
                    ),
                    TQBFReason.FINAL_ORACLE_MISMATCH,
                    len(plans),
                    event_already_counted=True,
                )
            accepted = TQBFProtocolState(
                phase="terminal",
                round_index=next_round,
                claim=next_claim,
                assignment=tuple(assignment),
                events_processed=events_processed,
                terminal_status=TerminalStatus.ACCEPT,
                reason_code=ErrorCode.PROTOCOL_ACCEPT,
            )
            return Transition(
                new_state=accepted,
                terminal_status=TerminalStatus.ACCEPT,
                reason_code=ErrorCode.PROTOCOL_ACCEPT,
                milestones={"completed_protocol_fraction": 1.0},
                public_state={"phase": "terminal", "rounds_completed": len(plans)},
            )

        next_state = TQBFProtocolState(
            phase="awaiting_polynomial",
            round_index=next_round,
            claim=next_claim,
            assignment=tuple(assignment),
            events_processed=events_processed,
        )
        return Transition(
            new_state=next_state,
            reply=ProtocolReply(
                kind=CHALLENGE_REPLY_KIND,
                payload={
                    "round_index": plan.round_index,
                    "point": encode_field(challenge),
                    "next_round": _round_payload(plans[next_round], total_rounds=len(plans)),
                },
            ),
            milestones={"completed_protocol_fraction": events_processed / (len(plans) + 1)},
            public_state={"phase": "awaiting_polynomial", "round_index": next_round},
        )

    def terminal_metrics(self, *, state: Any) -> Mapping[str, int | float | str]:
        if not isinstance(state, TQBFProtocolState):
            raise TypeError("state is not a TQBFProtocolState")
        num_variables = len(state.assignment)
        total_rounds = num_variables * (num_variables + 1) // 2
        metrics: dict[str, int | float | str] = {
            "events_processed": state.events_processed,
            "rounds_completed": state.round_index,
            "accepted": int(state.terminal_status == TerminalStatus.ACCEPT),
            "completed_protocol_fraction": self._completed_fraction(
                state, total_rounds=total_rounds
            ),
        }
        if state.reason_code is not None:
            metrics["reason_code"] = state.reason_code
        return metrics

    def _validate_identity(self, generated_case: GeneratedCase) -> None:
        if (
            generated_case.task_id != self.task_id
            or generated_case.task_version != self.task_version
        ):
            raise ValueError("generated case does not belong to Shamir-TQBF")

    @staticmethod
    def _completed_fraction(state: TQBFProtocolState, *, total_rounds: int) -> float:
        successful_events = state.events_processed
        if state.terminal_status == TerminalStatus.REJECT:
            successful_events = max(0, successful_events - 1)
        return min(successful_events / (total_rounds + 1), 1.0)

    @staticmethod
    def _reject(
        state: TQBFProtocolState,
        reason: str,
        total_rounds: int,
        *,
        event_already_counted: bool = False,
    ) -> Transition:
        events_processed = state.events_processed + (0 if event_already_counted else 1)
        rejected = TQBFProtocolState(
            phase="terminal",
            round_index=state.round_index,
            claim=state.claim,
            assignment=state.assignment,
            events_processed=events_processed,
            terminal_status=TerminalStatus.REJECT,
            reason_code=reason,
        )
        return Transition(
            new_state=rejected,
            terminal_status=TerminalStatus.REJECT,
            reason_code=reason,
            milestones={
                "completed_protocol_fraction": ShamirTQBFProtocol._completed_fraction(
                    rejected, total_rounds=total_rounds
                )
            },
            public_state={"phase": "terminal", "rounds_completed": state.round_index},
        )
