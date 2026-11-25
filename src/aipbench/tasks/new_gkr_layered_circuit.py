"""600-second GKR layered-circuit evaluation task."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Final

from aipbench.core.models import GeneratedCase
from aipbench.tasks.new_gkr_layered_circuit_cases import CASE_DEFINITIONS, CASE_PARAMETERS
from aipbench.tasks.shared.gkr_layered_circuit import (
    GKRLayeredCircuitProtocol,
    GKRProtocolState,
    GKRReason,
)
from aipbench.tasks.shared.gkr_layered_circuit_cases.common import (
    DeterministicStream,
    finalize_blueprint,
    parse_public_instance,
)

TASK_ID: Final = "t2.new_gkr_layered_circuit"
TASK_VERSION: Final = "0.1.0"
CASE_ID: Final = "c01"
CASE_IDS: Final[tuple[str, ...]] = tuple(CASE_PARAMETERS)

TASK_MANIFEST: Final[Mapping[str, Any]] = {
    "id": TASK_ID,
    "version": TASK_VERSION,
    "tier": 2,
    "title": "new GKR Layered Arithmetic-Circuit Evaluation",
    "plugin": {"entrypoint": "aipbench.tasks.new_gkr_layered_circuit:create_task"},
    "protocol": {
        "api_version": "aip/1",
        "mode": "interactive",
        "public_coin": True,
        "one_shot_eval": True,
        "max_events": 513,
        "participant_feedback": {"dev": "verbose", "eval": "minimal"},
    },
    "randomness": {
        "model": "committed_prg",
        "reveal_on_terminal": True,
        "domain_separation": "required",
    },
    "instance": {
        "public_schema": (
            "tasks/tier2_interactive/new_gkr_layered_circuit/schemas/public_instance.schema.json"
        ),
        "private_schema": (
            "tasks/tier2_interactive/new_gkr_layered_circuit/schemas/private_instance.schema.json"
        ),
    },
    "resources": {
        "wall_time_seconds": 600,
        "cpu_cores": 4,
        "memory_mb": 4096,
        "disk_mb": 4096,
        "max_artifact_bytes": 67_108_864,
        "max_events": 513,
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
        "class": "public_coin_interactive",
        "statement": "false output claims are accepted with probability below 2^-49",
        "error_bound": "<2^-49",
    },
}


class NewGKRLayeredCircuitGenerator:
    """Dispatch the seven scaled builders under a separate task identity."""

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
            raise ValueError(f"unsupported new GKR case: {case_id}")
        unknown = set(case_parameters) - set(definition.parameters)
        if unknown:
            raise ValueError(f"unsupported new GKR parameters: {', '.join(sorted(unknown))}")
        parameters = dict(definition.parameters)
        parameters.update(case_parameters)
        stream = DeterministicStream(instance_seed)
        blueprint = definition.builder(stream, parameters)
        public_instance, metadata = finalize_blueprint(blueprint=blueprint, stream=stream)
        parse_public_instance(public_instance)
        return GeneratedCase(
            task_id=TASK_ID,
            task_version=TASK_VERSION,
            case_id=case_id,
            public_instance=public_instance,
            private_instance={},
            generation_metadata=metadata,
        )


class NewGKRLayeredCircuitProtocol(GKRLayeredCircuitProtocol):
    """The shared GKR verifier under an independent identity and coin domain."""

    task_id = TASK_ID
    task_version = TASK_VERSION
    schema_root = "tasks/tier2_interactive/new_gkr_layered_circuit/schemas"
    randomness_domain = TASK_ID


VIRTUAL_AGENTS: Final[Mapping[str, Any]] = {}


@dataclass(frozen=True)
class NewGKRLayeredCircuitTaskPlugin:
    manifest: Mapping[str, Any]
    case_parameters: Mapping[str, Mapping[str, Any]]
    generator: NewGKRLayeredCircuitGenerator
    protocol: NewGKRLayeredCircuitProtocol


def create_task() -> NewGKRLayeredCircuitTaskPlugin:
    return NewGKRLayeredCircuitTaskPlugin(
        manifest=TASK_MANIFEST,
        case_parameters=CASE_PARAMETERS,
        generator=NewGKRLayeredCircuitGenerator(),
        protocol=NewGKRLayeredCircuitProtocol(),
    )


__all__ = [
    "CASE_ID",
    "CASE_IDS",
    "CASE_PARAMETERS",
    "GKRProtocolState",
    "GKRReason",
    "NewGKRLayeredCircuitGenerator",
    "NewGKRLayeredCircuitProtocol",
    "NewGKRLayeredCircuitTaskPlugin",
    "TASK_ID",
    "TASK_MANIFEST",
    "TASK_VERSION",
    "VIRTUAL_AGENTS",
    "create_task",
]
