"""600-second Boolean-hypercube Sum-Check task."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Final

from aipbench.core.models import GeneratedCase
from aipbench.tasks.new_boolean_hypercube_sumcheck_cases import (
    CASE_DEFINITIONS,
    CASE_PARAMETERS,
    DeterministicStream,
    finalize_blueprint,
)
from aipbench.tasks.shared.boolean_hypercube_sumcheck import (
    BooleanHypercubeSumCheckProtocol,
    SumCheckProtocolState,
    SumCheckReason,
)

TASK_ID: Final = "t2.new_boolean_hypercube_sumcheck"
TASK_VERSION: Final = "0.1.0"
CASE_ID: Final = "c01"
CASE_IDS: Final[tuple[str, ...]] = tuple(CASE_PARAMETERS)

TASK_MANIFEST: Final[Mapping[str, Any]] = {
    "id": TASK_ID,
    "version": TASK_VERSION,
    "tier": 2,
    "title": "new Boolean-Hypercube Polynomial Sum-Check",
    "plugin": {"entrypoint": "aipbench.tasks.new_boolean_hypercube_sumcheck:create_task"},
    "protocol": {
        "api_version": "aip/1",
        "mode": "interactive",
        "public_coin": True,
        "one_shot_eval": True,
        "max_events": 401,
        "participant_feedback": {"dev": "verbose", "eval": "minimal"},
    },
    "randomness": {
        "model": "committed_prg",
        "reveal_on_terminal": True,
        "domain_separation": "required",
    },
    "instance": {
        "public_schema": (
            "tasks/tier2_interactive/new_boolean_hypercube_sumcheck/schemas/"
            "public_instance.schema.json"
        ),
        "private_schema": (
            "tasks/tier2_interactive/new_boolean_hypercube_sumcheck/schemas/"
            "private_instance.schema.json"
        ),
    },
    "resources": {
        "wall_time_seconds": 600,
        "cpu_cores": 4,
        "memory_mb": 4096,
        "disk_mb": 4096,
        "max_artifact_bytes": 67_108_864,
        "max_events": 401,
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
        "statement": "a false sum is accepted with probability at most 5m/(2^61-1)",
        "error_bound": "5m/(2^61-1) < 2^-50 for m <= 400",
    },
}


class NewBooleanHypercubeSumCheckGenerator:
    """Dispatch the seven factor-model builders."""

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
            raise ValueError(f"unsupported new Sum-Check case: {case_id}")
        unknown = set(case_parameters) - set(definition.parameters)
        if unknown:
            raise ValueError(f"unsupported new Sum-Check parameters: {', '.join(sorted(unknown))}")
        parameters = dict(definition.parameters)
        parameters.update(case_parameters)
        stream = DeterministicStream(instance_seed)
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


class NewBooleanHypercubeSumCheckProtocol(BooleanHypercubeSumCheckProtocol):
    """The shared LFKN verifier under an independent task identity and coin domain."""

    task_id = TASK_ID
    task_version = TASK_VERSION
    schema_root = "tasks/tier2_interactive/new_boolean_hypercube_sumcheck/schemas"
    randomness_domain = TASK_ID


VIRTUAL_AGENTS: Final[Mapping[str, Any]] = {}


@dataclass(frozen=True)
class NewBooleanHypercubeSumCheckTaskPlugin:
    manifest: Mapping[str, Any]
    case_parameters: Mapping[str, Mapping[str, Any]]
    generator: NewBooleanHypercubeSumCheckGenerator
    protocol: NewBooleanHypercubeSumCheckProtocol


def create_task() -> NewBooleanHypercubeSumCheckTaskPlugin:
    return NewBooleanHypercubeSumCheckTaskPlugin(
        manifest=TASK_MANIFEST,
        case_parameters=CASE_PARAMETERS,
        generator=NewBooleanHypercubeSumCheckGenerator(),
        protocol=NewBooleanHypercubeSumCheckProtocol(),
    )


__all__ = [
    "CASE_ID",
    "CASE_IDS",
    "CASE_PARAMETERS",
    "NewBooleanHypercubeSumCheckGenerator",
    "NewBooleanHypercubeSumCheckProtocol",
    "NewBooleanHypercubeSumCheckTaskPlugin",
    "SumCheckProtocolState",
    "SumCheckReason",
    "TASK_ID",
    "TASK_MANIFEST",
    "TASK_VERSION",
    "VIRTUAL_AGENTS",
    "create_task",
]
