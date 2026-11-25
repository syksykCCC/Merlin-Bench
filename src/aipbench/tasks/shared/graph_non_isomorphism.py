"""Shared primitives used by the current Merlin-Bench tasks."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, TypeGuard

from aipbench.core.errors import ErrorCode
from aipbench.core.models import (
    GeneratedCase,
    ParticipantEvent,
    ProtocolReply,
    TerminalStatus,
    Transition,
)
from aipbench.core.protocol import ArthurContext, ParticipantClient, VirtualAgent
from aipbench.tasks.shared.graph_non_isomorphism_cases.common import (
    parse_public_graph,
    public_graph_fingerprint,
    relabel_graph,
    serialize_graph,
)

TASK_ID: Final = "t2.new_graph_non_isomorphism"

TASK_VERSION: Final = "0.1.0"

CHALLENGE_LANES: Final = 24

BEGIN_EVENT_KIND: Final = "gni.begin"

CHALLENGE_REPLY_KIND: Final = "gni.challenge"

RESPONSE_EVENT_KIND: Final = "gni.response"

_PUBLIC_INSTANCE_FIELDS: Final = frozenset(
    {"format_version", "graph_model", "challenge_lanes", "graphs"}
)

_RESPONSE_FIELDS: Final = frozenset({"source_bits"})


class GNIReason:
    """Stable participant-visible terminal reasons for this protocol."""

    MALFORMED_EVENT = "GNI_MALFORMED_EVENT"
    SOURCE_BITS_INCORRECT = "GNI_SOURCE_BITS_INCORRECT"


def _is_integer(value: object) -> TypeGuard[int]:
    """Recognize JSON integers while rejecting Python/JSON booleans."""

    return isinstance(value, int) and not isinstance(value, bool)


def _validate_public_instance(public_instance: Mapping[str, Any]) -> tuple[Any, Any]:
    """Strictly parse the two public colored simple source graphs."""

    if set(public_instance) != _PUBLIC_INSTANCE_FIELDS:
        raise ValueError("malformed generated Graph Non-Isomorphism instance")
    if public_instance.get("format_version") != "aip-gni-instance/1":
        raise ValueError("unsupported Graph Non-Isomorphism instance format")
    if public_instance.get("graph_model") != "undirected_simple_vertex_colored":
        raise ValueError("unsupported Graph Non-Isomorphism graph model")
    if public_instance.get("challenge_lanes") != CHALLENGE_LANES:
        raise ValueError(f"Graph Non-Isomorphism requires {CHALLENGE_LANES} challenge lanes")

    raw_graphs = public_instance.get("graphs")
    if not isinstance(raw_graphs, list) or len(raw_graphs) != 2:
        raise ValueError("Graph Non-Isomorphism requires exactly two source graphs")
    first = parse_public_graph(raw_graphs[0])
    second = parse_public_graph(raw_graphs[1])
    if first.num_vertices != second.num_vertices:
        raise ValueError("the two Graph Non-Isomorphism sources must have equal order")
    return first, second


@dataclass(frozen=True)
class GNIProtocolState:
    """Arthur-private state; ``source_bits`` never enters public state."""

    phase: str = "awaiting_begin"
    source_bits: tuple[int, ...] = ()
    terminal_status: TerminalStatus | None = None
    reason_code: str | None = None
    events_processed: int = 0


def _uniform_permutation(
    *,
    context: ArthurContext,
    task_id: str = TASK_ID,
    case_id: str,
    lane: int,
    order: int,
) -> list[int]:
    """Sample ``old_vertex -> new_vertex`` uniformly by Fisher--Yates."""

    permutation = list(range(order))
    for position in range(order - 1, 0, -1):
        other = context.random_int(
            tag=(f"{task_id}/{case_id}/gni/lane-{lane}/permutation/position-{position}"),
            lower_inclusive=0,
            upper_exclusive=position + 1,
        )
        permutation[position], permutation[other] = permutation[other], permutation[position]
    return permutation


def _make_challenge(
    *,
    sources: tuple[Any, Any],
    generated_case: GeneratedCase,
    context: ArthurContext,
    task_id: str = TASK_ID,
) -> tuple[tuple[int, ...], list[Mapping[str, Any]]]:
    source_bits: list[int] = []
    challenge_graphs: list[Mapping[str, Any]] = []
    order = sources[0].num_vertices
    for lane in range(CHALLENGE_LANES):
        source_bit = context.random_int(
            tag=f"{task_id}/{generated_case.case_id}/gni/lane-{lane}/source-bit",
            lower_inclusive=0,
            upper_exclusive=2,
        )
        permutation = _uniform_permutation(
            context=context,
            task_id=task_id,
            case_id=generated_case.case_id,
            lane=lane,
            order=order,
        )
        challenge = relabel_graph(sources[source_bit], permutation)
        # serialize_graph normalizes every edge and sorts the edge array.  It
        # intentionally does not preserve the selected source's array order.
        challenge_graphs.append(serialize_graph(challenge))
        source_bits.append(source_bit)
    return tuple(source_bits), challenge_graphs


def _parse_source_bits(payload: object) -> tuple[int, ...] | None:
    if not isinstance(payload, Mapping) or set(payload) != _RESPONSE_FIELDS:
        return None
    raw_bits = payload.get("source_bits")
    if not isinstance(raw_bits, list) or len(raw_bits) != CHALLENGE_LANES:
        return None
    if not all(_is_integer(bit) and bit in (0, 1) for bit in raw_bits):
        return None
    return tuple(raw_bits)


class GraphNonIsomorphismProtocol:
    """Two-event private-coin hidden-source protocol for colored GNI."""

    task_id = TASK_ID
    task_version = TASK_VERSION

    def initialize(
        self, *, generated_case: GeneratedCase, context: ArthurContext
    ) -> GNIProtocolState:
        del context
        self._validate_task_identity(generated_case)
        _validate_public_instance(generated_case.public_instance)
        return GNIProtocolState()

    def public_protocol_description(self, *, generated_case: GeneratedCase) -> Mapping[str, Any]:
        self._validate_task_identity(generated_case)
        sources = _validate_public_instance(generated_case.public_instance)
        return {
            "api_version": "aip/1",
            "mode": "interactive",
            "public_coin": False,
            "initial_event_kinds": [BEGIN_EVENT_KIND],
            "event_schemas": {
                BEGIN_EVENT_KIND: {
                    "schema_ref": (
                        "tasks/tier2_interactive/new_graph_non_isomorphism/schemas/begin.schema.json"
                    )
                },
                RESPONSE_EVENT_KIND: {
                    "schema_ref": (
                        "tasks/tier2_interactive/new_graph_non_isomorphism/schemas/response.schema.json"
                    )
                },
            },
            "reply_schemas": {
                CHALLENGE_REPLY_KIND: {
                    "schema_ref": (
                        "tasks/tier2_interactive/new_graph_non_isomorphism/schemas/"
                        "challenge.schema.json"
                    )
                }
            },
            "public_parameters": {
                "num_vertices": sources[0].num_vertices,
                "challenge_lanes": CHALLENGE_LANES,
                "response_event_kind": RESPONSE_EVENT_KIND,
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
        if not isinstance(state, GNIProtocolState):
            raise TypeError("state is not a GNIProtocolState")
        self._validate_task_identity(generated_case)
        sources = _validate_public_instance(generated_case.public_instance)

        if state.terminal_status is not None or event.artifact_refs:
            return self._rejection(state, GNIReason.MALFORMED_EVENT)
        if state.phase == "awaiting_begin":
            if (
                event.kind != BEGIN_EVENT_KIND
                or not isinstance(event.payload, Mapping)
                or set(event.payload)
            ):
                return self._rejection(state, GNIReason.MALFORMED_EVENT)
            source_bits, challenge_graphs = _make_challenge(
                sources=sources,
                generated_case=generated_case,
                context=context,
                task_id=self.task_id,
            )
            next_state = GNIProtocolState(
                phase="awaiting_response",
                source_bits=source_bits,
                events_processed=state.events_processed + 1,
            )
            return Transition(
                new_state=next_state,
                reply=ProtocolReply(
                    kind=CHALLENGE_REPLY_KIND,
                    payload={"graphs": challenge_graphs},
                ),
                milestones={"completed_protocol_fraction": 0.5},
                public_state={
                    "phase": "awaiting_response",
                    "challenge_lanes": CHALLENGE_LANES,
                },
            )

        if state.phase != "awaiting_response" or event.kind != RESPONSE_EVENT_KIND:
            return self._rejection(state, GNIReason.MALFORMED_EVENT)
        response_bits = _parse_source_bits(event.payload)
        if response_bits is None:
            return self._rejection(state, GNIReason.MALFORMED_EVENT)
        if response_bits != state.source_bits:
            return self._rejection(state, GNIReason.SOURCE_BITS_INCORRECT)

        accepted = GNIProtocolState(
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
            public_state={"phase": "terminal", "challenge_lanes_answered": CHALLENGE_LANES},
        )

    def terminal_metrics(self, *, state: Any) -> Mapping[str, int | float | str]:
        if not isinstance(state, GNIProtocolState):
            raise TypeError("state is not a GNIProtocolState")
        metrics: dict[str, int | float | str] = {
            "events_processed": state.events_processed,
            "accepted": int(state.terminal_status == TerminalStatus.ACCEPT),
            "completed_protocol_fraction": min(state.events_processed / 2, 1.0),
        }
        if state.reason_code is not None:
            metrics["reason_code"] = state.reason_code
        return metrics

    @staticmethod
    def _validate_task_identity(generated_case: GeneratedCase) -> None:
        if generated_case.task_id != TASK_ID or generated_case.task_version != TASK_VERSION:
            raise ValueError("generated case does not belong to this task plugin")

    @staticmethod
    def _rejection(state: GNIProtocolState, reason_code: str) -> Transition:
        rejected = GNIProtocolState(
            phase="terminal",
            terminal_status=TerminalStatus.REJECT,
            reason_code=reason_code,
            events_processed=state.events_processed + 1,
        )
        return Transition(
            new_state=rejected,
            terminal_status=TerminalStatus.REJECT,
            reason_code=reason_code,
            milestones={"completed_protocol_fraction": min((state.events_processed + 1) / 2, 1.0)},
            public_state={"phase": "terminal"},
        )


def _participant_instance(client: ParticipantClient) -> Mapping[str, Any]:
    response = client.get_instance()
    nested = response.get("public_instance")
    return nested if isinstance(nested, Mapping) else response


def _reply_graphs(response: Mapping[str, Any]) -> list[Any]:
    raw_reply = response.get("reply")
    if isinstance(raw_reply, Mapping):
        if raw_reply.get("kind") != CHALLENGE_REPLY_KIND:
            raise RuntimeError("Arthur returned an unexpected GNI reply kind")
        payload = raw_reply.get("payload")
        if isinstance(payload, Mapping):
            raw_graphs = payload.get("graphs")
            if isinstance(raw_graphs, list) and len(raw_graphs) == CHALLENGE_LANES:
                return raw_graphs
    # Small fake clients may return the reply payload directly.
    raw_graphs = response.get("graphs")
    if isinstance(raw_graphs, list) and len(raw_graphs) == CHALLENGE_LANES:
        return raw_graphs
    raise RuntimeError("Arthur response did not contain 24 GNI challenge graphs")


def _decode_source_bits(
    public_instance: Mapping[str, Any], challenge_graphs: list[Any]
) -> list[int]:
    """Classify challenges using only public graph fingerprints."""

    sources = _validate_public_instance(public_instance)
    source_fingerprints = tuple(public_graph_fingerprint(source) for source in sources)
    result: list[int] = []
    for raw_challenge in challenge_graphs:
        challenge = parse_public_graph(raw_challenge)
        if challenge.num_vertices != sources[0].num_vertices:
            raise RuntimeError("Arthur returned a challenge graph of the wrong order")
        fingerprint = public_graph_fingerprint(challenge)
        matches = [
            index for index, source in enumerate(source_fingerprints) if fingerprint == source
        ]
        if len(matches) != 1:
            raise RuntimeError("public GNI decoder could not identify a unique source graph")
        result.append(matches[0])
    return result


class HonestGraphNonIsomorphismAgent:
    """Reference prover that never reads case IDs or private generator data."""

    agent_id = "virtual-honest"

    def run(self, *, client: ParticipantClient, workspace: Path) -> None:
        del workspace
        public_instance = _participant_instance(client)
        begin_response = client.submit_event(sequence=0, kind=BEGIN_EVENT_KIND, payload={})
        source_bits = _decode_source_bits(public_instance, _reply_graphs(begin_response))
        client.submit_event(
            sequence=1,
            kind=RESPONSE_EVENT_KIND,
            payload={"source_bits": source_bits},
        )


class WrongSourceBitGraphNonIsomorphismAgent:
    """Negative control: decode honestly and flip exactly one source bit."""

    agent_id = "virtual-wrong-source-bit"

    def run(self, *, client: ParticipantClient, workspace: Path) -> None:
        del workspace
        public_instance = _participant_instance(client)
        begin_response = client.submit_event(sequence=0, kind=BEGIN_EVENT_KIND, payload={})
        source_bits = _decode_source_bits(public_instance, _reply_graphs(begin_response))
        source_bits[0] ^= 1
        client.submit_event(
            sequence=1,
            kind=RESPONSE_EVENT_KIND,
            payload={"source_bits": source_bits},
        )


_VIRTUAL_AGENT_LIST: Final[tuple[VirtualAgent, ...]] = (
    HonestGraphNonIsomorphismAgent(),
    WrongSourceBitGraphNonIsomorphismAgent(),
)

VIRTUAL_AGENTS: Final[Mapping[str, VirtualAgent]] = {
    agent.agent_id: agent for agent in _VIRTUAL_AGENT_LIST
}
