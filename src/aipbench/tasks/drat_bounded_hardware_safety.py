"""T3.3 bounded hardware safety with standard DRAT certificates."""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from aipbench.core.canonical import canonical_json_bytes, sha256_hex
from aipbench.core.errors import AIPBenchError, ErrorCode
from aipbench.core.models import GeneratedCase, ParticipantEvent, TerminalStatus, Transition
from aipbench.core.protocol import ArthurContext, ParticipantClient, VirtualAgent
from aipbench.tasks.drat_bounded_hardware_cases.common import DeterministicStream
from aipbench.tasks.drat_bounded_hardware_cases.registry import (
    CASE_DEFINITIONS,
    CASE_PARAMETERS,
    CASE_TITLES,
)

TASK_ID: Final = "t3.drat_bounded_hardware_safety"
TASK_VERSION: Final = "0.8.0"
CASE_IDS: Final[tuple[str, ...]] = tuple(CASE_PARAMETERS)
PROOF_EVENT_KIND: Final = "hardware.drat"
TOOLCHAIN: Final = "aiger-039ec1a2/bmc-tseitin-v1+drat-trim-2e3b2dc0+cadical-3.0.1-reference"
DRAT_TRIM_COMMIT: Final = "2e3b2dc0ecf938addbd779d42877b6ed69d9a985"
PROOF_MEDIA_TYPE: Final = "application/x-drat"
MAX_PROOF_BYTES: Final = 16_777_216
_WINDOWS_CREATE_NO_WINDOW: Final[int] = 0x08000000
_PAYLOAD_FIELDS: Final = frozenset({"instance_sha256"})
_HASH_RE: Final = re.compile(r"^[0-9a-f]{64}$")


class DratReason:
    ARTIFACT_MALFORMED = "DRAT_ARTIFACT_MALFORMED"
    INSTANCE_MISMATCH = "DRAT_INSTANCE_MISMATCH"
    TOOLCHAIN_UNAVAILABLE = "DRAT_TOOLCHAIN_UNAVAILABLE"
    PROOF_INVALID = "DRAT_PROOF_INVALID"
    RESOURCE_EXCEEDED = "DRAT_RESOURCE_EXCEEDED"
    BACKEND_FAILED = "DRAT_BACKEND_FAILED"


TASK_MANIFEST: Final[Mapping[str, Any]] = {
    "id": TASK_ID,
    "version": TASK_VERSION,
    "tier": 3,
    "title": "DRAT-Certified Bounded Hardware Safety",
    "plugin": {"entrypoint": "aipbench.tasks.drat_bounded_hardware_safety:create_task"},
    "protocol": {
        "api_version": "aip/1",
        "mode": "one_shot",
        "public_coin": False,
        "one_shot_eval": True,
        "max_events": 1,
        "participant_feedback": {"dev": "verbose", "eval": "minimal"},
    },
    "randomness": {
        "model": "none",
        "reveal_on_terminal": False,
        "domain_separation": "not_applicable",
    },
    "instance": {
        "public_schema": (
            "tasks/tier3_applied/drat_bounded_hardware_safety/schemas/public_instance.schema.json"
        ),
        "private_schema": (
            "tasks/tier3_applied/drat_bounded_hardware_safety/schemas/private_instance.schema.json"
        ),
    },
    "resources": {
        "wall_time_seconds": 600,
        "cpu_cores": 2,
        "memory_mb": 2048,
        "disk_mb": 2048,
        "max_artifact_bytes": MAX_PROOF_BYTES,
        "max_events": 1,
    },
    "audit": {
        "replay_mode": "strict",
        "require_signature": True,
        "require_seed_commitment": False,
        "require_instance_digest": True,
        "require_event_chain": True,
        "require_seed_reveal": False,
    },
    "scoring": {"primary": "binary_accept", "partial_progress": "proof_submitted"},
    "soundness": {
        "class": "native_drat_checked_bounded_safety",
        "statement": (
            "The published bounded-miter DIMACS formula is checked UNSAT by the pinned "
            "drat-trim checker using the submitted standard DRAT proof"
        ),
    },
}


def _instance_digest(content: Mapping[str, Any]) -> str:
    return sha256_hex(
        b"aipbench/t3-drat-bounded-hardware/instance/v1\x00" + canonical_json_bytes(content)
    )


