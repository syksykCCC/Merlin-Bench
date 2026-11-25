"""Independent 600-second Weighted Partial MaxSAT assignment task."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Final

from aipbench.core.models import GeneratedCase
from aipbench.tasks.new_maxsat_cases import (
    CASE_DEFINITIONS,
    CASE_PARAMETERS,
    NewMaxSatStream,
    finalize_blueprint,
)
from aipbench.tasks.shared.weighted_partial_maxsat import (
    ASSIGNMENT_EVENT_KIND,
    VIRTUAL_AGENTS,
    MaxSatProtocolState,
    MaxSatReason,
    WeightedPartialMaxSatProtocol,
    evaluate_assignment,
)

TASK_ID: Final = "t1.new_weighted_partial_maxsat"
TASK_VERSION: Final = "0.1.0"
CASE_IDS: Final[tuple[str, ...]] = tuple(CASE_PARAMETERS)

TASK_MANIFEST: Final[Mapping[str, Any]] = {
    "id": TASK_ID,
    "version": TASK_VERSION,
    "tier": 1,
    "title": "New Weighted Partial MaxSAT Assignment",
    "plugin": {"entrypoint": "aipbench.tasks.new_weighted_partial_maxsat:create_task"},
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
        "public_schema": (
            "tasks/tier1_np/new_weighted_partial_maxsat/schemas/public_instance.schema.json"
        ),
        "private_schema": (
            "tasks/tier1_np/new_weighted_partial_maxsat/schemas/private_instance.schema.json"
        ),
    },
    "resources": {
        "wall_time_seconds": 600,
        "cpu_cores": 4,
        "memory_mb": 4096,
        "disk_mb": 4096,
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
    "scoring": {"primary": "binary_accept", "partial_progress": "assignment_submitted"},
    "soundness": {
        "class": "deterministic_certificate",
        "statement": "all hard clauses satisfied and exact soft cost at most threshold",
    },
}


class NewWeightedPartialMaxSatGenerator:
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
            raise ValueError(f"unsupported new weighted-partial-MaxSAT case: {case_id}")
        parameters = dict(definition.parameters)
        parameters.update(case_parameters)
        stream = NewMaxSatStream(instance_seed)
        finalized = finalize_blueprint(
            blueprint=definition.builder(stream, parameters),
            stream=stream,
        )
        return GeneratedCase(
            task_id=TASK_ID,
            task_version=TASK_VERSION,
            case_id=case_id,
            public_instance=finalized.public_instance,
            private_instance=finalized.private_instance,
            generation_metadata={
                **dict(finalized.generation_metadata),
                "generator": f"new-weighted-partial-maxsat/{case_id}/v1",
                "case_id": case_id,
            },
        )


class NewWeightedPartialMaxSatProtocol(WeightedPartialMaxSatProtocol):
    task_id = TASK_ID
    task_version = TASK_VERSION

    @staticmethod
    def _validate_task_identity(generated_case: GeneratedCase) -> None:
        if generated_case.task_id != TASK_ID or generated_case.task_version != TASK_VERSION:
            raise ValueError("generated case does not belong to the new MaxSAT task")

    def public_protocol_description(self, *, generated_case: GeneratedCase) -> Mapping[str, Any]:
        description = dict(super().public_protocol_description(generated_case=generated_case))
        event_schemas = dict(description["event_schemas"])
        event_schemas[ASSIGNMENT_EVENT_KIND] = {
            "schema_ref": (
                "tasks/tier1_np/new_weighted_partial_maxsat/schemas/assignment.schema.json"
            )
        }
        description["event_schemas"] = event_schemas
        return description


@dataclass(frozen=True)
class NewWeightedPartialMaxSatTaskPlugin:
    manifest: Mapping[str, Any]
    case_parameters: Mapping[str, Mapping[str, Any]]
    generator: NewWeightedPartialMaxSatGenerator
    protocol: NewWeightedPartialMaxSatProtocol


def create_task() -> NewWeightedPartialMaxSatTaskPlugin:
    return NewWeightedPartialMaxSatTaskPlugin(
        manifest=TASK_MANIFEST,
        case_parameters=CASE_PARAMETERS,
        generator=NewWeightedPartialMaxSatGenerator(),
        protocol=NewWeightedPartialMaxSatProtocol(),
    )


__all__ = [
    "ASSIGNMENT_EVENT_KIND",
    "CASE_IDS",
    "CASE_PARAMETERS",
    "MaxSatProtocolState",
    "MaxSatReason",
    "NewWeightedPartialMaxSatGenerator",
    "NewWeightedPartialMaxSatProtocol",
    "NewWeightedPartialMaxSatTaskPlugin",
    "TASK_ID",
    "TASK_MANIFEST",
    "TASK_VERSION",
    "VIRTUAL_AGENTS",
    "create_task",
    "evaluate_assignment",
]
