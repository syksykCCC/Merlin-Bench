"""Seven cases for the private-coin GNI hidden-source task."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Final

from aipbench.core.models import GeneratedCase
from aipbench.tasks.new_graph_non_isomorphism_cases import (
    CASE_DEFINITIONS,
    CASE_PARAMETERS,
    NewDeterministicStream,
    finalize_blueprint,
)
from aipbench.tasks.shared.graph_non_isomorphism import (
    BEGIN_EVENT_KIND,
    CHALLENGE_LANES,
    CHALLENGE_REPLY_KIND,
    RESPONSE_EVENT_KIND,
    GNIProtocolState,
    GNIReason,
    GraphNonIsomorphismProtocol,
)
from aipbench.tasks.shared.graph_non_isomorphism_cases.common import parse_public_graph

TASK_ID: Final = "t2.new_graph_non_isomorphism"
TASK_VERSION: Final = "0.1.0"
CASE_IDS: Final[tuple[str, ...]] = tuple(CASE_PARAMETERS)


TASK_MANIFEST: Final[Mapping[str, Any]] = {
    "id": TASK_ID,
    "version": TASK_VERSION,
    "tier": 2,
    "title": "new Graph Non-Isomorphism Hidden-Source Challenge",
    "plugin": {"entrypoint": "aipbench.tasks.new_graph_non_isomorphism:create_task"},
    "protocol": {
        "api_version": "aip/1",
        "mode": "interactive",
        "public_coin": False,
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
            "tasks/tier2_interactive/new_graph_non_isomorphism/schemas/public_instance.schema.json"
        ),
        "private_schema": (
            "tasks/tier2_interactive/new_graph_non_isomorphism/schemas/private_instance.schema.json"
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
        "class": "private_coin_interactive",
        "statement": "isomorphic source pairs are accepted with probability at most 2^-24",
        "error_bound": "2^-24",
    },
}


def _validate_public_instance(public_instance: Mapping[str, Any]) -> tuple[Any, Any]:
    if set(public_instance) != {
        "format_version",
        "graph_model",
        "challenge_lanes",
        "graphs",
    }:
        raise ValueError("malformed generated new GNI instance")
    if public_instance.get("format_version") != "aip-gni-instance/1":
        raise ValueError("unsupported new GNI instance format")
    if public_instance.get("graph_model") != "undirected_simple_vertex_colored":
        raise ValueError("unsupported new GNI graph model")
    if public_instance.get("challenge_lanes") != CHALLENGE_LANES:
        raise ValueError("new GNI requires exactly 24 challenge lanes")
    raw_graphs = public_instance.get("graphs")
    if not isinstance(raw_graphs, list) or len(raw_graphs) != 2:
        raise ValueError("new GNI requires exactly two public source graphs")
    sources = (parse_public_graph(raw_graphs[0]), parse_public_graph(raw_graphs[1]))
    if sources[0].num_vertices != sources[1].num_vertices:
        raise ValueError("new GNI source orders differ")
    return sources


class NewGraphNonIsomorphismGenerator:
    def generate(
        self,
        *,
        instance_seed: bytes,
        case_id: str,
        case_parameters: Mapping[str, Any],
    ) -> GeneratedCase:
        definition = CASE_DEFINITIONS.get(case_id)
        if definition is None:
            raise ValueError(f"unsupported new GNI case: {case_id}")
        parameters = dict(definition.parameters)
        parameters.update(case_parameters)
        stream = NewDeterministicStream(instance_seed)
        finalized = finalize_blueprint(
            case_id=case_id,
            blueprint=definition.builder(stream, parameters),
            stream=stream,
        )
        _validate_public_instance(finalized.public_instance)
        return GeneratedCase(
            task_id=TASK_ID,
            task_version=TASK_VERSION,
            case_id=case_id,
            public_instance=finalized.public_instance,
            private_instance=finalized.private_instance,
            generation_metadata=finalized.generation_metadata,
        )


class NewGraphNonIsomorphismProtocol(GraphNonIsomorphismProtocol):
    task_id = TASK_ID
    task_version = TASK_VERSION

    def public_protocol_description(self, *, generated_case: GeneratedCase) -> Mapping[str, Any]:
        self._validate_task_identity(generated_case)
        sources = _validate_public_instance(generated_case.public_instance)
        schema_root = "tasks/tier2_interactive/new_graph_non_isomorphism/schemas"
        return {
            "api_version": "aip/1",
            "mode": "interactive",
            "public_coin": False,
            "initial_event_kinds": [BEGIN_EVENT_KIND],
            "event_schemas": {
                BEGIN_EVENT_KIND: {"schema_ref": f"{schema_root}/begin.schema.json"},
                RESPONSE_EVENT_KIND: {"schema_ref": f"{schema_root}/response.schema.json"},
            },
            "reply_schemas": {
                CHALLENGE_REPLY_KIND: {"schema_ref": f"{schema_root}/challenge.schema.json"}
            },
            "public_parameters": {
                "num_vertices": sources[0].num_vertices,
                "challenge_lanes": CHALLENGE_LANES,
                "response_event_kind": RESPONSE_EVENT_KIND,
                "soundness_error": "2^-24",
            },
        }

    @staticmethod
    def _validate_task_identity(generated_case: GeneratedCase) -> None:
        if generated_case.task_id != TASK_ID or generated_case.task_version != TASK_VERSION:
            raise ValueError("generated case does not belong to the new GNI task")


@dataclass(frozen=True)
class NewGraphNonIsomorphismTaskPlugin:
    manifest: Mapping[str, Any]
    case_parameters: Mapping[str, Mapping[str, Any]]
    generator: NewGraphNonIsomorphismGenerator
    protocol: NewGraphNonIsomorphismProtocol


VIRTUAL_AGENTS: Final[Mapping[str, Any]] = {}


def create_task() -> NewGraphNonIsomorphismTaskPlugin:
    return NewGraphNonIsomorphismTaskPlugin(
        manifest=TASK_MANIFEST,
        case_parameters=CASE_PARAMETERS,
        generator=NewGraphNonIsomorphismGenerator(),
        protocol=NewGraphNonIsomorphismProtocol(),
    )


__all__ = [
    "CASE_IDS",
    "CASE_PARAMETERS",
    "GNIProtocolState",
    "GNIReason",
    "NewGraphNonIsomorphismGenerator",
    "NewGraphNonIsomorphismProtocol",
    "TASK_ID",
    "TASK_MANIFEST",
    "TASK_VERSION",
    "VIRTUAL_AGENTS",
    "create_task",
]