class DratBoundedHardwareGenerator:
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
            raise ValueError(f"unsupported hardware case: {case_id}")
        unknown = set(case_parameters) - set(definition.parameters)
        if unknown:
            raise ValueError(f"unknown case parameters: {sorted(unknown)}")
        parameters = dict(definition.parameters)
        parameters.update(case_parameters)
        stream = DeterministicStream(
            hashlib.sha256(instance_seed + b"\x00" + case_id.encode("ascii")).digest()
        )
        blueprint = definition.builder(stream, parameters)
        aiger_bytes = blueprint.aiger_aag.encode("ascii")
        cnf_bytes = blueprint.bound_cnf.encode("ascii")
        digest_content: dict[str, Any] = {
            "format_version": "aip-bounded-hardware-drat-instance/1",
            "toolchain": TOOLCHAIN,
            "circuit_name": blueprint.circuit_name,
            "bound": blueprint.horizon,
            "property": "bad output is unreachable at every frame from 0 through bound",
            "aiger_sha256": sha256_hex(aiger_bytes),
            "cnf_sha256": sha256_hex(cnf_bytes),
            "aiger_aag": blueprint.aiger_aag,
            "bound_cnf": blueprint.bound_cnf,
            "num_cnf_variables": blueprint.num_cnf_variables,
            "num_cnf_clauses": blueprint.num_cnf_clauses,
            "public_features": dict(blueprint.public_features),
        }
        public_instance = {
            **digest_content,
            "instance_sha256": _instance_digest(digest_content),
        }
        private_instance = {
            "reference_solver": "CaDiCaL 3.0.1 --no-binary",
            "reference_checker_commit": DRAT_TRIM_COMMIT,
        }
        return GeneratedCase(
            task_id=TASK_ID,
            task_version=TASK_VERSION,
            case_id=case_id,
            public_instance=public_instance,
            private_instance=private_instance,
            generation_metadata={
                "case_title": blueprint.title,
                "aiger_bytes": len(aiger_bytes),
                "cnf_bytes": len(cnf_bytes),
                "cnf_variables": blueprint.num_cnf_variables,
                "cnf_clauses": blueprint.num_cnf_clauses,
            },
        )


def _validate_public_instance(public_instance: Mapping[str, Any]) -> None:
    required = {
        "format_version",
        "toolchain",
        "circuit_name",
        "bound",
        "property",
        "aiger_sha256",
        "cnf_sha256",
        "aiger_aag",
        "bound_cnf",
        "num_cnf_variables",
        "num_cnf_clauses",
        "public_features",
        "instance_sha256",
    }
    if set(public_instance) != required:
        raise ValueError("malformed generated hardware public instance")
    if (
        public_instance.get("format_version") != "aip-bounded-hardware-drat-instance/1"
        or public_instance.get("toolchain") != TOOLCHAIN
    ):
        raise ValueError("unsupported bounded hardware instance")
    aiger = public_instance.get("aiger_aag")
    cnf = public_instance.get("bound_cnf")
    if not isinstance(aiger, str) or not isinstance(cnf, str):
        raise ValueError("malformed AIGER/CNF sources")
    if public_instance.get("aiger_sha256") != sha256_hex(aiger.encode("ascii")):
        raise ValueError("AIGER digest mismatch")
    if public_instance.get("cnf_sha256") != sha256_hex(cnf.encode("ascii")):
        raise ValueError("CNF digest mismatch")
    content = {key: public_instance[key] for key in required - {"instance_sha256"}}
    if public_instance.get("instance_sha256") != _instance_digest(content):
        raise ValueError("hardware instance digest mismatch")


def _drat_trim_candidates() -> tuple[Path, ...]:
    candidates: list[Path] = []
    configured = os.environ.get("AIPBENCH_DRAT_TRIM")
    if configured:
        candidates.append(Path(configured).expanduser())
    direct = shutil.which("drat-trim")
    if direct:
        candidates.append(Path(direct))
    return tuple(dict.fromkeys(candidate.resolve() for candidate in candidates))


def find_drat_trim_executable() -> Path | None:
    for candidate in _drat_trim_candidates():
        if candidate.is_file():
            return candidate
    return None


