"""T3.2 contract-verified programs checked by native Dafny and Z3.

Merlin uploads exactly one UTF-8 ``Solution.dfy`` artifact.  Arthur combines it
with the public challenge and executable harness, invokes the pinned Dafny
verifier, then compiles and runs that already-verified program with the Java
backend.  Python does not implement a substitute verifier.
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
from aipbench.tasks.dafny_verified_program_cases.common import DeterministicStream
from aipbench.tasks.dafny_verified_program_cases.registry import (
    CASE_DEFINITIONS,
    CASE_PARAMETERS,
    CASE_TITLES,
)

TASK_ID: Final = "t3.dafny_verified_programs"
TASK_VERSION: Final = "0.2.0"
CASE_IDS: Final[tuple[str, ...]] = tuple(CASE_PARAMETERS)
PROGRAM_EVENT_KIND: Final = "dafny.program"
DAFNY_TOOLCHAIN: Final = "dafny-lang/dafny:4.11.0+z3"
DAFNY_VERSION: Final = "4.11.0"
SOLUTION_MEDIA_TYPE: Final = "text/x-dafny; charset=utf-8"
MAX_SOLUTION_BYTES: Final = 1_048_576
_WINDOWS_CREATE_NO_WINDOW: Final[int] = 0x08000000
_PAYLOAD_FIELDS: Final = frozenset({"instance_sha256"})
_HASH_RE: Final = re.compile(r"^[0-9a-f]{64}$")
_IMPORT_RE: Final = re.compile(
    r"(?m)^\s*import\s+(?:opened\s+)?(?:[A-Za-z][A-Za-z0-9_]*\s*=\s*)?([^\s;]+)\s*;?\s*$"
)
_MODULE_RE: Final = re.compile(r"\bmodule\s+([A-Za-z][A-Za-z0-9_]*)\b")
_FORBIDDEN_SOURCE_RE: Final = re.compile(
    r"(?i)(?:\{:\s*|\b(?:assume|expect|axiom|extern|include|print)\b|"
    r"\bmethod\s+Main\b|\bdecreases\s*\*|\bmodule\s+(?:Challenge|ArthurHarness)\b|"
    r"--verification-time-limit|--verify|--compile)"
)


class DafnyReason:
    ARTIFACT_MALFORMED = "DAFNY_ARTIFACT_MALFORMED"
    INSTANCE_MISMATCH = "DAFNY_INSTANCE_MISMATCH"
    SOURCE_FORBIDDEN = "DAFNY_SOURCE_FORBIDDEN"
    TOOLCHAIN_UNAVAILABLE = "DAFNY_TOOLCHAIN_UNAVAILABLE"
    VERIFICATION_FAILED = "DAFNY_VERIFICATION_FAILED"
    EXECUTION_FAILED = "DAFNY_EXECUTION_FAILED"
    RESOURCE_EXCEEDED = "DAFNY_RESOURCE_EXCEEDED"
    BACKEND_FAILED = "DAFNY_BACKEND_FAILED"


TASK_MANIFEST: Final[Mapping[str, Any]] = {
    "id": TASK_ID,
    "version": TASK_VERSION,
    "tier": 3,
    "title": "Dafny-Verified Programs",
    "plugin": {"entrypoint": "aipbench.tasks.dafny_verified_programs:create_task"},
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
            "tasks/tier3_applied/dafny_verified_programs/schemas/public_instance.schema.json"
        ),
        "private_schema": (
            "tasks/tier3_applied/dafny_verified_programs/schemas/private_instance.schema.json"
        ),
    },
    "resources": {
        "wall_time_seconds": 600,
        "cpu_cores": 2,
        "memory_mb": 2048,
        "disk_mb": 1024,
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
    "scoring": {"primary": "binary_accept", "partial_progress": "program_submitted"},
    "soundness": {
        "class": "native_contract_verified_program",
        "statement": (
            "Dafny 4.11.0 and its bundled Z3 verify the submitted implementation against "
            "the public contracts; Arthur then executes its fixed Java harness"
        ),
    },
}


def _instance_digest(content: Mapping[str, Any]) -> str:
    return sha256_hex(
        b"aipbench/t3-dafny-verified-programs/instance/v1\x00" + canonical_json_bytes(content)
    )


class DafnyVerifiedProgramsGenerator:
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
            raise ValueError(f"unsupported Dafny case: {case_id}")
        unknown = set(case_parameters) - set(definition.parameters)
        if unknown:
            raise ValueError(f"unknown case parameters: {sorted(unknown)}")
        parameters = dict(definition.parameters)
        parameters.update(case_parameters)
        stream = DeterministicStream(
            hashlib.sha256(instance_seed + b"\x00" + case_id.encode("ascii")).digest()
        )
        blueprint = definition.builder(stream, parameters)
        challenge_bytes = blueprint.challenge_source.encode("utf-8")
        harness_bytes = blueprint.harness_source.encode("utf-8")
        digest_content: dict[str, Any] = {
            "format_version": "aip-dafny-program-instance/1",
            "toolchain": DAFNY_TOOLCHAIN,
            "solution_module": "Solution",
            "challenge_sha256": sha256_hex(challenge_bytes),
            "harness_sha256": sha256_hex(harness_bytes),
            "challenge_source": blueprint.challenge_source,
            "harness_source": blueprint.harness_source,
            "success_marker": f"AIPBENCH_DAFNY_OK:{case_id}",
            "public_features": dict(blueprint.public_features),
        }
        public_instance = {
            **digest_content,
            "instance_sha256": _instance_digest(digest_content),
        }
        reference = blueprint.reference_solution
        private_instance = {
            "reference_solution": reference,
            "reference_solution_sha256": sha256_hex(reference.encode("utf-8")),
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
                "harness_bytes": len(harness_bytes),
            },
        )


def _validate_public_instance(public_instance: Mapping[str, Any]) -> None:
    required = {
        "format_version",
        "toolchain",
        "solution_module",
        "challenge_sha256",
        "harness_sha256",
        "challenge_source",
        "harness_source",
        "success_marker",
        "public_features",
        "instance_sha256",
    }
    if set(public_instance) != required:
        raise ValueError("malformed generated Dafny public instance")
    if (
        public_instance.get("format_version") != "aip-dafny-program-instance/1"
        or public_instance.get("toolchain") != DAFNY_TOOLCHAIN
        or public_instance.get("solution_module") != "Solution"
    ):
        raise ValueError("unsupported generated Dafny instance format")
    challenge = public_instance.get("challenge_source")
    harness = public_instance.get("harness_source")
    marker = public_instance.get("success_marker")
    features = public_instance.get("public_features")
    if (
        not isinstance(challenge, str)
        or not isinstance(harness, str)
        or not isinstance(marker, str)
        or not isinstance(features, Mapping)
    ):
        raise ValueError("malformed generated Dafny instance values")
    if public_instance.get("challenge_sha256") != sha256_hex(challenge.encode("utf-8")):
        raise ValueError("generated Dafny challenge digest mismatch")
    if public_instance.get("harness_sha256") != sha256_hex(harness.encode("utf-8")):
        raise ValueError("generated Dafny harness digest mismatch")
    content = {key: public_instance[key] for key in required - {"instance_sha256"}}
    if public_instance.get("instance_sha256") != _instance_digest(content):
        raise ValueError("generated Dafny instance digest mismatch")


def _decode_solution(content: bytes) -> str:
    if not content or len(content) > MAX_SOLUTION_BYTES or b"\x00" in content:
        raise _ProgramRejected(DafnyReason.ARTIFACT_MALFORMED)
    try:
        source = content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise _ProgramRejected(DafnyReason.ARTIFACT_MALFORMED) from exc
    if source.startswith("\ufeff") or "\r" in source or not source.endswith("\n"):
        raise _ProgramRejected(DafnyReason.ARTIFACT_MALFORMED)
    modules = _MODULE_RE.findall(source)
    imports = _IMPORT_RE.findall(source)
    if (
        modules != ["Solution"]
        or not imports
        or any(imported != "Challenge" for imported in imports)
        or _FORBIDDEN_SOURCE_RE.search(source)
    ):
        raise _ProgramRejected(DafnyReason.SOURCE_FORBIDDEN)
    return source


def _dafny_candidates() -> tuple[Path, ...]:
    candidates: list[Path] = []
    configured = os.environ.get("AIPBENCH_DAFNY")
    if configured:
        candidates.append(Path(configured).expanduser())
    direct = shutil.which("dafny")
    if direct:
        candidates.append(Path(direct))
    return tuple(dict.fromkeys(candidate.resolve() for candidate in candidates))


def find_dafny_executable() -> Path | None:
    for candidate in _dafny_candidates():
        if candidate.is_file():
            return candidate
    return None


def _java_bin() -> Path | None:
    configured = os.environ.get("AIPBENCH_JAVA_HOME") or os.environ.get("JAVA_HOME")
    if configured:
        candidate = Path(configured) / "bin"
        if (candidate / ("java.exe" if os.name == "nt" else "java")).is_file():
            return candidate
    direct = shutil.which("java")
    if direct:
        return Path(direct).resolve().parent
    return None


@dataclass(frozen=True)
class DafnyCheckResult:
    verify_stdout_tail: str
    run_stdout_tail: str


class _ProgramRejected(Exception):
    def __init__(self, reason_code: str, diagnostic: str = "") -> None:
        super().__init__(reason_code)
        self.reason_code = reason_code
        self.diagnostic = diagnostic


class _BackendFailure(Exception):
    pass


def _subprocess_environment(workspace: Path, executable: Path, java_bin: Path) -> dict[str, str]:
    environment = {
        "HOME": str(workspace),
        "USERPROFILE": str(workspace),
        "TEMP": str(workspace),
        "TMP": str(workspace),
        "PATH": os.pathsep.join((str(executable.parent), str(java_bin))),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
    }
    if java_bin.name.lower() == "bin":
        environment["JAVA_HOME"] = str(java_bin.parent)
    if os.name == "nt":
        for name in ("SystemRoot", "WINDIR"):
            value = os.environ.get(name)
            if value:
                environment[name] = value
    return environment


def _run_checked(
    executable: Path,
    arguments: list[str],
    *,
    cwd: Path,
    java_bin: Path,
    timeout_seconds: float,
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            [str(executable), *arguments],
            cwd=cwd,
            env=_subprocess_environment(cwd, executable, java_bin),
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
            creationflags=_WINDOWS_CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
    except subprocess.TimeoutExpired as exc:
        raise _ProgramRejected(DafnyReason.RESOURCE_EXCEEDED) from exc
    except OSError as exc:
        raise _BackendFailure("could not execute native Dafny") from exc


def verify_dafny_solution(
    *,
    public_instance: Mapping[str, Any],
    solution_content: bytes,
    dafny_executable: Path | None = None,
    timeout_seconds: float = 600.0,
) -> DafnyCheckResult:
    """Verify and execute one untrusted solution in a fresh directory."""

    _validate_public_instance(public_instance)
    solution = _decode_solution(solution_content)
    executable = dafny_executable or find_dafny_executable()
    java_bin = _java_bin()
    if executable is None or java_bin is None:
        raise _BackendFailure(DafnyReason.TOOLCHAIN_UNAVAILABLE)
    with tempfile.TemporaryDirectory(prefix="aipbench-dafny-") as raw_workspace:
        workspace = Path(raw_workspace)
        version = _run_checked(
            executable,
            ["--version"],
            cwd=workspace,
            java_bin=java_bin,
            timeout_seconds=min(timeout_seconds, 10.0),
        )
        version_output = version.stdout + "\n" + version.stderr
        if version.returncode != 0 or DAFNY_VERSION not in version_output:
            raise _BackendFailure(DafnyReason.TOOLCHAIN_UNAVAILABLE)
        combined = "\n".join(
            (
                str(public_instance["challenge_source"]).rstrip(),
                solution.rstrip(),
                str(public_instance["harness_source"]).rstrip(),
                "",
            )
        )
        combined_path = workspace / "Combined.dfy"
        combined_path.write_text(combined, encoding="utf-8", newline="\n")
        frozen_bytes = combined_path.read_bytes()
        verified = _run_checked(
            executable,
            [
                "verify",
                "Combined.dfy",
                "--verification-time-limit",
                str(max(1, int(timeout_seconds))),
                "--cores",
                "2",
                "--allow-warnings=false",
                "--enforce-determinism",
            ],
            cwd=workspace,
            java_bin=java_bin,
            timeout_seconds=timeout_seconds,
        )
        verify_output = verified.stdout + "\n" + verified.stderr
        if verified.returncode != 0:
            raise _ProgramRejected(DafnyReason.VERIFICATION_FAILED, verify_output[-8_192:])
        if combined_path.read_bytes() != frozen_bytes:
            raise _ProgramRejected(DafnyReason.SOURCE_FORBIDDEN, "combined source changed")
        executed = _run_checked(
            executable,
            [
                "run",
                "Combined.dfy",
                "--no-verify",
                "--target",
                "java",
                "--allow-warnings=false",
            ],
            cwd=workspace,
            java_bin=java_bin,
            timeout_seconds=timeout_seconds,
        )
        run_output = executed.stdout + "\n" + executed.stderr
        marker = str(public_instance["success_marker"])
        if executed.returncode != 0 or run_output.count(marker) != 1:
            raise _ProgramRejected(DafnyReason.EXECUTION_FAILED, run_output[-8_192:])
        if combined_path.read_bytes() != frozen_bytes:
            raise _ProgramRejected(DafnyReason.SOURCE_FORBIDDEN, "combined source changed")
        return DafnyCheckResult(verify_output[-512:], run_output[-512:])


@dataclass(frozen=True)
class DafnyVerifiedProgramsState:
    phase: str = "awaiting_program"
    terminal_status: TerminalStatus | None = None
    reason_code: str | None = None
    events_processed: int = 0
    artifact_bytes: int = 0


class DafnyVerifiedProgramsProtocol:
    task_id = TASK_ID
    task_version = TASK_VERSION

    def initialize(
        self, *, generated_case: GeneratedCase, context: ArthurContext
    ) -> DafnyVerifiedProgramsState:
        del context
        self._validate_identity(generated_case)
        _validate_public_instance(generated_case.public_instance)
        return DafnyVerifiedProgramsState()

    def public_protocol_description(self, *, generated_case: GeneratedCase) -> Mapping[str, Any]:
        self._validate_identity(generated_case)
        _validate_public_instance(generated_case.public_instance)
        features = generated_case.public_instance["public_features"]
        assert isinstance(features, Mapping)
        return {
            "api_version": "aip/1",
            "mode": "one_shot",
            "initial_event_kinds": [PROGRAM_EVENT_KIND],
            "event_schemas": {
                PROGRAM_EVENT_KIND: {
                    "schema_ref": (
                        "tasks/tier3_applied/dafny_verified_programs/"
                        "schemas/program_submission.schema.json"
                    )
                }
            },
            "public_parameters": {
                "toolchain": DAFNY_TOOLCHAIN,
                "solution_module": "Solution",
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
        if not isinstance(state, DafnyVerifiedProgramsState):
            raise TypeError("state is not a DafnyVerifiedProgramsState")
        self._validate_identity(generated_case)
        if state.terminal_status is not None:
            return self._terminal(TerminalStatus.REJECT, ErrorCode.SESSION_TERMINAL)
        if event.kind != PROGRAM_EVENT_KIND:
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
            return self._terminal(TerminalStatus.REJECT, DafnyReason.INSTANCE_MISMATCH)
        try:
            artifact_path = context.get_artifact_path(event.artifact_refs[0])
            artifact_content = artifact_path.read_bytes()
            verify_dafny_solution(
                public_instance=generated_case.public_instance,
                solution_content=artifact_content,
            )
        except _ProgramRejected as rejected:
            return self._terminal(
                TerminalStatus.REJECT,
                rejected.reason_code,
                artifact_bytes=len(artifact_content) if "artifact_content" in locals() else 0,
            )
        except (AIPBenchError, OSError):
            return self._terminal(TerminalStatus.REJECT, DafnyReason.ARTIFACT_MALFORMED)
        except _BackendFailure as failure:
            reason = (
                str(failure)
                if str(failure) == DafnyReason.TOOLCHAIN_UNAVAILABLE
                else DafnyReason.BACKEND_FAILED
            )
            return self._terminal(TerminalStatus.SYSTEM_ERROR, reason)
        return self._terminal(
            TerminalStatus.ACCEPT,
            ErrorCode.PROTOCOL_ACCEPT,
            artifact_bytes=len(artifact_content),
        )

    def terminal_metrics(self, *, state: Any) -> Mapping[str, int | float | str]:
        if not isinstance(state, DafnyVerifiedProgramsState):
            raise TypeError("state is not a DafnyVerifiedProgramsState")
        metrics: dict[str, int | float | str] = {
            "events_processed": state.events_processed,
            "program_valid": int(state.terminal_status == TerminalStatus.ACCEPT),
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
            raise ValueError("generated case uses an unknown Dafny case ID")

    @staticmethod
    def _terminal(
        status: TerminalStatus, reason_code: str, *, artifact_bytes: int = 0
    ) -> Transition:
        next_state = DafnyVerifiedProgramsState(
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
                "program_submitted": 1,
                "native_verifier_checked": int(status == TerminalStatus.ACCEPT),
            },
            public_state={
                "phase": "terminal",
                "program_checked": status == TerminalStatus.ACCEPT,
            },
        )


def solve_public_instance(public_instance: Mapping[str, Any], case_id: str) -> str:
    _validate_public_instance(public_instance)
    definition = CASE_DEFINITIONS.get(case_id)
    if definition is None:
        raise ValueError(f"unknown Dafny case: {case_id}")
    blueprint = definition.builder(
        DeterministicStream(b"public-reference-not-used-for-instance-data"),
        definition.parameters,
    )
    return blueprint.reference_solution


def _participant_instance(client: ParticipantClient) -> Mapping[str, Any]:
    response = client.get_instance()
    nested = response.get("public_instance")
    return nested if isinstance(nested, Mapping) else response


class HonestDafnyVerifiedProgramsAgent:
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
            content=(solution.rstrip() + "\n").encode("utf-8"),
            media_type=SOLUTION_MEDIA_TYPE,
        )
        artifact_id = artifact.get("artifact_id")
        if not isinstance(artifact_id, str):
            raise ValueError("artifact upload did not return an ID")
        digest = public_instance.get("instance_sha256")
        assert isinstance(digest, str)
        client.submit_event(
            sequence=0,
            kind=PROGRAM_EVENT_KIND,
            payload={"instance_sha256": digest},
            artifact_refs=(artifact_id,),
        )


class InvalidDafnyVerifiedProgramsAgent:
    agent_id = "virtual-invalid-program"

    def run(self, *, client: ParticipantClient, workspace: Path) -> None:
        del workspace
        source = "module Solution { import opened Challenge method Main() {} }\n"
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
            kind=PROGRAM_EVENT_KIND,
            payload={"instance_sha256": digest},
            artifact_refs=(artifact_id,),
        )


_VIRTUAL_AGENT_LIST: Final[tuple[VirtualAgent, ...]] = (
    HonestDafnyVerifiedProgramsAgent(),
    InvalidDafnyVerifiedProgramsAgent(),
)
VIRTUAL_AGENTS: Final[Mapping[str, VirtualAgent]] = {
    agent.agent_id: agent for agent in _VIRTUAL_AGENT_LIST
}


@dataclass(frozen=True)
class DafnyVerifiedProgramsTaskPlugin:
    manifest: Mapping[str, Any]
    case_parameters: Mapping[str, Mapping[str, Any]]
    generator: DafnyVerifiedProgramsGenerator
    protocol: DafnyVerifiedProgramsProtocol


def create_task() -> DafnyVerifiedProgramsTaskPlugin:
    return DafnyVerifiedProgramsTaskPlugin(
        manifest=TASK_MANIFEST,
        case_parameters=CASE_PARAMETERS,
        generator=DafnyVerifiedProgramsGenerator(),
        protocol=DafnyVerifiedProgramsProtocol(),
    )


__all__ = [
    "CASE_IDS",
    "CASE_PARAMETERS",
    "CASE_TITLES",
    "DAFNY_TOOLCHAIN",
    "DAFNY_VERSION",
    "DafnyCheckResult",
    "DafnyReason",
    "DafnyVerifiedProgramsGenerator",
    "DafnyVerifiedProgramsProtocol",
    "DafnyVerifiedProgramsState",
    "DafnyVerifiedProgramsTaskPlugin",
    "PROGRAM_EVENT_KIND",
    "SOLUTION_MEDIA_TYPE",
    "TASK_ID",
    "TASK_MANIFEST",
    "TASK_VERSION",
    "VIRTUAL_AGENTS",
    "create_task",
    "find_dafny_executable",
    "solve_public_instance",
    "verify_dafny_solution",
]
