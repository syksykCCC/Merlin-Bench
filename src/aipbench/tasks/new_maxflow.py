"""Independent 600-second Max-Flow / Min-Cut certificate task."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Final

from aipbench.core.models import GeneratedCase
from aipbench.tasks.new_maxflow_cases import (
    CASE_DEFINITIONS,
    CASE_PARAMETERS,
    NewMaxFlowStream,
    finalize_blueprint,
)
from aipbench.tasks.shared.maxflow import (
    CERTIFICATE_EVENT_KIND,
    VIRTUAL_AGENTS,
    MaxFlowProtocol,
    MaxFlowProtocolState,
    MaxFlowReason,
    solve_maxflow,
)

TASK_ID: Final = "t1.new_maxflow_min_cut"
TASK_VERSION: Final = "0.1.0"
CASE_IDS: Final[tuple[str, ...]] = tuple(CASE_PARAMETERS)

TASK_MANIFEST: Final[Mapping[str, Any]] = {
    "id": TASK_ID,
    "version": TASK_VERSION,
    "tier": 1,
    "title": "New Max-Flow / Min-Cut Certificates",
    "plugin": {"entrypoint": "aipbench.tasks.new_maxflow:create_task"},
    "protocol": {
        "api_version": "aip/1",
        "mode": "one_shot",
        "public_coin": False,
        "one_shot_eval": True,
        "max_events": 1,
        "participant_feedback": {"dev": "verbose", "eval": "minimal"},
    },
    "randomness": {
        "model": "committed_prg",
        "reveal_on_terminal": True,
        "domain_separation": "required",
    },
    "instance": {
        "public_schema": ("tasks/tier1_np/new_maxflow_min_cut/schemas/public_instance.schema.json"),
        "private_schema": (
            "tasks/tier1_np/new_maxflow_min_cut/schemas/private_instance.schema.json"
        ),
    },
    "resources": {
        "wall_time_seconds": 600,
        "cpu_cores": 2,
        "memory_mb": 512,
        "disk_mb": 512,
        "max_artifact_bytes": 8_388_608,
        "max_events": 1,
    },
    "audit": {
        "replay_mode": "strict",
        "require_signature": True,
        "require_seed_commitment": True,
        "require_instance_digest": True,
        "require_event_chain": True,
        "require_seed_reveal": True,
    },
    "scoring": {"primary": "binary_accept", "partial_progress": "certificate_submitted"},
    "soundness": {
        "class": "deterministic_certificate",
        "statement": "exact primal feasibility plus equal-capacity dual cut",
    },
}


class NewMaxFlowGenerator:
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
            raise ValueError(f"unsupported new max-flow case: {case_id}")
        parameters = dict(definition.parameters)
        parameters.update(case_parameters)
        stream = NewMaxFlowStream(instance_seed)
        finalized = finalize_blueprint(
            case_id=case_id,
            blueprint=definition.builder(stream, parameters),
            stream=stream,
        )
        return GeneratedCase(
            task_id=TASK_ID,
            task_version=TASK_VERSION,
            case_id=case_id,
            public_instance=finalized.public_instance,
            private_instance=finalized.private_instance,
            generation_metadata=finalized.generation_metadata,
        )


class NewMaxFlowProtocol(MaxFlowProtocol):
    """The established primal/dual relation under the new task identity."""

    task_id = TASK_ID
    task_version = TASK_VERSION

    @staticmethod
    def _validate_task_identity(generated_case: GeneratedCase) -> None:
        if generated_case.task_id != TASK_ID or generated_case.task_version != TASK_VERSION:
            raise ValueError("generated case does not belong to the new max-flow task")

    def public_protocol_description(self, *, generated_case: GeneratedCase) -> Mapping[str, Any]:
        description = dict(super().public_protocol_description(generated_case=generated_case))
        event_schemas = dict(description["event_schemas"])
        event_schemas[CERTIFICATE_EVENT_KIND] = {
            "schema_ref": ("tasks/tier1_np/new_maxflow_min_cut/schemas/certificate.schema.json")
        }
        description["event_schemas"] = event_schemas
        return description


@dataclass(frozen=True)
class NewMaxFlowTaskPlugin:
    manifest: Mapping[str, Any]
    case_parameters: Mapping[str, Mapping[str, Any]]
    generator: NewMaxFlowGenerator
    protocol: NewMaxFlowProtocol


def create_task() -> NewMaxFlowTaskPlugin:
    return NewMaxFlowTaskPlugin(
        manifest=TASK_MANIFEST,
        case_parameters=CASE_PARAMETERS,
        generator=NewMaxFlowGenerator(),
        protocol=NewMaxFlowProtocol(),
    )


__all__ = [
    "CASE_IDS",
    "CASE_PARAMETERS",
    "CERTIFICATE_EVENT_KIND",
    "MaxFlowProtocolState",
    "MaxFlowReason",
    "NewMaxFlowGenerator",
    "NewMaxFlowProtocol",
    "NewMaxFlowTaskPlugin",
    "TASK_ID",
    "TASK_MANIFEST",
    "TASK_VERSION",
    "VIRTUAL_AGENTS",
    "create_task",
    "solve_maxflow",
]