def _cadical_candidates() -> tuple[Path, ...]:
    candidates: list[Path] = []
    configured = os.environ.get("AIPBENCH_CADICAL")
    if configured:
        candidates.append(Path(configured).expanduser())
    direct = shutil.which("cadical")
    if direct:
        candidates.append(Path(direct))
    return tuple(dict.fromkeys(candidate.resolve() for candidate in candidates))


def find_cadical_executable() -> Path | None:
    for candidate in _cadical_candidates():
        if candidate.is_file():
            return candidate
    return None


class _ProofRejected(Exception):
    def __init__(self, reason_code: str, diagnostic: str = "") -> None:
        super().__init__(reason_code)
        self.reason_code = reason_code
        self.diagnostic = diagnostic


class _BackendFailure(Exception):
    pass


def _run(
    command: list[str], *, cwd: Path, timeout_seconds: float
) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["TEMP"] = str(cwd)
    environment["TMP"] = str(cwd)
    try:
        return subprocess.run(
            command,
            cwd=cwd,
            env=environment,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
            creationflags=_WINDOWS_CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
    except subprocess.TimeoutExpired as exc:
        raise _ProofRejected(DratReason.RESOURCE_EXCEEDED) from exc
    except OSError as exc:
        raise _BackendFailure("could not execute native SAT proof tool") from exc


@dataclass(frozen=True)
class DratCheckResult:
    stdout_tail: str


def verify_drat_proof(
    *,
    public_instance: Mapping[str, Any],
    proof_content: bytes,
    checker_executable: Path | None = None,
    timeout_seconds: float = 600.0,
) -> DratCheckResult:
    _validate_public_instance(public_instance)
    if not proof_content or len(proof_content) > MAX_PROOF_BYTES:
        raise _ProofRejected(DratReason.ARTIFACT_MALFORMED)
    executable = checker_executable or find_drat_trim_executable()
    if executable is None:
        raise _BackendFailure(DratReason.TOOLCHAIN_UNAVAILABLE)
    with tempfile.TemporaryDirectory(prefix="aipbench-drat-check-") as raw:
        workspace = Path(raw)
        cnf_path = workspace / "bound.cnf"
        proof_path = workspace / "proof.drat"
        cnf_path.write_text(str(public_instance["bound_cnf"]), encoding="ascii", newline="\n")
        proof_path.write_bytes(proof_content)
        completed = _run(
            [str(executable), str(cnf_path), str(proof_path), "-w"],
            cwd=workspace,
            timeout_seconds=timeout_seconds,
        )
        output = completed.stdout + "\n" + completed.stderr
        if completed.returncode != 0 or "s VERIFIED" not in output:
            raise _ProofRejected(DratReason.PROOF_INVALID, output[-8_192:])
        return DratCheckResult(output[-512:])


def solve_public_instance(public_instance: Mapping[str, Any]) -> bytes:
    """Generate a standard reference DRAT proof using public CNF only."""

    _validate_public_instance(public_instance)
    executable = find_cadical_executable()
    if executable is None:
        raise _BackendFailure(DratReason.TOOLCHAIN_UNAVAILABLE)
    with tempfile.TemporaryDirectory(prefix="aipbench-cadical-") as raw:
        workspace = Path(raw)
        cnf_path = workspace / "bound.cnf"
        proof_path = workspace / "proof.drat"
        cnf_path.write_text(str(public_instance["bound_cnf"]), encoding="ascii", newline="\n")
        completed = _run(
            [str(executable), "--quiet", "--no-binary", str(cnf_path), str(proof_path)],
            cwd=workspace,
            timeout_seconds=600.0,
        )
        if completed.returncode != 20 or not proof_path.is_file():
            raise _BackendFailure("CaDiCaL did not produce an UNSAT proof")
        proof = proof_path.read_bytes()
        verify_drat_proof(public_instance=public_instance, proof_content=proof)
        return proof


@dataclass(frozen=True)
class DratBoundedHardwareState:
    phase: str = "awaiting_proof"
    terminal_status: TerminalStatus | None = None
    reason_code: str | None = None
    events_processed: int = 0
    artifact_bytes: int = 0


class DratBoundedHardwareProtocol:
    task_id = TASK_ID
    task_version = TASK_VERSION

    def initialize(
        self, *, generated_case: GeneratedCase, context: ArthurContext
    ) -> DratBoundedHardwareState:
        del context
        self._validate_identity(generated_case)
        _validate_public_instance(generated_case.public_instance)
        return DratBoundedHardwareState()

    def public_protocol_description(self, *, generated_case: GeneratedCase) -> Mapping[str, Any]:
        self._validate_identity(generated_case)
        _validate_public_instance(generated_case.public_instance)
        return {
            "api_version": "aip/1",
            "mode": "one_shot",
            "initial_event_kinds": [PROOF_EVENT_KIND],
            "event_schemas": {
                PROOF_EVENT_KIND: {
                    "schema_ref": (
                        "tasks/tier3_applied/drat_bounded_hardware_safety/"
                        "schemas/proof_submission.schema.json"
                    )
                }
            },
            "public_parameters": {
                "toolchain": TOOLCHAIN,
                "bound": generated_case.public_instance["bound"],
                "num_cnf_variables": generated_case.public_instance["num_cnf_variables"],
                "num_cnf_clauses": generated_case.public_instance["num_cnf_clauses"],
                "max_proof_bytes": MAX_PROOF_BYTES,
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
        if not isinstance(state, DratBoundedHardwareState):
            raise TypeError("state is not a DratBoundedHardwareState")
        self._validate_identity(generated_case)
        if state.terminal_status is not None:
            return self._terminal(TerminalStatus.REJECT, ErrorCode.SESSION_TERMINAL)
        if event.kind != PROOF_EVENT_KIND:
            return self._terminal(TerminalStatus.REJECT, ErrorCode.INVALID_EVENT_KIND)
        if set(event.payload) != _PAYLOAD_FIELDS or len(event.artifact_refs) != 1:
            return self._terminal(TerminalStatus.REJECT, ErrorCode.INVALID_PAYLOAD)
        submitted = event.payload.get("instance_sha256")
        expected = generated_case.public_instance.get("instance_sha256")
        if (
            not isinstance(submitted, str)
            or _HASH_RE.fullmatch(submitted) is None
            or submitted != expected
        ):
            return self._terminal(TerminalStatus.REJECT, DratReason.INSTANCE_MISMATCH)
        try:
            artifact_path = context.get_artifact_path(event.artifact_refs[0])
            proof_content = artifact_path.read_bytes()
            verify_drat_proof(
                public_instance=generated_case.public_instance,
                proof_content=proof_content,
            )
        except _ProofRejected as rejected:
            return self._terminal(
                TerminalStatus.REJECT,
                rejected.reason_code,
                artifact_bytes=len(proof_content) if "proof_content" in locals() else 0,
            )
        except (AIPBenchError, OSError):
            return self._terminal(TerminalStatus.REJECT, DratReason.ARTIFACT_MALFORMED)
        except _BackendFailure as failure:
            reason = (
                str(failure)
                if str(failure) == DratReason.TOOLCHAIN_UNAVAILABLE
                else DratReason.BACKEND_FAILED
            )
            return self._terminal(TerminalStatus.SYSTEM_ERROR, reason)
        return self._terminal(
            TerminalStatus.ACCEPT,
            ErrorCode.PROTOCOL_ACCEPT,
            artifact_bytes=len(proof_content),
        )

    def terminal_metrics(self, *, state: Any) -> Mapping[str, int | float | str]:
        if not isinstance(state, DratBoundedHardwareState):
            raise TypeError("state is not a DratBoundedHardwareState")
        metrics: dict[str, int | float | str] = {
            "events_processed": state.events_processed,
            "proof_valid": int(state.terminal_status == TerminalStatus.ACCEPT),
            "artifact_bytes": state.artifact_bytes,
        }
        if state.reason_code is not None:
            metrics["reason_code"] = state.reason_code
        return metrics

    @staticmethod
    def _validate_identity(generated_case: GeneratedCase) -> None:
        if generated_case.task_id != TASK_ID or generated_case.task_version != TASK_VERSION:
            raise ValueError("generated case does not belong to this task plugin")
        if generated_case.case_id not in CASE_IDS:
            raise ValueError("generated case uses an unknown hardware case ID")

    @staticmethod
    def _terminal(
        status: TerminalStatus, reason_code: str, *, artifact_bytes: int = 0
    ) -> Transition:
        next_state = DratBoundedHardwareState(
            phase="terminal",
            terminal_status=status,
            reason_code=reason_code,
            events_processed=1,
            artifact_bytes=artifact_bytes,
        )
        return Transition(
            new_state=next_state,
            terminal_status=status,
            reason_code=reason_code,
            milestones={
                "proof_submitted": 1,
                "drat_checked": int(status == TerminalStatus.ACCEPT),
            },
            public_state={
                "phase": "terminal",
                "proof_checked": status == TerminalStatus.ACCEPT,
            },
        )


def _participant_instance(client: ParticipantClient) -> Mapping[str, Any]:
    response = client.get_instance()
    nested = response.get("public_instance")
    return nested if isinstance(nested, Mapping) else response


class HonestDratBoundedHardwareAgent:
    agent_id = "virtual-honest"

    def run(self, *, client: ParticipantClient, workspace: Path) -> None:
        del workspace
        public_instance = _participant_instance(client)
        proof = solve_public_instance(public_instance)
        artifact = client.upload_artifact(content=proof, media_type=PROOF_MEDIA_TYPE)
        artifact_id = artifact.get("artifact_id")
        if not isinstance(artifact_id, str):
            raise ValueError("artifact upload did not return an ID")
        digest = public_instance.get("instance_sha256")
        assert isinstance(digest, str)
        client.submit_event(
            sequence=0,
            kind=PROOF_EVENT_KIND,
            payload={"instance_sha256": digest},
            artifact_refs=(artifact_id,),
        )


class InvalidDratBoundedHardwareAgent:
    agent_id = "virtual-invalid-proof"

    def run(self, *, client: ParticipantClient, workspace: Path) -> None:
        del workspace
        artifact = client.upload_artifact(content=b"1 0\n", media_type=PROOF_MEDIA_TYPE)
        artifact_id = artifact.get("artifact_id")
        if not isinstance(artifact_id, str):
            raise ValueError("artifact upload did not return an ID")
        public_instance = _participant_instance(client)
        digest = public_instance.get("instance_sha256")
        assert isinstance(digest, str)
        client.submit_event(
            sequence=0,
            kind=PROOF_EVENT_KIND,
            payload={"instance_sha256": digest},
            artifact_refs=(artifact_id,),
        )


_VIRTUAL_AGENT_LIST: Final[tuple[VirtualAgent, ...]] = (
    HonestDratBoundedHardwareAgent(),
    InvalidDratBoundedHardwareAgent(),
)
VIRTUAL_AGENTS: Final[Mapping[str, VirtualAgent]] = {
    agent.agent_id: agent for agent in _VIRTUAL_AGENT_LIST
}


@dataclass(frozen=True)
class DratBoundedHardwareTaskPlugin:
    manifest: Mapping[str, Any]
    case_parameters: Mapping[str, Mapping[str, Any]]
    generator: DratBoundedHardwareGenerator
    protocol: DratBoundedHardwareProtocol


def create_task() -> DratBoundedHardwareTaskPlugin:
    return DratBoundedHardwareTaskPlugin(
        manifest=TASK_MANIFEST,
        case_parameters=CASE_PARAMETERS,
        generator=DratBoundedHardwareGenerator(),
        protocol=DratBoundedHardwareProtocol(),
    )


__all__ = [
    "CASE_IDS",
    "CASE_PARAMETERS",
    "CASE_TITLES",
    "DRAT_TRIM_COMMIT",
    "DratBoundedHardwareGenerator",
    "DratBoundedHardwareProtocol",
    "DratBoundedHardwareState",
    "DratBoundedHardwareTaskPlugin",
    "DratCheckResult",
    "DratReason",
    "PROOF_EVENT_KIND",
    "PROOF_MEDIA_TYPE",
    "TASK_ID",
    "TASK_MANIFEST",
    "TASK_VERSION",
    "TOOLCHAIN",
    "VIRTUAL_AGENTS",
    "create_task",
    "find_cadical_executable",
    "find_drat_trim_executable",
    "solve_public_instance",
    "verify_drat_proof",
]
