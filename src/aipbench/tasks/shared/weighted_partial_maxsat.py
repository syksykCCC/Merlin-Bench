"""Shared primitives used by the current Merlin-Bench tasks."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from aipbench.core.errors import ErrorCode
from aipbench.core.models import GeneratedCase, ParticipantEvent, TerminalStatus, Transition
from aipbench.core.protocol import ArthurContext, ParticipantClient, VirtualAgent

TASK_ID: Final = "t1.new_weighted_partial_maxsat"

TASK_VERSION: Final = "0.2.0"

ASSIGNMENT_EVENT_KIND: Final = "maxsat.assignment"

MAX_SAFE_INTEGER: Final = (1 << 53) - 1

_INSTANCE_FIELDS: Final = frozenset(
    {"format_version", "num_variables", "hard_clauses", "soft_clauses", "threshold"}
)

_HARD_CLAUSE_FIELDS: Final = frozenset({"clause_id", "literals"})

_SOFT_CLAUSE_FIELDS: Final = frozenset({"clause_id", "literals", "weight"})

_ASSIGNMENT_FIELDS: Final = frozenset({"assignment"})


class MaxSatReason:
    """Stable participant-visible rejection codes."""

    ASSIGNMENT_LENGTH_MISMATCH = "MAXSAT_ASSIGNMENT_LENGTH_MISMATCH"
    ASSIGNMENT_VALUE_INVALID = "MAXSAT_ASSIGNMENT_VALUE_INVALID"
    HARD_CLAUSE_UNSATISFIED = "MAXSAT_HARD_CLAUSE_UNSATISFIED"
    COST_EXCEEDS_THRESHOLD = "MAXSAT_COST_EXCEEDS_THRESHOLD"


@dataclass(frozen=True)
class MaxSatProtocolState:
    phase: str = "awaiting_assignment"
    terminal_status: TerminalStatus | None = None
    reason_code: str | None = None
    soft_cost: int | None = None
    events_processed: int = 0


@dataclass(frozen=True)
class _Clause:
    clause_id: int
    literals: tuple[int, ...]
    weight: int | None = None


@dataclass(frozen=True)
class _Formula:
    num_variables: int
    hard_clauses: tuple[_Clause, ...]
    soft_clauses: tuple[_Clause, ...]
    threshold: int


class _AssignmentRejected(Exception):
    def __init__(self, reason_code: str, *, soft_cost: int | None = None) -> None:
        super().__init__(reason_code)
        self.reason_code = reason_code
        self.soft_cost = soft_cost


def _is_integer(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _parse_clause(
    value: object,
    *,
    num_variables: int,
    soft: bool,
) -> _Clause:
    expected_fields = _SOFT_CLAUSE_FIELDS if soft else _HARD_CLAUSE_FIELDS
    if not isinstance(value, Mapping) or set(value) != expected_fields:
        raise ValueError("malformed generated MaxSAT clause")
    clause_id = value.get("clause_id")
    raw_literals = value.get("literals")
    weight = value.get("weight") if soft else None
    if not _is_integer(clause_id) or not isinstance(raw_literals, list):
        raise ValueError("MaxSAT clause fields have invalid types")
    assert isinstance(clause_id, int)
    if clause_id < 0 or not raw_literals:
        raise ValueError("MaxSAT clauses require a nonnegative ID and at least one literal")
    literals: list[int] = []
    variables: set[int] = set()
    for literal in raw_literals:
        if not _is_integer(literal):
            raise ValueError("MaxSAT literals must be JSON integers")
        assert isinstance(literal, int)
        variable = abs(literal)
        if literal == 0 or not 1 <= variable <= num_variables or variable in variables:
            raise ValueError("MaxSAT clause contains an invalid or repeated variable")
        variables.add(variable)
        literals.append(literal)
    parsed_weight: int | None = None
    if soft:
        if not _is_integer(weight):
            raise ValueError("MaxSAT soft-clause weight must be a positive exact integer")
        assert isinstance(weight, int)
        if not 1 <= weight <= MAX_SAFE_INTEGER:
            raise ValueError("MaxSAT soft-clause weight must be a positive exact integer")
        parsed_weight = weight
    return _Clause(clause_id, tuple(literals), parsed_weight)


def _parse_formula(public_instance: Mapping[str, Any]) -> _Formula:
    if set(public_instance) != _INSTANCE_FIELDS:
        raise ValueError("malformed generated MaxSAT instance")
    if public_instance.get("format_version") != "aip-weighted-partial-maxsat-instance/1":
        raise ValueError("unsupported MaxSAT instance format")
    num_variables = public_instance.get("num_variables")
    raw_hard = public_instance.get("hard_clauses")
    raw_soft = public_instance.get("soft_clauses")
    threshold = public_instance.get("threshold")
    if (
        not _is_integer(num_variables)
        or not isinstance(raw_hard, list)
        or not isinstance(raw_soft, list)
        or not _is_integer(threshold)
    ):
        raise ValueError("malformed generated MaxSAT instance fields")
    assert isinstance(num_variables, int)
    assert isinstance(threshold, int)
    if num_variables < 1 or not 0 <= threshold <= MAX_SAFE_INTEGER:
        raise ValueError("invalid MaxSAT variable count or threshold")

    hard_clauses = tuple(
        _parse_clause(value, num_variables=num_variables, soft=False) for value in raw_hard
    )
    soft_clauses = tuple(
        _parse_clause(value, num_variables=num_variables, soft=True) for value in raw_soft
    )
    clause_ids = [clause.clause_id for clause in (*hard_clauses, *soft_clauses)]
    if len(clause_ids) != len(set(clause_ids)):
        raise ValueError("MaxSAT clause IDs must be globally unique")
    total_soft_weight = sum(clause.weight or 0 for clause in soft_clauses)
    if total_soft_weight > MAX_SAFE_INTEGER:
        raise ValueError("MaxSAT weight sum is outside the exact range")
    return _Formula(num_variables, hard_clauses, soft_clauses, threshold)


def _clause_satisfied(clause: _Clause, assignment: tuple[int, ...]) -> bool:
    return any(
        assignment[abs(literal) - 1] == (1 if literal > 0 else 0) for literal in clause.literals
    )


def evaluate_assignment(public_instance: Mapping[str, Any], assignment: object) -> tuple[bool, int]:
    """Strictly evaluate a public assignment and return hard feasibility plus soft cost."""

    formula = _parse_formula(public_instance)
    if not isinstance(assignment, list) or len(assignment) != formula.num_variables:
        raise _AssignmentRejected(MaxSatReason.ASSIGNMENT_LENGTH_MISMATCH)
    values: list[int] = []
    for value in assignment:
        if not _is_integer(value) or value not in (0, 1):
            raise _AssignmentRejected(MaxSatReason.ASSIGNMENT_VALUE_INVALID)
        values.append(value)
    frozen = tuple(values)
    hard_satisfied = all(_clause_satisfied(clause, frozen) for clause in formula.hard_clauses)
    soft_cost = sum(
        clause.weight or 0
        for clause in formula.soft_clauses
        if not _clause_satisfied(clause, frozen)
    )
    return hard_satisfied, soft_cost


def _verify_assignment(payload: Mapping[str, Any], formula: _Formula) -> int:
    if set(payload) != _ASSIGNMENT_FIELDS:
        raise _AssignmentRejected(ErrorCode.INVALID_PAYLOAD)
    assignment = payload.get("assignment")
    if not isinstance(assignment, list) or len(assignment) != formula.num_variables:
        raise _AssignmentRejected(MaxSatReason.ASSIGNMENT_LENGTH_MISMATCH)
    values: list[int] = []
    for value in assignment:
        if not _is_integer(value) or value not in (0, 1):
            raise _AssignmentRejected(MaxSatReason.ASSIGNMENT_VALUE_INVALID)
        values.append(value)
    frozen = tuple(values)
    if any(not _clause_satisfied(clause, frozen) for clause in formula.hard_clauses):
        raise _AssignmentRejected(MaxSatReason.HARD_CLAUSE_UNSATISFIED)
    soft_cost = sum(
        clause.weight or 0
        for clause in formula.soft_clauses
        if not _clause_satisfied(clause, frozen)
    )
    if soft_cost > formula.threshold:
        raise _AssignmentRejected(MaxSatReason.COST_EXCEEDS_THRESHOLD, soft_cost=soft_cost)
    return soft_cost


class WeightedPartialMaxSatProtocol:
    """Pure one-shot verifier for a complete assignment to a public WCNF instance."""

    task_id = TASK_ID
    task_version = TASK_VERSION

    def initialize(
        self, *, generated_case: GeneratedCase, context: ArthurContext
    ) -> MaxSatProtocolState:
        del context
        self._validate_task_identity(generated_case)
        _parse_formula(generated_case.public_instance)
        return MaxSatProtocolState()

    def public_protocol_description(self, *, generated_case: GeneratedCase) -> Mapping[str, Any]:
        self._validate_task_identity(generated_case)
        formula = _parse_formula(generated_case.public_instance)
        return {
            "api_version": "aip/1",
            "mode": "one_shot",
            "initial_event_kinds": [ASSIGNMENT_EVENT_KIND],
            "event_schemas": {
                ASSIGNMENT_EVENT_KIND: {
                    "schema_ref": (
                        "tasks/tier1_np/new_weighted_partial_maxsat/schemas/assignment.schema.json"
                    )
                }
            },
            "public_parameters": {
                "num_variables": formula.num_variables,
                "num_hard_clauses": len(formula.hard_clauses),
                "num_soft_clauses": len(formula.soft_clauses),
                "one_shot": True,
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
        del context
        if not isinstance(state, MaxSatProtocolState):
            raise TypeError("state is not a MaxSatProtocolState")
        self._validate_task_identity(generated_case)
        if state.terminal_status is not None:
            return Transition(
                new_state=state,
                terminal_status=TerminalStatus.REJECT,
                reason_code=ErrorCode.SESSION_TERMINAL,
                public_state={"phase": "terminal"},
            )
        if event.kind != ASSIGNMENT_EVENT_KIND:
            return self._rejection(ErrorCode.INVALID_EVENT_KIND)
        if event.artifact_refs:
            return self._rejection(ErrorCode.INVALID_PAYLOAD)

        formula = _parse_formula(generated_case.public_instance)
        try:
            soft_cost = _verify_assignment(event.payload, formula)
        except _AssignmentRejected as rejected:
            return self._rejection(rejected.reason_code, soft_cost=rejected.soft_cost)

        accepted_state = MaxSatProtocolState(
            phase="terminal",
            terminal_status=TerminalStatus.ACCEPT,
            reason_code=ErrorCode.PROTOCOL_ACCEPT,
            soft_cost=soft_cost,
            events_processed=1,
        )
        return Transition(
            new_state=accepted_state,
            terminal_status=TerminalStatus.ACCEPT,
            reason_code=ErrorCode.PROTOCOL_ACCEPT,
            milestones={"assignment_submitted": 1, "soft_cost": soft_cost},
            public_state={"phase": "terminal", "assignment_checked": True},
        )

    def terminal_metrics(self, *, state: Any) -> Mapping[str, int | float | str]:
        if not isinstance(state, MaxSatProtocolState):
            raise TypeError("state is not a MaxSatProtocolState")
        metrics: dict[str, int | float | str] = {
            "events_processed": state.events_processed,
            "assignment_valid": int(state.terminal_status == TerminalStatus.ACCEPT),
        }
        if state.soft_cost is not None:
            metrics["soft_cost"] = state.soft_cost
        if state.reason_code is not None:
            metrics["reason_code"] = state.reason_code
        return metrics

    @staticmethod
    def _validate_task_identity(generated_case: GeneratedCase) -> None:
        if generated_case.task_id != TASK_ID or generated_case.task_version != TASK_VERSION:
            raise ValueError("generated case does not belong to this task plugin")

    @staticmethod
    def _rejection(reason_code: str, *, soft_cost: int | None = None) -> Transition:
        rejected_state = MaxSatProtocolState(
            phase="terminal",
            terminal_status=TerminalStatus.REJECT,
            reason_code=reason_code,
            soft_cost=soft_cost,
            events_processed=1,
        )
        milestones: dict[str, int] = {"assignment_submitted": 1}
        if soft_cost is not None:
            milestones["soft_cost"] = soft_cost
        return Transition(
            new_state=rejected_state,
            terminal_status=TerminalStatus.REJECT,
            reason_code=reason_code,
            milestones=milestones,
            public_state={"phase": "terminal", "assignment_checked": False},
        )


def _participant_instance(client: ParticipantClient) -> Mapping[str, Any]:
    response = client.get_instance()
    nested = response.get("public_instance")
    return nested if isinstance(nested, Mapping) else response


class WrongLengthMaxSatAgent:
    """Deterministic negative fixture that never depends on a private witness."""

    agent_id = "virtual-wrong-length"

    def run(self, *, client: ParticipantClient, workspace: Path) -> None:
        del workspace
        instance = _participant_instance(client)
        num_variables = instance.get("num_variables")
        if not _is_integer(num_variables):
            raise ValueError("participant returned a malformed MaxSAT instance")
        assert isinstance(num_variables, int)
        if num_variables < 1:
            raise ValueError("participant returned a malformed MaxSAT instance")
        client.submit_event(
            sequence=0,
            kind=ASSIGNMENT_EVENT_KIND,
            payload={"assignment": [0] * (num_variables - 1)},
        )


class InvalidValueMaxSatAgent:
    """Deterministic negative fixture containing one non-Boolean integer."""

    agent_id = "virtual-invalid-value"

    def run(self, *, client: ParticipantClient, workspace: Path) -> None:
        del workspace
        instance = _participant_instance(client)
        num_variables = instance.get("num_variables")
        if not _is_integer(num_variables):
            raise ValueError("participant returned a malformed MaxSAT instance")
        assert isinstance(num_variables, int)
        if num_variables < 1:
            raise ValueError("participant returned a malformed MaxSAT instance")
        assignment = [0] * num_variables
        assignment[0] = 2
        client.submit_event(
            sequence=0,
            kind=ASSIGNMENT_EVENT_KIND,
            payload={"assignment": assignment},
        )


_VIRTUAL_AGENT_LIST: Final[tuple[VirtualAgent, ...]] = (
    WrongLengthMaxSatAgent(),
    InvalidValueMaxSatAgent(),
)

VIRTUAL_AGENTS: Final[Mapping[str, VirtualAgent]] = {
    agent.agent_id: agent for agent in _VIRTUAL_AGENT_LIST
}
