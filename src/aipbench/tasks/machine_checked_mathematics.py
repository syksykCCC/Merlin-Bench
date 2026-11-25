"""T3.1 machine-checked mathematics using a fixed Lean 4 kernel.

All eight cases share the same one-shot relation: the participant uploads one
UTF-8 ``Solution.lean`` artifact exporting
``AMBenchSolution.proof : Challenge.Target``.  The challenge is generated from
the public instance, staged in a fresh directory, and checked with the pinned
Lean 4.19.0 executable.  Python never substitutes for the kernel judgement.
"""

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
from aipbench.tasks.machine_checked_mathematics_cases import (
    CASE_DEFINITIONS,
    CASE_PARAMETERS,
    CASE_TITLES,
)
from aipbench.tasks.machine_checked_mathematics_cases.common import (
    PRELUDE_SOURCE,
    DeterministicStream,
)

TASK_ID: Final = "t3.machine_checked_mathematics"
TASK_VERSION: Final = "0.1.0"
CASE_IDS: Final[tuple[str, ...]] = tuple(CASE_PARAMETERS)
PROOF_EVENT_KIND: Final = "lean.proof"
LEAN_TOOLCHAIN: Final = "leanprover/lean4:v4.19.0"
LEAN_VERSION: Final = "4.19.0"
SOLUTION_MEDIA_TYPE: Final = "text/x-lean; charset=utf-8"
MAX_SOLUTION_BYTES: Final = 262_144
# ``subprocess.CREATE_NO_WINDOW`` is exposed only on Windows, so referring to
# it directly fails Linux type checking even behind an ``os.name`` guard.
# This is the documented Win32 ``CREATE_NO_WINDOW`` flag value.
_WINDOWS_CREATE_NO_WINDOW: Final[int] = 0x08000000
_PAYLOAD_FIELDS: Final = frozenset({"instance_sha256"})
_HASH_RE: Final = re.compile(r"^[0-9a-f]{64}$")
_IMPORT_RE: Final = re.compile(r"(?m)^\s*import\s+([^\r\n]+)\s*$")
_IMPORT_TOKEN_RE: Final = re.compile(r"\bimport\b")
_FORBIDDEN_SOURCE_RE: Final = re.compile(
    r"(?m)^\s*#|\b(?:sorry|admit|axiom|opaque|unsafe|unsafeCast|macro|syntax|elab|"
    r"run_tac|initialize|builtin_initialize|set_option|native_decide|implemented_by|extern)\b|"
    r"\b(?:IO|EIO|BaseIO|FilePath|System|Process)(?=[\s.]|$)|"
    r"Lean\.(?:ofReduceBool|trustCompiler)"
)


class LeanReason:
    """Stable, participant-safe T3.1 reason codes."""

    ARTIFACT_MALFORMED = "LEAN_ARTIFACT_MALFORMED"
    INSTANCE_MISMATCH = "LEAN_INSTANCE_MISMATCH"
    SOURCE_FORBIDDEN = "LEAN_SOURCE_FORBIDDEN"
    TOOLCHAIN_UNAVAILABLE = "LEAN_TOOLCHAIN_UNAVAILABLE"
    ELABORATION_FAILED = "LEAN_ELABORATION_FAILED"
    RESOURCE_EXCEEDED = "LEAN_RESOURCE_EXCEEDED"
    AXIOM_AUDIT_FAILED = "LEAN_AXIOM_AUDIT_FAILED"
    BACKEND_FAILED = "LEAN_BACKEND_FAILED"


