"""Shared primitives used by the current Merlin-Bench tasks."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, TypeGuard

from aipbench.core.errors import ErrorCode
from aipbench.core.models import GeneratedCase, ParticipantEvent, TerminalStatus, Transition
from aipbench.core.protocol import ArthurContext, ParticipantClient, VirtualAgent
from aipbench.tasks.shared.closest_vector_cases.common import (
    MAX_AMBIENT_DIMENSION,
    MAX_LATTICE_RANK,
    MAX_MATRIX_CELLS,
    MAX_SAFE_INTEGER,
    exact_matrix_rank,
    squared_distance_numerator,
)

TASK_ID: Final = "t1.new_structured_closest_vector"

TASK_VERSION: Final = "0.1.0"

COEFFICIENTS_EVENT_KIND: Final = "closest_vector.coefficients"

_INSTANCE_FIELDS: Final = frozenset(
    {
        "format_version",
        "ambient_dimension",
        "rank",
        "basis",
        "target_numerator",
        "denominator",
        "radius_squared_numerator",
        "coefficient_bound",
    }
)

_COEFFICIENT_FIELDS: Final = frozenset({"coefficients"})


class ClosestVectorReason:
    """Stable participant-visible rejection codes."""

    COEFFICIENT_COUNT_INVALID = "CLOSEST_VECTOR_COEFFICIENT_COUNT_INVALID"
    COEFFICIENT_INVALID = "CLOSEST_VECTOR_COEFFICIENT_INVALID"
    DISTANCE_EXCEEDED = "CLOSEST_VECTOR_DISTANCE_EXCEEDED"


@dataclass(frozen=True)
class ClosestVectorProtocolState:
    phase: str = "awaiting_coefficients"
    terminal_status: TerminalStatus | None = None
    reason_code: str | None = None
    events_processed: int = 0


@dataclass(frozen=True)
class _Instance:
    ambient_dimension: int
    rank: int
    basis: tuple[tuple[int, ...], ...]
    target_numerator: tuple[int, ...]
    denominator: int
    radius_squared_numerator: int
    coefficient_bound: int


@dataclass(frozen=True)
class CoefficientEvaluation:
    distance_numerator: int
    radius_squared_numerator: int
    within_radius: bool


class _SubmissionRejected(Exception):
    def __init__(self, reason_code: str) -> None:
        super().__init__(reason_code)
        self.reason_code = reason_code


def _is_integer(value: object) -> TypeGuard[int]:
    return isinstance(value, int) and not isinstance(value, bool)


def _parse_instance(public_instance: Mapping[str, Any]) -> _Instance:
    if set(public_instance) != _INSTANCE_FIELDS:
        raise ValueError("malformed generated Structured Closest Vector instance")
    if public_instance.get("format_version") != "aip-structured-closest-vector-instance/1":
        raise ValueError("unsupported Structured Closest Vector instance format")
    ambient_dimension = public_instance.get("ambient_dimension")
    rank = public_instance.get("rank")
    denominator = public_instance.get("denominator")
    radius = public_instance.get("radius_squared_numerator")
    coefficient_bound = public_instance.get("coefficient_bound")
    raw_basis = public_instance.get("basis")
    raw_target = public_instance.get("target_numerator")
    if (
        not all(
            _is_integer(value)
            for value in (ambient_dimension, rank, denominator, radius, coefficient_bound)
        )
        or not isinstance(raw_basis, list)
        or not isinstance(raw_target, list)
    ):
        raise ValueError("malformed generated Structured Closest Vector fields")
    assert isinstance(ambient_dimension, int)
    assert isinstance(rank, int)
    assert isinstance(denominator, int)
    assert isinstance(radius, int)
    assert isinstance(coefficient_bound, int)
    if (
        not 1 <= ambient_dimension <= MAX_AMBIENT_DIMENSION
        or not 1 <= rank <= MAX_LATTICE_RANK
        or ambient_dimension * rank > MAX_MATRIX_CELLS
        or not 1 <= denominator <= MAX_SAFE_INTEGER
        or not 0 <= radius <= MAX_SAFE_INTEGER
        or not 1 <= coefficient_bound <= MAX_SAFE_INTEGER
    ):
        raise ValueError("generated dimensions or numeric bounds are invalid")
    if len(raw_basis) != ambient_dimension or len(raw_target) != ambient_dimension:
        raise ValueError("generated basis or target has the wrong ambient dimension")

    basis_rows: list[tuple[int, ...]] = []
    for raw_row in raw_basis:
        if not isinstance(raw_row, list) or len(raw_row) != rank:
            raise ValueError("generated basis is not a rectangular d-by-n matrix")
        if any(not _is_integer(value) or abs(value) > MAX_SAFE_INTEGER for value in raw_row):
            raise ValueError("generated basis contains an invalid integer")
        basis_rows.append(tuple(raw_row))
    if any(not _is_integer(value) or abs(value) > MAX_SAFE_INTEGER for value in raw_target):
        raise ValueError("generated target contains an invalid integer")
    basis = tuple(basis_rows)
    if exact_matrix_rank(basis) != rank:
        raise ValueError("generated basis does not have full column rank")
    return _Instance(
        ambient_dimension=ambient_dimension,
        rank=rank,
        basis=basis,
        target_numerator=tuple(raw_target),
        denominator=denominator,
        radius_squared_numerator=radius,
        coefficient_bound=coefficient_bound,
    )


def _parse_coefficients(value: object, instance: _Instance) -> tuple[int, ...]:
    if not isinstance(value, list):
        raise _SubmissionRejected(ErrorCode.INVALID_PAYLOAD)
    if len(value) != instance.rank:
        raise _SubmissionRejected(ClosestVectorReason.COEFFICIENT_COUNT_INVALID)
    coefficients: list[int] = []
    for coefficient in value:
        if not _is_integer(coefficient) or abs(coefficient) > instance.coefficient_bound:
            raise _SubmissionRejected(ClosestVectorReason.COEFFICIENT_INVALID)
        assert isinstance(coefficient, int)
        coefficients.append(coefficient)
    return tuple(coefficients)


def _evaluate(instance: _Instance, coefficients: tuple[int, ...]) -> CoefficientEvaluation:
    distance = squared_distance_numerator(
        instance.basis,
        instance.target_numerator,
        instance.denominator,
        coefficients,
    )
    return CoefficientEvaluation(
        distance_numerator=distance,
        radius_squared_numerator=instance.radius_squared_numerator,
        within_radius=distance <= instance.radius_squared_numerator,
    )


def evaluate_coefficients(
    public_instance: Mapping[str, Any], coefficients: object
) -> CoefficientEvaluation:
    """Strictly parse and evaluate a coefficient-vector certificate."""

    instance = _parse_instance(public_instance)
    parsed = _parse_coefficients(coefficients, instance)
    return _evaluate(instance, parsed)


def _verify_coefficients(payload: Mapping[str, Any], instance: _Instance) -> CoefficientEvaluation:
    if set(payload) != _COEFFICIENT_FIELDS:
        raise _SubmissionRejected(ErrorCode.INVALID_PAYLOAD)
    coefficients = _parse_coefficients(payload.get("coefficients"), instance)
    evaluation = _evaluate(instance, coefficients)
    if not evaluation.within_radius:
        raise _SubmissionRejected(ClosestVectorReason.DISTANCE_EXCEEDED)
    return evaluation


class StructuredClosestVectorProtocol:
    """Pure one-shot verifier for an exact rational-target CVP relation."""

    task_id = TASK_ID
    task_version = TASK_VERSION

    def initialize(
        self, *, generated_case: GeneratedCase, context: ArthurContext
    ) -> ClosestVectorProtocolState:
        del context
        self._validate_task_identity(generated_case)
        _parse_instance(generated_case.public_instance)
        return ClosestVectorProtocolState()

    def public_protocol_description(self, *, generated_case: GeneratedCase) -> Mapping[str, Any]:
        self._validate_task_identity(generated_case)
        instance = _parse_instance(generated_case.public_instance)
        return {
            "api_version": "aip/1",
            "mode": "one_shot",
            "initial_event_kinds": [COEFFICIENTS_EVENT_KIND],
            "event_schemas": {
                COEFFICIENTS_EVENT_KIND: {
                    "schema_ref": (
                        "tasks/tier1_np/new_structured_closest_vector/schemas/coefficients.schema.json"
                    )
                }
            },
            "public_parameters": {
                "ambient_dimension": instance.ambient_dimension,
                "rank": instance.rank,
                "denominator": instance.denominator,
                "radius_squared_numerator": instance.radius_squared_numerator,
                "coefficient_bound": instance.coefficient_bound,
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
        if not isinstance(state, ClosestVectorProtocolState):
            raise TypeError("state is not a ClosestVectorProtocolState")
        self._validate_task_identity(generated_case)
        if state.terminal_status is not None:
            return Transition(
                new_state=state,
                terminal_status=TerminalStatus.REJECT,
                reason_code=ErrorCode.SESSION_TERMINAL,
                public_state={"phase": "terminal"},
            )
        if event.kind != COEFFICIENTS_EVENT_KIND:
            return self._rejection(ErrorCode.INVALID_EVENT_KIND)
        if event.artifact_refs:
            return self._rejection(ErrorCode.INVALID_PAYLOAD)

        instance = _parse_instance(generated_case.public_instance)
        try:
            evaluation = _verify_coefficients(event.payload, instance)
        except _SubmissionRejected as rejected:
            return self._rejection(rejected.reason_code)

        accepted = ClosestVectorProtocolState(
            phase="terminal",
            terminal_status=TerminalStatus.ACCEPT,
            reason_code=ErrorCode.PROTOCOL_ACCEPT,
            events_processed=1,
        )
        return Transition(
            new_state=accepted,
            terminal_status=TerminalStatus.ACCEPT,
            reason_code=ErrorCode.PROTOCOL_ACCEPT,
            milestones={"coefficients_submitted": 1},
            public_state={
                "phase": "terminal",
                "coefficients_checked": True,
                "distance_numerator": evaluation.distance_numerator,
            },
        )

    def terminal_metrics(self, *, state: Any) -> Mapping[str, int | float | str]:
        if not isinstance(state, ClosestVectorProtocolState):
            raise TypeError("state is not a ClosestVectorProtocolState")
        metrics: dict[str, int | float | str] = {
            "events_processed": state.events_processed,
            "coefficients_valid": int(state.terminal_status == TerminalStatus.ACCEPT),
        }
        if state.reason_code is not None:
            metrics["reason_code"] = state.reason_code
        return metrics

    @staticmethod
    def _validate_task_identity(generated_case: GeneratedCase) -> None:
        if generated_case.task_id != TASK_ID or generated_case.task_version != TASK_VERSION:
            raise ValueError("generated case does not belong to this task plugin")

    @staticmethod
    def _rejection(reason_code: str) -> Transition:
        rejected = ClosestVectorProtocolState(
            phase="terminal",
            terminal_status=TerminalStatus.REJECT,
            reason_code=reason_code,
            events_processed=1,
        )
        return Transition(
            new_state=rejected,
            terminal_status=TerminalStatus.REJECT,
            reason_code=reason_code,
            milestones={"coefficients_submitted": 1},
            public_state={"phase": "terminal", "coefficients_checked": False},
        )


def _participant_instance(client: ParticipantClient) -> Mapping[str, Any]:
    response = client.get_instance()
    nested = response.get("public_instance")
    return nested if isinstance(nested, Mapping) else response


class WrongCoefficientCountAgent:
    agent_id = "virtual-wrong-coefficient-count"

    def run(self, *, client: ParticipantClient, workspace: Path) -> None:
        del workspace
        instance = _participant_instance(client)
        rank = instance.get("rank")
        count = rank - 1 if isinstance(rank, int) and rank > 1 else 0
        client.submit_event(
            sequence=0,
            kind=COEFFICIENTS_EVENT_KIND,
            payload={"coefficients": [0] * count},
        )


class InvalidCoefficientAgent:
    agent_id = "virtual-invalid-coefficient"

    def run(self, *, client: ParticipantClient, workspace: Path) -> None:
        del workspace
        instance = _participant_instance(client)
        rank = instance.get("rank")
        bound = instance.get("coefficient_bound")
        count = rank if isinstance(rank, int) and rank > 0 else 1
        invalid = bound + 1 if isinstance(bound, int) else MAX_SAFE_INTEGER + 1
        coefficients = [0] * count
        coefficients[0] = invalid
        client.submit_event(
            sequence=0,
            kind=COEFFICIENTS_EVENT_KIND,
            payload={"coefficients": coefficients},
        )


_VIRTUAL_AGENT_LIST: Final[tuple[VirtualAgent, ...]] = (
    WrongCoefficientCountAgent(),
    InvalidCoefficientAgent(),
)

VIRTUAL_AGENTS: Final[Mapping[str, VirtualAgent]] = {
    agent.agent_id: agent for agent in _VIRTUAL_AGENT_LIST
}
