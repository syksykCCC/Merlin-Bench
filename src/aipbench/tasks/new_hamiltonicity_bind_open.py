"""600-second Hamiltonicity bind--challenge--open task."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Final

from aipbench.core.models import GeneratedCase
from aipbench.tasks.new_hamiltonicity_cases import CASE_DEFAULTS, build_case
from aipbench.tasks.shared.hamiltonicity_bind_open import (
    HamiltonicityProtocol,
    HamiltonicityProtocolState,
    HamiltonicityReason,
)
from aipbench.tasks.shared.hamiltonicity_bind_open_cases.common import (
    DeterministicStream,
    finalize_blueprint,
)

TASK_ID: Final = "t2.new_hamiltonicity_bind_open"
TASK_VERSION: Final = "0.1.0"
CASE_ID: Final = "c01"
CASE_IDS: Final[tuple[str, ...]] = tuple(CASE_DEFAULTS)
CASE_PARAMETERS: Final[Mapping[str, Mapping[str, object]]] = CASE_DEFAULTS

TASK_MANIFEST: Final[Mapping[str, Any]] = {
    "id": TASK_ID,
    "version": TASK_VERSION,
    "tier": 2,
    "title": "new Hamiltonicity Bind--Challenge--Open",
    "plugin": {"entrypoint": "aipbench.tasks.new_hamiltonicity_bind_open:create_task"},
    "protocol": {
        "api_version": "aip/1",
        "mode": "interactive",
        "public_coin": True,
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
            "tasks/tier2_interactive/new_hamiltonicity_bind_open/schemas/"
            "public_instance.schema.json"
        ),
        "private_schema": (
            "tasks/tier2_interactive/new_hamiltonicity_bind_open/schemas/"
            "private_instance.schema.json"
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
        "class": "public_coin_interactive",
        "statement": "non-Hamiltonian public graphs are accepted with probability at most 2^-24",
        "error_bound": "2^-24",
    },
}


class NewHamiltonicityGenerator:
    """Dispatch seven scaled public graph distributions."""

    def generate(
        self,
        *,
        instance_seed: bytes,
        case_id: str,
        case_parameters: Mapping[str, Any],
    ) -> GeneratedCase:
        if not isinstance(instance_seed, bytes):
            raise TypeError("instance_seed must be bytes")
        defaults = CASE_PARAMETERS.get(case_id)
        if defaults is None:
            raise ValueError(f"unsupported new Hamiltonicity case: {case_id}")
        if not set(case_parameters).issubset(defaults):
            raise ValueError("unknown new Hamiltonicity case parameter")
        parameters: dict[str, object] = dict(defaults)
        parameters.update(case_parameters)
        stream = DeterministicStream(instance_seed)
        blueprint = build_case(case_id, stream, parameters)
        finalized = finalize_blueprint(case_id=case_id, blueprint=blueprint, stream=stream)
        return GeneratedCase(
            task_id=TASK_ID,
            task_version=TASK_VERSION,
            case_id=case_id,
            public_instance=finalized.public_instance,
            private_instance=finalized.private_instance,
            generation_metadata={
                **finalized.generation_metadata,
                "difficulty_frozen": False,
            },
        )


class NewHamiltonicityProtocol(HamiltonicityProtocol):
    """Shared verifier under an independent identity and coin domain."""

    task_id = TASK_ID
    task_version = TASK_VERSION
    schema_root = "tasks/tier2_interactive/new_hamiltonicity_bind_open/schemas"
    randomness_domain = TASK_ID


VIRTUAL_AGENTS: Final[Mapping[str, Any]] = {}


@dataclass(frozen=True)
class NewHamiltonicityTaskPlugin:
    manifest: Mapping[str, Any]
    case_parameters: Mapping[str, Mapping[str, object]]
    generator: NewHamiltonicityGenerator
    protocol: NewHamiltonicityProtocol


def create_task() -> NewHamiltonicityTaskPlugin:
    return NewHamiltonicityTaskPlugin(
        manifest=TASK_MANIFEST,
        case_parameters=CASE_PARAMETERS,
        generator=NewHamiltonicityGenerator(),
        protocol=NewHamiltonicityProtocol(),
    )


__all__ = [
    "CASE_ID",
    "CASE_IDS",
    "CASE_PARAMETERS",
    "HamiltonicityProtocolState",
    "HamiltonicityReason",
    "NewHamiltonicityGenerator",
    "NewHamiltonicityProtocol",
    "NewHamiltonicityTaskPlugin",
    "TASK_ID",
    "TASK_MANIFEST",
    "TASK_VERSION",
    "VIRTUAL_AGENTS",
    "create_task",
]