TASK_MANIFEST: Final[Mapping[str, Any]] = {
    "id": TASK_ID,
    "version": TASK_VERSION,
    "tier": 3,
    "title": "Machine-Checked Mathematics",
    "plugin": {"entrypoint": "aipbench.tasks.machine_checked_mathematics:create_task"},
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
            "tasks/tier3_applied/machine_checked_mathematics/schemas/public_instance.schema.json"
        ),
        "private_schema": (
            "tasks/tier3_applied/machine_checked_mathematics/schemas/private_instance.schema.json"
        ),
    },
    "resources": {
        "wall_time_seconds": 600,
        "cpu_cores": 2,
        "memory_mb": 1024,
        "disk_mb": 512,
        "max_artifact_bytes": MAX_SOLUTION_BYTES,
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
    "scoring": {
        "primary": "binary_accept",
        "partial_progress": "proof_submitted",
    },
    "soundness": {
        "class": "deterministic_kernel_checked_proof",
        "statement": (
            "Lean 4.19.0 kernel checks an exact proof of the generated Challenge.Target; "
            "the trusted boundary includes the challenge encoding and process isolation"
        ),
    },
}


def _instance_digest(content: Mapping[str, Any]) -> str:
    return sha256_hex(
        b"aipbench/t3-machine-checked-mathematics/instance/v1\x00" + canonical_json_bytes(content)
    )


class MachineCheckedMathematicsGenerator:
    """Build deterministic Lean challenges for all eight case families."""

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
            raise ValueError(f"unsupported machine-checked mathematics case: {case_id}")
        unknown = set(case_parameters) - set(definition.parameters)
        if unknown:
            raise ValueError(f"unknown case parameters: {sorted(unknown)}")
        parameters = dict(definition.parameters)
        parameters.update(case_parameters)
        stream = DeterministicStream(
            hashlib.sha256(instance_seed + b"\x00" + case_id.encode("ascii")).digest()
        )
        blueprint = definition.builder(stream, parameters)
        solved = definition.solver(blueprint.problem)
        if solved != blueprint.reference_certificate:
            raise AssertionError("public solver disagrees with generated reference certificate")
        reference_solution = definition.solution_renderer(solved)
        challenge_bytes = blueprint.challenge_source.encode("utf-8")
        prelude_bytes = PRELUDE_SOURCE.encode("utf-8")
        digest_content: dict[str, Any] = {
            "format_version": "aip-lean-proof-instance/1",
            "toolchain": LEAN_TOOLCHAIN,
            "target_name": "Challenge.Target",
            "proof_name": "AMBenchSolution.proof",
            "prelude_sha256": sha256_hex(prelude_bytes),
            "challenge_sha256": sha256_hex(challenge_bytes),
            "prelude_source": PRELUDE_SOURCE,
            "challenge_source": blueprint.challenge_source,
            "problem": dict(blueprint.problem),
            "public_features": dict(blueprint.public_features),
        }
        public_instance = {
            **digest_content,
            "instance_sha256": _instance_digest(digest_content),
        }
        private_instance = {
            "reference_certificate": list(solved),
            "reference_solution": reference_solution,
            "reference_solution_sha256": sha256_hex(reference_solution.encode("utf-8")),
        }
        return GeneratedCase(
            task_id=TASK_ID,
            task_version=TASK_VERSION,
            case_id=case_id,
            public_instance=public_instance,
            private_instance=private_instance,
            generation_metadata={
                "case_title": blueprint.title,
                "challenge_bytes": len(challenge_bytes),
                **dict(blueprint.metadata),
            },
        )


def _validate_public_instance(public_instance: Mapping[str, Any]) -> None:
    required = {
        "format_version",
        "toolchain",
        "target_name",
        "proof_name",
        "prelude_sha256",
        "challenge_sha256",
        "prelude_source",
        "challenge_source",
        "problem",
        "public_features",
        "instance_sha256",
    }
    if set(public_instance) != required:
        raise ValueError("malformed generated Lean public instance")
    if (
        public_instance.get("format_version") != "aip-lean-proof-instance/1"
        or public_instance.get("toolchain") != LEAN_TOOLCHAIN
        or public_instance.get("target_name") != "Challenge.Target"
        or public_instance.get("proof_name") != "AMBenchSolution.proof"
    ):
        raise ValueError("unsupported generated Lean instance format")
    prelude = public_instance.get("prelude_source")
    challenge = public_instance.get("challenge_source")
    problem = public_instance.get("problem")
    features = public_instance.get("public_features")
    if (
        not isinstance(prelude, str)
        or not isinstance(challenge, str)
        or not isinstance(problem, Mapping)
        or not isinstance(features, Mapping)
    ):
        raise ValueError("malformed generated Lean instance values")
    if public_instance.get("prelude_sha256") != sha256_hex(prelude.encode("utf-8")):
        raise ValueError("generated Lean prelude digest mismatch")
    if public_instance.get("challenge_sha256") != sha256_hex(challenge.encode("utf-8")):
        raise ValueError("generated Lean challenge digest mismatch")
    digest_content = {key: public_instance[key] for key in required - {"instance_sha256"}}
    if public_instance.get("instance_sha256") != _instance_digest(digest_content):
        raise ValueError("generated Lean instance digest mismatch")


