"""Shared primitives used by the current Merlin-Bench tasks."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Final

from aipbench.core.errors import ErrorCode
from aipbench.core.models import (
    GeneratedCase,
    ParticipantEvent,
    ProtocolReply,
    TerminalStatus,
    Transition,
)
from aipbench.core.protocol import ArthurContext
from aipbench.tasks.shared.hamiltonicity_bind_open_cases.common import (
    LogicalGraph,
    is_strict_integer,
    parse_public_graph,
    relabel_graph,
    validate_hamilton_cycle,
)

TASK_ID: Final = "t2.new_hamiltonicity_bind_open"

TASK_VERSION: Final = "0.1.0"

CHALLENGE_LANES: Final = 24

COMMIT_EVENT_KIND: Final = "hamiltonicity.commit"

CHALLENGE_REPLY_KIND: Final = "hamiltonicity.challenge"

OPEN_EVENT_KIND: Final = "hamiltonicity.open"

_PUBLIC_FIELDS: Final = frozenset(
    {"format_version", "graph_model", "num_vertices", "edges", "challenge_lanes"}
)

_COMMIT_FIELDS: Final = frozenset({"graphs"})

_OPEN_FIELDS: Final = frozenset({"openings"})


class HamiltonicityReason:
    """Stable participant-visible terminal reasons."""

    MALFORMED_EVENT = "HAMILTONICITY_MALFORMED_EVENT"
    INVALID_OPENING = "HAMILTONICITY_INVALID_OPENING"


def _validate_public_instance(public_instance: Mapping[str, Any]) -> LogicalGraph:
    if set(public_instance) != _PUBLIC_FIELDS:
        raise ValueError("malformed generated Hamiltonicity instance")
    if public_instance.get("format_version") != "aip-hamiltonicity/1":
        raise ValueError("unsupported Hamiltonicity instance format")
    if public_instance.get("graph_model") != "undirected_simple":
        raise ValueError("unsupported Hamiltonicity graph model")
    if public_instance.get("challenge_lanes") != CHALLENGE_LANES:
        raise ValueError(f"Hamiltonicity requires exactly {CHALLENGE_LANES} challenge lanes")
    return parse_public_graph(
        {
            "num_vertices": public_instance.get("num_vertices"),
            "edges": public_instance.get("edges"),
        }
    )


@dataclass(frozen=True)
class HamiltonicityProtocolState:
    """Arthur-private commitment and challenge state."""

    phase: str = "awaiting_commit"
    committed_graphs: tuple[LogicalGraph, ...] = ()
    challenge_bits: tuple[int, ...] = ()
    terminal_status: TerminalStatus | None = None
    reason_code: str | None = None
    events_processed: int = 0


def _parse_commit(payload: object, order: int) -> tuple[LogicalGraph, ...] | None:
    if not isinstance(payload, Mapping) or set(payload) != _COMMIT_FIELDS:
        return None
    raw_graphs = payload.get("graphs")
    if not isinstance(raw_graphs, list) or len(raw_graphs) != CHALLENGE_LANES:
        return None
    graphs: list[LogicalGraph] = []
    try:
        for raw_graph in raw_graphs:
            graph = parse_public_graph(raw_graph)
            if graph.num_vertices != order:
                return None
            graphs.append(graph)
    except ValueError:
        return None
    return tuple(graphs)


def _parse_opening_payload(payload: object, order: int) -> list[Mapping[str, Any]] | None:
    if not isinstance(payload, Mapping) or set(payload) != _OPEN_FIELDS:
        return None
    raw_openings = payload.get("openings")
    if not isinstance(raw_openings, list) or len(raw_openings) != CHALLENGE_LANES:
        return None
    openings: list[Mapping[str, Any]] = []
    for raw_opening in raw_openings:
        if not isinstance(raw_opening, Mapping):
            return None
        kind = raw_opening.get("kind")
        if kind == "isomorphism":
            if set(raw_opening) != {"kind", "permutation"}:
                return None
            values = raw_opening.get("permutation")
        elif kind == "cycle":
            if set(raw_opening) != {"kind", "vertices"}:
                return None
            values = raw_opening.get("vertices")
        else:
            return None
        if (
            not isinstance(values, list)
            or len(values) != order
            or any(not is_strict_integer(value) for value in values)
        ):
            return None
        openings.append(raw_opening)
    return openings


def _opening_is_valid(
    *,
    source: LogicalGraph,
    commitment: LogicalGraph,
    challenge_bit: int,
    opening: Mapping[str, Any],
) -> bool:
    if challenge_bit == 0:
        if opening.get("kind") != "isomorphism":
            return False
        permutation = opening["permutation"]
        if not isinstance(permutation, list) or set(permutation) != set(range(source.num_vertices)):
            return False
        try:
            return relabel_graph(source, permutation) == commitment
        except ValueError:
            return False
    if opening.get("kind") != "cycle":
        return False
    vertices = opening["vertices"]
    if not isinstance(vertices, list):
        return False
    try:
        validate_hamilton_cycle(commitment, vertices)
    except ValueError:
        return False
    return True


class HamiltonicityProtocol:
    """Atomic commit, random challenge, and tagged opening verifier."""

    task_id = TASK_ID
    task_version = TASK_VERSION
    schema_root = "tasks/tier2_interactive/new_hamiltonicity_bind_open/schemas"
    randomness_domain = TASK_ID

    def initialize(
        self, *, generated_case: GeneratedCase, context: ArthurContext
    ) -> HamiltonicityProtocolState:
        del context
        self._validate_task_identity(generated_case)
        _validate_public_instance(generated_case.public_instance)
        return HamiltonicityProtocolState()

    def public_protocol_description(self, *, generated_case: GeneratedCase) -> Mapping[str, Any]:
        self._validate_task_identity(generated_case)
        graph = _validate_public_instance(generated_case.public_instance)
        return {
            "api_version": "aip/1",
            "mode": "interactive",
            "public_coin": True,
            "initial_event_kinds": [COMMIT_EVENT_KIND],
            "event_schemas": {
                COMMIT_EVENT_KIND: {"schema_ref": f"{self.schema_root}/commit.schema.json"},
                OPEN_EVENT_KIND: {"schema_ref": f"{self.schema_root}/open.schema.json"},
            },
            "reply_schemas": {
                CHALLENGE_REPLY_KIND: {"schema_ref": f"{self.schema_root}/challenge.schema.json"}
            },
            "public_parameters": {
                "num_vertices": graph.num_vertices,
                "num_edges": len(graph.edges),
                "challenge_lanes": CHALLENGE_LANES,
                "permutation_orientation": "source_to_commit",
                "open_event_kind": OPEN_EVENT_KIND,
                "soundness_error": "2^-24",
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
        if not isinstance(state, HamiltonicityProtocolState):
            raise TypeError("state is not a HamiltonicityProtocolState")
        self._validate_task_identity(generated_case)
        source = _validate_public_instance(generated_case.public_instance)
        if state.terminal_status is not None or event.artifact_refs:
            return self._rejection(state, HamiltonicityReason.MALFORMED_EVENT)
        if state.phase == "awaiting_commit":
            if event.kind != COMMIT_EVENT_KIND:
                return self._rejection(state, HamiltonicityReason.MALFORMED_EVENT)
            commitments = _parse_commit(event.payload, source.num_vertices)
            if commitments is None:
                return self._rejection(state, HamiltonicityReason.MALFORMED_EVENT)
            bits = tuple(
                context.random_int(
                    tag=(
                        f"{self.randomness_domain}/{generated_case.case_id}/"
                        f"hamiltonicity/lane-{lane}/bit"
                    ),
                    lower_inclusive=0,
                    upper_exclusive=2,
                )
                for lane in range(CHALLENGE_LANES)
            )
            next_state = HamiltonicityProtocolState(
                phase="awaiting_open",
                committed_graphs=commitments,
                challenge_bits=bits,
                events_processed=state.events_processed + 1,
            )
            return Transition(
                new_state=next_state,
                reply=ProtocolReply(kind=CHALLENGE_REPLY_KIND, payload={"bits": list(bits)}),
                milestones={"completed_protocol_fraction": 0.5},
                public_state={"phase": "awaiting_open", "commitment_count": CHALLENGE_LANES},
            )

        if state.phase != "awaiting_open" or event.kind != OPEN_EVENT_KIND:
            return self._rejection(state, HamiltonicityReason.MALFORMED_EVENT)
        openings = _parse_opening_payload(event.payload, source.num_vertices)
        if openings is None:
            return self._rejection(state, HamiltonicityReason.MALFORMED_EVENT)
        if not all(
            _opening_is_valid(
                source=source,
                commitment=commitment,
                challenge_bit=bit,
                opening=opening,
            )
            for commitment, bit, opening in zip(
                state.committed_graphs, state.challenge_bits, openings, strict=True
            )
        ):
            return self._rejection(state, HamiltonicityReason.INVALID_OPENING)
        accepted = HamiltonicityProtocolState(
            phase="terminal",
            terminal_status=TerminalStatus.ACCEPT,
            reason_code=ErrorCode.PROTOCOL_ACCEPT,
            events_processed=state.events_processed + 1,
        )
        return Transition(
            new_state=accepted,
            terminal_status=TerminalStatus.ACCEPT,
            reason_code=ErrorCode.PROTOCOL_ACCEPT,
            milestones={"completed_protocol_fraction": 1.0},
            public_state={"phase": "terminal", "openings_verified": CHALLENGE_LANES},
        )

    def terminal_metrics(self, *, state: Any) -> Mapping[str, int | float | str]:
        if not isinstance(state, HamiltonicityProtocolState):
            raise TypeError("state is not a HamiltonicityProtocolState")
        metrics: dict[str, int | float | str] = {
            "events_processed": state.events_processed,
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
    def _completed_fraction(state: HamiltonicityProtocolState) -> float:
        successful_events = state.events_processed
        if state.terminal_status == TerminalStatus.REJECT:
            successful_events = max(0, successful_events - 1)
        return min(successful_events / 2, 1.0)

    @staticmethod
    def _rejection(state: HamiltonicityProtocolState, reason_code: str) -> Transition:
        rejected = HamiltonicityProtocolState(
            phase="terminal",
            terminal_status=TerminalStatus.REJECT,
            reason_code=reason_code,
            events_processed=state.events_processed + 1,
        )
        return Transition(
            new_state=rejected,
            terminal_status=TerminalStatus.REJECT,
            reason_code=reason_code,
            milestones={
                "completed_protocol_fraction": HamiltonicityProtocol._completed_fraction(rejected)
            },
            public_state={"phase": "terminal"},
        )
