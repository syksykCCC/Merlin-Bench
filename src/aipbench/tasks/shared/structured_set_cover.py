"""Shared primitives used by the current Merlin-Bench tasks."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, TypeGuard

from aipbench.core.errors import ErrorCode
from aipbench.core.models import GeneratedCase, ParticipantEvent, TerminalStatus, Transition
from aipbench.core.protocol import ArthurContext, ParticipantClient, VirtualAgent
from aipbench.tasks.shared.set_cover_cases.common import (
    MAX_NUM_ELEMENTS,
    MAX_NUM_SETS,
    MAX_TOTAL_INCIDENCE,
    solve_exact_partition,
)

TASK_ID: Final = "t1.new_structured_set_cover"

TASK_VERSION: Final = "0.1.0"

SELECTION_EVENT_KIND: Final = "set_cover.selection"

MAX_SAFE_INTEGER: Final = 9_007_199_254_740_991

_INSTANCE_FIELDS: Final = frozenset({"format_version", "num_elements", "sets", "budget"})

_SET_FIELDS: Final = frozenset({"set_id", "elements", "weight"})

_SELECTION_FIELDS: Final = frozenset({"set_ids"})


class SetCoverReason:
    """Stable participant-visible rejection codes."""

    SET_ID_INVALID = "SET_COVER_SET_ID_INVALID"
    SET_ID_DUPLICATE = "SET_COVER_SET_ID_DUPLICATE"
    BUDGET_EXCEEDED = "SET_COVER_BUDGET_EXCEEDED"
    UNCOVERED_ELEMENT = "SET_COVER_UNCOVERED_ELEMENT"


@dataclass(frozen=True)
class SetCoverProtocolState:
    phase: str = "awaiting_selection"
    terminal_status: TerminalStatus | None = None
    reason_code: str | None = None
    events_processed: int = 0


@dataclass(frozen=True)
class _Candidate:
    elements: frozenset[int]
    weight: int


@dataclass(frozen=True)
class _Instance:
    num_elements: int
    sets_by_id: Mapping[int, _Candidate]
    budget: int


@dataclass(frozen=True)
class SelectionEvaluation:
    total_weight: int
    covered_elements: int
    covers_universe: bool


class _SelectionRejected(Exception):
    def __init__(self, reason_code: str) -> None:
        super().__init__(reason_code)
        self.reason_code = reason_code


def _is_integer(value: object) -> TypeGuard[int]:
    return isinstance(value, int) and not isinstance(value, bool)


def _parse_instance(public_instance: Mapping[str, Any]) -> _Instance:
    if set(public_instance) != _INSTANCE_FIELDS:
        raise ValueError("malformed generated Structured Set Cover instance")
    if public_instance.get("format_version") != "aip-structured-set-cover-instance/1":
        raise ValueError("unsupported Structured Set Cover instance format")
    num_elements = public_instance.get("num_elements")
    budget = public_instance.get("budget")
    raw_sets = public_instance.get("sets")
    if not _is_integer(num_elements) or not _is_integer(budget) or not isinstance(raw_sets, list):
        raise ValueError("malformed generated Structured Set Cover fields")
    assert isinstance(num_elements, int)
    assert isinstance(budget, int)
    if (
        not 1 <= num_elements <= MAX_NUM_ELEMENTS
        or not 1 <= budget <= MAX_SAFE_INTEGER
        or not raw_sets
        or len(raw_sets) > MAX_NUM_SETS
    ):
        raise ValueError("generated universe, set family, or budget is invalid")

    sets_by_id: dict[int, _Candidate] = {}
    incidence_keys: set[frozenset[int]] = set()
    union: set[int] = set()
    total_incidence = 0
    for raw_set in raw_sets:
        if not isinstance(raw_set, Mapping) or set(raw_set) != _SET_FIELDS:
            raise ValueError("generated public set is malformed")
        set_id = raw_set.get("set_id")
        weight = raw_set.get("weight")
        raw_elements = raw_set.get("elements")
        if not _is_integer(set_id) or not _is_integer(weight) or not isinstance(raw_elements, list):
            raise ValueError("generated public set fields have invalid types")
        assert isinstance(set_id, int)
        assert isinstance(weight, int)
        total_incidence += len(raw_elements)
        if len(raw_elements) > num_elements or total_incidence > MAX_TOTAL_INCIDENCE:
            raise ValueError("generated public incidence exceeds the task safety envelope")
        if (
            not 1 <= set_id <= MAX_SAFE_INTEGER
            or set_id in sets_by_id
            or not 1 <= weight <= MAX_SAFE_INTEGER
            or not raw_elements
        ):
            raise ValueError("generated public set ID, weight, or incidence is invalid")
        elements: set[int] = set()
        for element in raw_elements:
            if not _is_integer(element):
                raise ValueError("generated public set contains a non-integer element")
            assert isinstance(element, int)
            if not 1 <= element <= num_elements or element in elements:
                raise ValueError("generated public set contains an invalid or repeated element")
            elements.add(element)
        frozen_elements = frozenset(elements)
        if frozen_elements in incidence_keys:
            raise ValueError("generated public sets must be incidence-distinct")
        incidence_keys.add(frozen_elements)
        sets_by_id[set_id] = _Candidate(frozen_elements, weight)
        union.update(elements)
    if len(union) != num_elements:
        raise ValueError("generated public sets do not cover the declared universe")
    return _Instance(num_elements, sets_by_id, budget)


def _parse_set_ids(value: object, instance: _Instance) -> tuple[int, ...]:
    if not isinstance(value, list):
        raise _SelectionRejected(ErrorCode.INVALID_PAYLOAD)
    result: list[int] = []
    for set_id in value:
        if not _is_integer(set_id) or set_id not in instance.sets_by_id:
            raise _SelectionRejected(SetCoverReason.SET_ID_INVALID)
        assert isinstance(set_id, int)
        result.append(set_id)
    if len(set(result)) != len(result):
        raise _SelectionRejected(SetCoverReason.SET_ID_DUPLICATE)
    return tuple(result)


def _evaluate(instance: _Instance, set_ids: tuple[int, ...]) -> SelectionEvaluation:
    total_weight = 0
    covered: set[int] = set()
    for set_id in set_ids:
        candidate = instance.sets_by_id[set_id]
        total_weight += candidate.weight
        covered.update(candidate.elements)
    return SelectionEvaluation(
        total_weight=total_weight,
        covered_elements=len(covered),
        covers_universe=len(covered) == instance.num_elements,
    )


def evaluate_selection(public_instance: Mapping[str, Any], set_ids: object) -> SelectionEvaluation:
    """Strictly parse and evaluate a public set-ID selection."""

    instance = _parse_instance(public_instance)
    parsed = _parse_set_ids(set_ids, instance)
    return _evaluate(instance, parsed)


def solve_public_exact_cover(public_instance: Mapping[str, Any]) -> tuple[int, ...]:
    """Solve a generated scaled instance using only its public incidence lists."""

    instance = _parse_instance(public_instance)
    set_ids = tuple(instance.sets_by_id)
    candidates = tuple(
        frozenset(element - 1 for element in instance.sets_by_id[set_id].elements)
        for set_id in set_ids
    )
    if any(instance.sets_by_id[set_id].weight != 1 for set_id in set_ids):
        raise ValueError("the scaled public exact-cover baseline requires unit weights")
    solution = solve_exact_partition(instance.num_elements, candidates)
    selected = tuple(set_ids[index] for index in solution.candidate_indices)
    evaluation = _evaluate(instance, selected)
    if evaluation.total_weight > instance.budget or not evaluation.covers_universe:
        raise RuntimeError("public exact-cover baseline recovered an invalid selection")
    return selected


def _verify_selection(payload: Mapping[str, Any], instance: _Instance) -> SelectionEvaluation:
    if set(payload) != _SELECTION_FIELDS:
        raise _SelectionRejected(ErrorCode.INVALID_PAYLOAD)
    set_ids = _parse_set_ids(payload.get("set_ids"), instance)
    evaluation = _evaluate(instance, set_ids)
    if evaluation.total_weight > instance.budget:
        raise _SelectionRejected(SetCoverReason.BUDGET_EXCEEDED)
    if not evaluation.covers_universe:
        raise _SelectionRejected(SetCoverReason.UNCOVERED_ELEMENT)
    return evaluation


class StructuredSetCoverProtocol:
    """Pure one-shot verifier for a budget-feasible public set cover."""

    task_id = TASK_ID
    task_version = TASK_VERSION

    def initialize(
        self, *, generated_case: GeneratedCase, context: ArthurContext
    ) -> SetCoverProtocolState:
        del context
        self._validate_task_identity(generated_case)
        _parse_instance(generated_case.public_instance)
        return SetCoverProtocolState()

    def public_protocol_description(self, *, generated_case: GeneratedCase) -> Mapping[str, Any]:
        self._validate_task_identity(generated_case)
        instance = _parse_instance(generated_case.public_instance)
        return {
            "api_version": "aip/1",
            "mode": "one_shot",
            "initial_event_kinds": [SELECTION_EVENT_KIND],
            "event_schemas": {
                SELECTION_EVENT_KIND: {
                    "schema_ref": (
                        "tasks/tier1_np/new_structured_set_cover/schemas/selection.schema.json"
                    )
                }
            },
            "public_parameters": {
                "num_elements": instance.num_elements,
                "num_sets": len(instance.sets_by_id),
                "budget": instance.budget,
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
        if not isinstance(state, SetCoverProtocolState):
            raise TypeError("state is not a SetCoverProtocolState")
        self._validate_task_identity(generated_case)
        if state.terminal_status is not None:
            return Transition(
                new_state=state,
                terminal_status=TerminalStatus.REJECT,
                reason_code=ErrorCode.SESSION_TERMINAL,
                public_state={"phase": "terminal"},
            )
        if event.kind != SELECTION_EVENT_KIND:
            return self._rejection(ErrorCode.INVALID_EVENT_KIND)
        if event.artifact_refs:
            return self._rejection(ErrorCode.INVALID_PAYLOAD)

        instance = _parse_instance(generated_case.public_instance)
        try:
            evaluation = _verify_selection(event.payload, instance)
        except _SelectionRejected as rejected:
            return self._rejection(rejected.reason_code)

        accepted = SetCoverProtocolState(
            phase="terminal",
            terminal_status=TerminalStatus.ACCEPT,
            reason_code=ErrorCode.PROTOCOL_ACCEPT,
            events_processed=1,
        )
        return Transition(
            new_state=accepted,
            terminal_status=TerminalStatus.ACCEPT,
            reason_code=ErrorCode.PROTOCOL_ACCEPT,
            milestones={"set_selection_submitted": 1},
            public_state={
                "phase": "terminal",
                "selection_checked": True,
                "selected_weight": evaluation.total_weight,
            },
        )

    def terminal_metrics(self, *, state: Any) -> Mapping[str, int | float | str]:
        if not isinstance(state, SetCoverProtocolState):
            raise TypeError("state is not a SetCoverProtocolState")
        metrics: dict[str, int | float | str] = {
            "events_processed": state.events_processed,
            "selection_valid": int(state.terminal_status == TerminalStatus.ACCEPT),
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
        rejected = SetCoverProtocolState(
            phase="terminal",
            terminal_status=TerminalStatus.REJECT,
            reason_code=reason_code,
            events_processed=1,
        )
        return Transition(
            new_state=rejected,
            terminal_status=TerminalStatus.REJECT,
            reason_code=reason_code,
            milestones={"set_selection_submitted": 1},
            public_state={"phase": "terminal", "selection_checked": False},
        )


def _participant_instance(client: ParticipantClient) -> Mapping[str, Any]:
    response = client.get_instance()
    nested = response.get("public_instance")
    return nested if isinstance(nested, Mapping) else response


class HonestSetCoverAgent:
    agent_id = "virtual-honest"

    def run(self, *, client: ParticipantClient, workspace: Path) -> None:
        del workspace
        instance = _participant_instance(client)
        selection = solve_public_exact_cover(instance)
        client.submit_event(
            sequence=0,
            kind=SELECTION_EVENT_KIND,
            payload={"set_ids": list(selection)},
        )


class EmptySetCoverAgent:
    agent_id = "virtual-wrong-cover"

    def run(self, *, client: ParticipantClient, workspace: Path) -> None:
        del workspace
        _participant_instance(client)
        client.submit_event(
            sequence=0,
            kind=SELECTION_EVENT_KIND,
            payload={"set_ids": []},
        )


class InvalidSetIdAgent:
    agent_id = "virtual-invalid-set-id"

    def run(self, *, client: ParticipantClient, workspace: Path) -> None:
        del workspace
        _participant_instance(client)
        client.submit_event(
            sequence=0,
            kind=SELECTION_EVENT_KIND,
            payload={"set_ids": [0]},
        )


_VIRTUAL_AGENT_LIST: Final[tuple[VirtualAgent, ...]] = (
    HonestSetCoverAgent(),
    EmptySetCoverAgent(),
    InvalidSetIdAgent(),
)

VIRTUAL_AGENTS: Final[Mapping[str, VirtualAgent]] = {
    agent.agent_id: agent for agent in _VIRTUAL_AGENT_LIST
}