def _decode_solution(content: bytes) -> str:
    if not content or len(content) > MAX_SOLUTION_BYTES or b"\x00" in content:
        raise _ProofRejected(LeanReason.ARTIFACT_MALFORMED)
    try:
        source = content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise _ProofRejected(LeanReason.ARTIFACT_MALFORMED) from exc
    if source.startswith("\ufeff") or "\r" in source or not source.endswith("\n"):
        raise _ProofRejected(LeanReason.ARTIFACT_MALFORMED)
    imports = tuple(match.group(1).strip() for match in _IMPORT_RE.finditer(source))
    if (
        imports != ("Challenge",)
        or len(_IMPORT_TOKEN_RE.findall(source)) != 1
        or _FORBIDDEN_SOURCE_RE.search(source)
    ):
        raise _ProofRejected(LeanReason.SOURCE_FORBIDDEN)
    return source


def _lean_candidates() -> tuple[Path, ...]:
    configured = os.environ.get("AIPBENCH_LEAN")
    candidates: list[Path] = []
    if configured:
        candidates.append(Path(configured).expanduser())
    toolchain = Path.home() / ".elan" / "toolchains" / "leanprover--lean4---v4.19.0" / "bin"
    executable_name = "lean.exe" if os.name == "nt" else "lean"
    candidates.append(toolchain / executable_name)
    direct = shutil.which("lean")
    if direct and os.environ.get("AIPBENCH_ALLOW_ELAN_SHIM") == "1":
        candidates.append(Path(direct))
    unique: list[Path] = []
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved not in unique:
            unique.append(resolved)
    return tuple(unique)


def find_lean_executable() -> Path | None:
    """Return a pinned direct Lean executable, never an implicit updating shim."""

    for candidate in _lean_candidates():
        if candidate.is_file():
            return candidate
    return None


@dataclass(frozen=True)
class LeanCheckResult:
    elapsed_stage: str
    stdout_tail: str


class _ProofRejected(Exception):
    def __init__(self, reason_code: str, diagnostic: str = "") -> None:
        super().__init__(reason_code)
        self.reason_code = reason_code
        self.diagnostic = diagnostic


class _BackendFailure(Exception):
    pass


def _subprocess_environment(workspace: Path, executable: Path) -> dict[str, str]:
    environment = {
        "HOME": str(workspace),
        "USERPROFILE": str(workspace),
        "LEAN_PATH": str(workspace),
        "PATH": str(executable.parent),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
    }
    if os.name == "nt":
        for name in ("SystemRoot", "WINDIR", "TEMP", "TMP"):
            value = os.environ.get(name)
            if value:
                environment[name] = value
    return environment


def _run_checked(
    executable: Path,
    arguments: list[str],
    *,
    cwd: Path,
    timeout_seconds: float,
) -> subprocess.CompletedProcess[str]:
    creation_flags = _WINDOWS_CREATE_NO_WINDOW if os.name == "nt" else 0
    try:
        return subprocess.run(
            [str(executable), *arguments],
            cwd=cwd,
            env=_subprocess_environment(cwd, executable),
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
            creationflags=creation_flags,
        )
    except subprocess.TimeoutExpired as exc:
        raise _ProofRejected(LeanReason.RESOURCE_EXCEEDED) from exc
    except OSError as exc:
        raise _BackendFailure("could not execute the pinned Lean binary") from exc


