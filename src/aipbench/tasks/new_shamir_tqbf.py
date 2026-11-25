"""600-second Shamir-style TQBF interactive-proof task."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Final

from aipbench.core.models import GeneratedCase
from aipbench.tasks.new_tqbf_cases import CASE_DEFAULTS, build_case
from aipbench.tasks.shared.shamir_tqbf import (
    ShamirTQBFProtocol,
    TQBFProtocolState,
    TQBFReason,
    _build_round_plan,
    _parse_public_instance,
)
from aipbench.tasks.shared.tqbf_cases.common import blueprint_to_public

TASK_ID: Final = "t2.new_shamir_tqbf"
TASK_VERSION: Final = "0.1.0"
CASE_ID: Final = "c01"
CASE_IDS: Final[tuple[str, ...]] = tuple(CASE_DEFAULTS)
CASE_PARAMETERS: Final[Mapping[str, Mapping[str, object]]] = CASE_DEFAULTS

TASK_MANIFEST: Final[Mapping[str, Any]] = {
    "id": TASK_ID,
    "version": TASK_VERSION,
    "tier": 2,
    "title": "new Shamir-Style TQBF Interactive Proof",
    "plugin": {"entrypoint": "aipbench.tasks.new_shamir_tqbf:create_task"},
    "protocol": {
        "api_version": "aip/1",
        "mode": "interactive",
        "public_coin": True,
        "one_shot_eval": True,
        "max_events": 991,
        "participant_feedback": {"dev": "verbose", "eval": "minimal"},
    },
    "randomness": {
        "model": "committed_prg",
        "reveal_on_terminal": True,
        "domain_separation": "required",
    },
    "instance": {
        "public_schema": (
            "tasks/tier2_interactive/new_shamir_tqbf/schemas/public_instance.schema.json"
        ),
        "private_schema": (
            "tasks/tier2_interactive/new_shamir_tqbf/schemas/private_instance.schema.json"
        ),
    },
    "resources": {
        "wall_time_seconds": 600,
        "cpu_cores": 4,
        "memory_mb": 4096,
        "disk_mb": 4096,
        "max_artifact_bytes": 33_554_432,
        "max_events": 991,
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
        "statement": (
            "false initial claim acceptance is bounded by the sum of public round "
            "degrees divided by 2^61-1"
        ),
        "error_bound": "at most 2^-24 for accepted generated instances",
    },
}


class NewShamirTQBFGenerator:
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
            raise ValueError(f"unsupported new Shamir-TQBF case: {case_id}")
        if not set(case_parameters).issubset(defaults):
            raise ValueError("unknown new Shamir-TQBF case parameter")
        parameters: dict[str, object] = dict(defaults)
        parameters.update(case_parameters)
        blueprint = build_case(case_id, instance_seed, parameters)
        public_instance = blueprint_to_public(blueprint)
        circuit = _parse_public_instance(public_instance, max_variables=44, max_gates=4096)
        plans = _build_round_plan(circuit)
        return GeneratedCase(
            task_id=TASK_ID,
            task_version=TASK_VERSION,
            case_id=case_id,
            public_instance=public_instance,
            private_instance={"truth": 1, "family": blueprint.family},
            generation_metadata={
                "family": blueprint.family,
                "num_variables": circuit.num_inputs,
                "num_gates": len(circuit.gates),
                "num_rounds": len(plans),
                "difficulty_frozen": False,
            },
        )


class NewShamirTQBFProtocol(ShamirTQBFProtocol):
    task_id = TASK_ID
    task_version = TASK_VERSION
    schema_root = "tasks/tier2_interactive/new_shamir_tqbf/schemas"
    randomness_domain = TASK_ID
    max_variables = 44
    max_gates = 4096


VIRTUAL_AGENTS: Final[Mapping[str, Any]] = {}


@dataclass(frozen=True)
class NewShamirTQBFTaskPlugin:
    manifest: Mapping[str, Any]
    case_parameters: Mapping[str, Mapping[str, object]]
    generator: NewShamirTQBFGenerator
    protocol: NewShamirTQBFProtocol


def create_task() -> NewShamirTQBFTaskPlugin:
    return NewShamirTQBFTaskPlugin(
        manifest=TASK_MANIFEST,
        case_parameters=CASE_PARAMETERS,
        generator=NewShamirTQBFGenerator(),
        protocol=NewShamirTQBFProtocol(),
    )


__all__ = [
    "CASE_ID",
    "CASE_IDS",
    "CASE_PARAMETERS",
    "NewShamirTQBFGenerator",
    "NewShamirTQBFProtocol",
    "NewShamirTQBFTaskPlugin",
    "TASK_ID",
    "TASK_MANIFEST",
    "TASK_VERSION",
    "TQBFProtocolState",
    "TQBFReason",
    "VIRTUAL_AGENTS",
    "create_task",
]