def verify_lean_solution(
    *,
    public_instance: Mapping[str, Any],
    solution_content: bytes,
    lean_executable: Path | None = None,
    timeout_seconds: float = 600.0,
) -> LeanCheckResult:
    """Stage and kernel-check one untrusted solution in a fresh directory."""

    _validate_public_instance(public_instance)
    solution = _decode_solution(solution_content)
    executable = lean_executable or find_lean_executable()
    if executable is None:
        raise _BackendFailure(LeanReason.TOOLCHAIN_UNAVAILABLE)
    with tempfile.TemporaryDirectory(prefix="aipbench-lean-") as temporary:
        workspace = Path(temporary)
        version_check = _run_checked(
            executable,
            ["--version"],
            cwd=workspace,
            timeout_seconds=min(timeout_seconds, 5.0),
        )
        version_output = version_check.stdout + "\n" + version_check.stderr
        if version_check.returncode != 0 or f"version {LEAN_VERSION}" not in version_output:
            raise _BackendFailure(LeanReason.TOOLCHAIN_UNAVAILABLE)
        (workspace / "AMBenchPrelude.lean").write_text(
            str(public_instance["prelude_source"]), encoding="utf-8", newline="\n"
        )
        (workspace / "Challenge.lean").write_text(
            str(public_instance["challenge_source"]), encoding="utf-8", newline="\n"
        )
        (workspace / "Solution.lean").write_text(solution, encoding="utf-8", newline="\n")
        for module_name in ("AMBenchPrelude.lean", "Challenge.lean", "Solution.lean"):
            output_name = str(Path(module_name).with_suffix(".olean"))
            completed = _run_checked(
                executable,
                ["-o", output_name, module_name],
                cwd=workspace,
                timeout_seconds=timeout_seconds,
            )
            stage_output = completed.stdout + "\n" + completed.stderr
            if completed.returncode != 0:
                raise _ProofRejected(LeanReason.ELABORATION_FAILED, stage_output[-8_192:])

        # The Arthur-owned wrapper does not exist while untrusted Solution.lean is
        # elaborated.  Create it only afterwards, then verify that the bytes did not
        # change while Lean imported the submitted module.
        wrapper = """import Solution

example : Challenge.Target := AMBenchSolution.proof
#print axioms AMBenchSolution.proof
"""
        wrapper_path = workspace / "Verify.lean"
        wrapper_path.write_text(wrapper, encoding="utf-8", newline="\n")
        wrapper_bytes = wrapper_path.read_bytes()
        completed = _run_checked(
            executable,
            ["-o", "Verify.olean", "Verify.lean"],
            cwd=workspace,
            timeout_seconds=timeout_seconds,
        )
        output = (completed.stdout + "\n" + completed.stderr)[-8_192:]
        try:
            wrapper_unchanged = wrapper_path.read_bytes() == wrapper_bytes
        except OSError:
            wrapper_unchanged = False
        if not wrapper_unchanged:
            raise _ProofRejected(LeanReason.SOURCE_FORBIDDEN, "verification wrapper changed")
        if completed.returncode != 0:
            raise _ProofRejected(LeanReason.ELABORATION_FAILED, output)
        expected_audit = "'AMBenchSolution.proof' does not depend on any axioms"
        if "depends on axioms:" in output or expected_audit not in output:
            raise _ProofRejected(LeanReason.AXIOM_AUDIT_FAILED, output)
        return LeanCheckResult(elapsed_stage="kernel_and_axiom_audit", stdout_tail=output[-512:])


@dataclass(frozen=True)
class MachineCheckedMathematicsState:
    phase: str = "awaiting_proof"
    terminal_status: TerminalStatus | None = None
    reason_code: str | None = None
    events_processed: int = 0
    artifact_bytes: int = 0


class MachineCheckedMathematicsProtocol:
    task_id = TASK_ID
    task_version = TASK_VERSION

    def initialize(
        self, *, generated_case: GeneratedCase, context: ArthurContext
    ) -> MachineCheckedMathematicsState:
        del context
        self._validate_identity(generated_case)
        _validate_public_instance(generated_case.public_instance)
        return MachineCheckedMathematicsState()

    def public_protocol_description(self, *, generated_case: GeneratedCase) -> Mapping[str, Any]:
        self._validate_identity(generated_case)
        _validate_public_instance(generated_case.public_instance)
        features = generated_case.public_instance["public_features"]
        assert isinstance(features, Mapping)
        return {
            "api_version": "aip/1",
            "mode": "one_shot",
            "initial_event_kinds": [PROOF_EVENT_KIND],
            "event_schemas": {
                PROOF_EVENT_KIND: {
                    "schema_ref": (
                        "tasks/tier3_applied/machine_checked_mathematics/"
                        "schemas/proof_submission.schema.json"
                    )
                }
            },
            "public_parameters": {
                "toolchain": LEAN_TOOLCHAIN,
                "target_name": "Challenge.Target",
                "proof_name": "AMBenchSolution.proof",
                "max_solution_bytes": MAX_SOLUTION_BYTES,
                "one_shot": True,
                **dict(features),
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
        if not isinstance(state, MachineCheckedMathematicsState):
            raise TypeError("state is not a MachineCheckedMathematicsState")
        self._validate_identity(generated_case)
        if state.terminal_status is not None:
            return self._terminal(
                TerminalStatus.REJECT,
                ErrorCode.SESSION_TERMINAL,
                artifact_bytes=state.artifact_bytes,
            )
        if event.kind != PROOF_EVENT_KIND:
            return self._terminal(TerminalStatus.REJECT, ErrorCode.INVALID_EVENT_KIND)
        if set(event.payload) != _PAYLOAD_FIELDS or len(event.artifact_refs) != 1:
            return self._terminal(TerminalStatus.REJECT, ErrorCode.INVALID_PAYLOAD)
        submitted_digest = event.payload.get("instance_sha256")
        expected_digest = generated_case.public_instance.get("instance_sha256")
        if (
            not isinstance(submitted_digest, str)
            or _HASH_RE.fullmatch(submitted_digest) is None
            or submitted_digest != expected_digest
        ):
            return self._terminal(TerminalStatus.REJECT, LeanReason.INSTANCE_MISMATCH)
        try:
            artifact_path = context.get_artifact_path(event.artifact_refs[0])
            artifact_content = artifact_path.read_bytes()
            verify_lean_solution(
                public_instance=generated_case.public_instance,
                solution_content=artifact_content,
            )
        except _ProofRejected as rejected:
            return self._terminal(
                TerminalStatus.REJECT,
                rejected.reason_code,
                artifact_bytes=len(artifact_content) if "artifact_content" in locals() else 0,
            )
        except (AIPBenchError, OSError):
            return self._terminal(TerminalStatus.REJECT, LeanReason.ARTIFACT_MALFORMED)
        except _BackendFailure as failure:
            reason = (
                str(failure)
                if str(failure) == LeanReason.TOOLCHAIN_UNAVAILABLE
                else LeanReason.BACKEND_FAILED
            )
            return self._terminal(TerminalStatus.SYSTEM_ERROR, reason)

        return self._terminal(
            TerminalStatus.ACCEPT,
            ErrorCode.PROTOCOL_ACCEPT,
            artifact_bytes=len(artifact_content),
        )

    def terminal_metrics(self, *, state: Any) -> Mapping[str, int | float | str]:
        if not isinstance(state, MachineCheckedMathematicsState):
            raise TypeError("state is not a MachineCheckedMathematicsState")
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
            raise ValueError("generated case uses an unknown T3.1 case ID")

    @staticmethod
    def _terminal(
        status: TerminalStatus,
        reason_code: str,
        *,
        artifact_bytes: int = 0,
    ) -> Transition:
        state = MachineCheckedMathematicsState(
            phase="terminal",
            terminal_status=status,
            reason_code=reason_code,
            events_processed=1,
            artifact_bytes=artifact_bytes,
        )
        return Transition(
            new_state=state,
            terminal_status=status,
            reason_code=reason_code,
            milestones={
                "proof_submitted": 1,
                "kernel_checked": int(status == TerminalStatus.ACCEPT),
            },
            public_state={
                "phase": "terminal",
                "proof_checked": status == TerminalStatus.ACCEPT,
            },
        )


def solve_public_instance(public_instance: Mapping[str, Any], case_id: str) -> str:
    """Construct the deterministic reference proof using public data only."""

    _validate_public_instance(public_instance)
    definition = CASE_DEFINITIONS.get(case_id)
    if definition is None:
        raise ValueError(f"unknown T3.1 case: {case_id}")
    problem = public_instance.get("problem")
    if not isinstance(problem, Mapping):
        raise ValueError("public instance has no problem mapping")
    return definition.solution_renderer(definition.solver(problem))


def _participant_instance(client: ParticipantClient) -> Mapping[str, Any]:
    response = client.get_instance()
    nested = response.get("public_instance")
    if isinstance(nested, Mapping):
        return nested
    return response


class HonestMachineCheckedMathematicsAgent:
    agent_id = "virtual-honest"

    def run(self, *, client: ParticipantClient, workspace: Path) -> None:
        del workspace
        session = client.get_session()
        case_id = session.get("case_id")
        if not isinstance(case_id, str):
            raise ValueError("session does not expose a case ID")
        public_instance = _participant_instance(client)
        solution = solve_public_instance(public_instance, case_id)
        artifact = client.upload_artifact(
            content=solution.encode("utf-8"), media_type=SOLUTION_MEDIA_TYPE
        )
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


class InvalidProofMachineCheckedMathematicsAgent:
    agent_id = "virtual-invalid-proof"

    def run(self, *, client: ParticipantClient, workspace: Path) -> None:
        del workspace
        source = """import Challenge

namespace AMBenchSolution
theorem proof : Challenge.Target := by
  exact False.elim (by contradiction)
end AMBenchSolution
"""
        artifact = client.upload_artifact(
            content=source.encode("utf-8"), media_type=SOLUTION_MEDIA_TYPE
        )
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
    HonestMachineCheckedMathematicsAgent(),
    InvalidProofMachineCheckedMathematicsAgent(),
)
VIRTUAL_AGENTS: Final[Mapping[str, VirtualAgent]] = {
    agent.agent_id: agent for agent in _VIRTUAL_AGENT_LIST
}


@dataclass(frozen=True)
class MachineCheckedMathematicsTaskPlugin:
    manifest: Mapping[str, Any]
    case_parameters: Mapping[str, Mapping[str, Any]]
    generator: MachineCheckedMathematicsGenerator
    protocol: MachineCheckedMathematicsProtocol


def create_task() -> MachineCheckedMathematicsTaskPlugin:
    return MachineCheckedMathematicsTaskPlugin(
        manifest=TASK_MANIFEST,
        case_parameters=CASE_PARAMETERS,
        generator=MachineCheckedMathematicsGenerator(),
        protocol=MachineCheckedMathematicsProtocol(),
    )


__all__ = [
    "CASE_IDS",
    "CASE_PARAMETERS",
    "CASE_TITLES",
    "LEAN_TOOLCHAIN",
    "LEAN_VERSION",
    "LeanCheckResult",
    "LeanReason",
    "MachineCheckedMathematicsGenerator",
    "MachineCheckedMathematicsProtocol",
    "MachineCheckedMathematicsState",
    "MachineCheckedMathematicsTaskPlugin",
    "PROOF_EVENT_KIND",
    "SOLUTION_MEDIA_TYPE",
    "TASK_ID",
    "TASK_MANIFEST",
    "TASK_VERSION",
    "VIRTUAL_AGENTS",
    "create_task",
    "find_lean_executable",
    "solve_public_instance",
    "verify_lean_solution",
]
