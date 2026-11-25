"""Unified, transport-independent Arthur session runtime."""

from __future__ import annotations

import json
import math
import secrets
import threading
import time
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from aipbench.core.artifacts import ARTIFACT_ID_RE, ArtifactStore
from aipbench.core.canonical import canonical_json_bytes, digest_json, pretty_json_text
from aipbench.core.errors import AIPBenchError, ErrorCode, SessionTerminalError
from aipbench.core.event_log import EventLog
from aipbench.core.models import (
    GeneratedCase,
    ParticipantEvent,
    ProtocolReply,
    SessionLifecycle,
    SessionMode,
    TerminalStatus,
    Transition,
)
from aipbench.core.protocol import ArthurContext, TaskPlugin
from aipbench.core.randomness import CommittedPRG
from aipbench.core.signing import ResultSigner


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(pretty_json_text(value), encoding="utf-8", newline="\n")


def _read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _json_clone(value: Any) -> Any:
    return json.loads(canonical_json_bytes(value))


@dataclass(frozen=True)
class RuntimeSecrets:
    coin_seed: bytes
    session_token: str


class RuntimeArthurContext(ArthurContext):
    def __init__(
        self,
        *,
        mode: SessionMode,
        prg: CommittedPRG,
        artifact_store: ArtifactStore,
    ) -> None:
        self._mode = mode
        self._prg = prg
        self._artifact_store = artifact_store
        self._event_hash: str | None = None

    @property
    def mode(self) -> SessionMode:
        return self._mode

    def bind_event(self, event_hash: str) -> None:
        self._event_hash = event_hash

    def _require_bound_event(self) -> str:
        if self._event_hash is None:
            raise AIPBenchError(
                "CHALLENGE_BEFORE_COMMIT",
                "protocol randomness requested before participant event commit",
            )
        return self._event_hash

    def random_bytes(self, *, tag: str, length: int) -> bytes:
        return self._prg.random_bytes(
            tag=tag, length=length, event_hash=self._require_bound_event()
        )

    def random_int(self, *, tag: str, lower_inclusive: int, upper_exclusive: int) -> int:
        return self._prg.random_int(
            tag=tag,
            lower_inclusive=lower_inclusive,
            upper_exclusive=upper_exclusive,
            event_hash=self._require_bound_event(),
        )

    def random_field_element(self, *, tag: str, modulus: int) -> int:
        return self.random_int(tag=tag, lower_inclusive=0, upper_exclusive=modulus)

    def get_artifact_path(self, artifact_id: str) -> Path:
        return self._artifact_store.resolve(artifact_id)


class ArthurRuntime:
    """One-shot Arthur runtime shared by in-process and HTTP transports."""

    def __init__(
        self,
        *,
        plugin: TaskPlugin,
        generated_case: GeneratedCase,
        run_dir: Path,
        run_id: str,
        session_id: str,
        mode: SessionMode,
        coin_seed: bytes,
        signer: ResultSigner,
        session_token: str,
        initialize_disk: bool,
    ) -> None:
        self._lock = threading.RLock()
        self.plugin = plugin
        self.generated_case = GeneratedCase(
            task_id=generated_case.task_id,
            task_version=generated_case.task_version,
            case_id=generated_case.case_id,
            public_instance=_json_clone(generated_case.public_instance),
            private_instance=_json_clone(generated_case.private_instance),
            generation_metadata=_json_clone(generated_case.generation_metadata),
        )
        self.run_dir = run_dir.resolve()
        self.run_id = run_id
        self.session_id = session_id
        self.mode = mode
        self.signer = signer
        self.session_token = session_token
        self.manifest = _json_clone(plugin.manifest)
        self.task_manifest_digest = digest_json(self.manifest)
        self.instance_digest = digest_json(generated_case.public_instance)
        self.private_instance_digest = digest_json(generated_case.private_instance)
        self.generation_metadata_digest = digest_json(generated_case.generation_metadata)
        self.protocol_description = dict(
            self.plugin.protocol.public_protocol_description(generated_case=self.generated_case)
        )
        self.protocol_digest = digest_json(self.protocol_description)
        self.lifecycle = SessionLifecycle.PREPARED
        self.expected_sequence = 0
        self.events_received = 0
        self.started_ns = time.monotonic_ns()
        self.decision_elapsed_ms: int | None = None
        self.terminal_result: dict[str, Any] | None = None

        resources = self.manifest.get("resources", {})
        max_artifact_bytes = int(resources.get("max_artifact_bytes", 64 * 1024 * 1024))
        self.max_events = int(resources.get("max_events", 1000))
        self.wall_time_seconds = int(resources.get("wall_time_seconds", 600))
        self.artifact_store = ArtifactStore(
            self.run_dir / "official" / "artifacts", max_total_bytes=max_artifact_bytes
        )
        self.event_log = EventLog(self.run_dir / "official" / "transcript.jsonl")
        self.prg = CommittedPRG(
            seed=coin_seed, run_id=self.run_id, task_digest=self.task_manifest_digest
        )
        self.seed_commitment_document = {
            "algorithm": "HMAC-SHA256-PRF",
            "commitment": self.prg.commitment,
            "model": "committed_prg",
        }
        self.signing_public_key_document = {
            "algorithm": "Ed25519",
            "public_key": self.signer.public_base64,
        }
        self.context = RuntimeArthurContext(
            mode=mode, prg=self.prg, artifact_store=self.artifact_store
        )
        self.state = self.plugin.protocol.initialize(
            generated_case=self.generated_case, context=self.context
        )
        if initialize_disk:
            self._initialize_disk(coin_seed=coin_seed)

    @classmethod
    def create(
        cls,
        *,
        plugin: TaskPlugin,
        case_id: str,
        run_dir: Path,
        mode: SessionMode = SessionMode.DEV,
        instance_seed: bytes,
        coin_seed: bytes | None = None,
        run_id: str | None = None,
        session_token: str | None = None,
    ) -> ArthurRuntime:
        if run_dir.exists() and any(run_dir.iterdir()):
            raise AIPBenchError("RUN_DIRECTORY_NOT_EMPTY", f"run directory is not empty: {run_dir}")
        coin_seed = coin_seed or secrets.token_bytes(32)
        run_id = (
            run_id
            or f"run-{digest_json({'seed': instance_seed.hex(), 'coin': coin_seed.hex()})[7:23]}"
        )
        session_id = f"session-{digest_json({'run_id': run_id})[7:23]}"
        session_token = session_token or secrets.token_urlsafe(32)
        parameters = plugin.case_parameters.get(case_id)
        if parameters is None:
            raise AIPBenchError("CASE_NOT_FOUND", f"unknown case: {case_id}")
        generated_case = plugin.generator.generate(
            instance_seed=instance_seed, case_id=case_id, case_parameters=parameters
        )
        return cls(
            plugin=plugin,
            generated_case=generated_case,
            run_dir=run_dir,
            run_id=run_id,
            session_id=session_id,
            mode=mode,
            coin_seed=coin_seed,
            signer=ResultSigner.generate(),
            session_token=session_token,
            initialize_disk=True,
        )

    @classmethod
    def load_prepared(cls, *, plugin: TaskPlugin, run_dir: Path) -> ArthurRuntime:
        run_dir = run_dir.resolve()
        if (run_dir / "official" / "result.json").exists():
            raise AIPBenchError("SESSION_ALREADY_TERMINAL", "cannot resume a terminal one-shot run")
        if (run_dir / "official" / "transcript.jsonl").stat().st_size:
            raise AIPBenchError("SESSION_ALREADY_ACTIVE", "resuming an active run is not supported")
        session = _read_json(run_dir / "official" / "session.json")
        private_runtime = _read_json(run_dir / "private" / "runtime.json")
        generated_case = GeneratedCase(
            task_id=session["task_id"],
            task_version=session["task_version"],
            case_id=session["case_id"],
            public_instance=_read_json(run_dir / "public" / "instance.json"),
            private_instance=_read_json(run_dir / "private" / "instance.private.json"),
            generation_metadata=_read_json(run_dir / "private" / "generation.metadata.json"),
        )
        return cls(
            plugin=plugin,
            generated_case=generated_case,
            run_dir=run_dir,
            run_id=session["run_id"],
            session_id=session["session_id"],
            mode=SessionMode(session["mode"]),
            coin_seed=bytes.fromhex(private_runtime["coin_seed_hex"]),
            signer=ResultSigner.from_private_base64(private_runtime["signing_private_key"]),
            session_token=private_runtime["session_token"],
            initialize_disk=False,
        )

    def _initialize_disk(self, *, coin_seed: bytes) -> None:
        for name in ("public", "official", "private"):
            (self.run_dir / name).mkdir(parents=True, exist_ok=True)
        _write_json(self.run_dir / "public" / "instance.json", self.generated_case.public_instance)
        _write_json(self.run_dir / "public" / "protocol.json", self.protocol_description)
        _write_json(
            self.run_dir / "private" / "instance.private.json",
            self.generated_case.private_instance,
        )
        _write_json(
            self.run_dir / "private" / "generation.metadata.json",
            self.generated_case.generation_metadata,
        )
        _write_json(
            self.run_dir / "private" / "runtime.json",
            {
                "coin_seed_hex": coin_seed.hex(),
                "session_token": self.session_token,
                "signing_private_key": self.signer.private_base64,
            },
        )
        _write_json(self.run_dir / "official" / "task_manifest.json", self.manifest)
        _write_json(
            self.run_dir / "official" / "seed_commitment.json",
            self.seed_commitment_document,
        )
        _write_json(
            self.run_dir / "official" / "signing_public_key.json",
            self.signing_public_key_document,
        )
        _write_json(self.run_dir / "official" / "session.json", self.get_session())

    def get_session(self) -> dict[str, Any]:
        resources = self.manifest.get("resources", {})
        return {
            "api_version": "aip/1",
            "budgets": {
                "max_artifact_bytes": int(resources.get("max_artifact_bytes", 64 * 1024 * 1024)),
                "max_events": self.max_events,
                "wall_time_seconds": int(resources.get("wall_time_seconds", 600)),
            },
            "case_id": self.generated_case.case_id,
            "coin_commitment": self.prg.commitment,
            "instance_digest": self.instance_digest,
            "mode": self.mode.value,
            "protocol_digest": self.protocol_digest,
            "run_id": self.run_id,
            "session_id": self.session_id,
            "task_id": self.generated_case.task_id,
            "task_manifest_digest": self.task_manifest_digest,
            "task_version": self.generated_case.task_version,
        }

    def get_protocol(self) -> Mapping[str, Any]:
        return cast(dict[str, Any], _json_clone(self.protocol_description))

    def get_instance(self) -> Mapping[str, Any]:
        return cast(dict[str, Any], _json_clone(self.generated_case.public_instance))

    def get_status(self) -> dict[str, Any]:
        status: dict[str, Any] = {
            "lifecycle": self.lifecycle.value,
            "next_sequence": self.expected_sequence,
            "session_id": self.session_id,
        }
        if self.terminal_result is not None:
            status["terminal_status"] = self.terminal_result["terminal_status"]
            status["reason_code"] = self.terminal_result["reason_code"]
        return status

    def observer_inputs(self) -> dict[str, Any]:
        """Return one locked, public-only dynamic snapshot for the local observer."""

        with self._lock:
            terminal_result: dict[str, Any] | None = None
            if self.terminal_result is not None:
                terminal_result = {
                    key: _json_clone(self.terminal_result[key])
                    for key in (
                        "duration_ms",
                        "events_received",
                        "milestones",
                        "reason_code",
                        "terminal_status",
                    )
                    if key in self.terminal_result
                }
            return {
                "elapsed_ms": self._elapsed_ms(),
                "events_received": self.events_received,
                "status": self.get_status(),
                "terminal_result": terminal_result,
            }

    def upload_artifact(self, *, content: bytes, media_type: str) -> Mapping[str, Any]:
        with self._lock:
            if self.terminal_result is not None:
                raise SessionTerminalError()
            if self._wall_time_exceeded():
                raise AIPBenchError(
                    ErrorCode.BUDGET_EXCEEDED,
                    "wall-time budget exceeded",
                    http_status=408,
                )
            return self.artifact_store.put(content=content, media_type=media_type)

    def _terminal_transition(self, *, code: str, system: bool = False) -> Transition:
        status = TerminalStatus.SYSTEM_ERROR if system else TerminalStatus.REJECT
        return Transition(
            new_state=self.state,
            terminal_status=status,
            reason_code=code,
            milestones={},
            public_state={"phase": "terminal"},
        )

    def _timeout_transition(self) -> Transition:
        return Transition(
            new_state=self.state,
            terminal_status=TerminalStatus.TIMEOUT,
            reason_code=ErrorCode.BUDGET_EXCEEDED,
            milestones={},
            public_state={"phase": "terminal"},
        )

    def _wall_time_exceeded(self) -> bool:
        elapsed_ns = time.monotonic_ns() - self.started_ns
        return elapsed_ns > self.wall_time_seconds * 1_000_000_000

    def _elapsed_ms(self) -> int:
        return (time.monotonic_ns() - self.started_ns) // 1_000_000

    def submit_event(self, event: ParticipantEvent) -> dict[str, Any]:
        with self._lock:
            return self._submit_event_locked(event)

    def _submit_event_locked(self, event: ParticipantEvent) -> dict[str, Any]:
        if self.terminal_result is not None:
            raise SessionTerminalError()
        self._validate_event_envelope(event)
        merlin_record = self.event_log.append(
            direction="MERLIN_TO_ARTHUR",
            sequence=event.sequence,
            kind=event.kind,
            payload=event.payload,
            artifact_refs=event.artifact_refs,
        )
        self.context.bind_event(str(merlin_record["event_hash"]))
        self.events_received += 1
        self.lifecycle = SessionLifecycle.ACTIVE

        if self._wall_time_exceeded():
            transition = self._timeout_transition()
        elif event.sequence != self.expected_sequence:
            transition = self._terminal_transition(code=ErrorCode.INVALID_SEQUENCE)
        elif self.events_received > self.max_events:
            transition = self._terminal_transition(code=ErrorCode.BUDGET_EXCEEDED)
        else:
            try:
                for artifact_id in event.artifact_refs:
                    self.artifact_store.resolve(artifact_id)
                transition = self.plugin.protocol.handle_event(
                    state=self.state,
                    event=event,
                    generated_case=self.generated_case,
                    context=self.context,
                )
            except AIPBenchError as exc:
                transition = self._terminal_transition(code=exc.code)
            except Exception:
                transition = self._terminal_transition(
                    code=ErrorCode.SYSTEM_BACKEND_ERROR, system=True
                )
        if self._wall_time_exceeded():
            transition = self._timeout_transition()
        if transition.terminal_status is not None:
            self.decision_elapsed_ms = self._elapsed_ms()
        if event.sequence == self.expected_sequence:
            self.expected_sequence += 1
        self.state = transition.new_state
        response = self._response_for(event=event, transition=transition)
        response_record = self.event_log.append(
            direction="ARTHUR_TO_MERLIN",
            sequence=event.sequence,
            kind="runtime.response",
            payload=response,
        )
        response_with_receipt = {
            **response,
            "receipt": {"event_hash": response_record["event_hash"]},
        }
        if transition.terminal_status is not None:
            self._finalize(transition=transition)
        return response_with_receipt

    @staticmethod
    def _validate_event_envelope(event: ParticipantEvent) -> None:
        if type(event.sequence) is not int or event.sequence < 0:
            raise AIPBenchError(
                ErrorCode.INVALID_SEQUENCE, "sequence must be a non-negative integer"
            )
        if not isinstance(event.kind, str) or not 1 <= len(event.kind) <= 128:
            raise AIPBenchError(ErrorCode.INVALID_EVENT_KIND, "event kind must be a short string")
        if not isinstance(event.payload, dict) or not ArthurRuntime._is_json_native(event.payload):
            raise AIPBenchError(ErrorCode.INVALID_PAYLOAD, "event payload must be a JSON object")
        if not isinstance(event.artifact_refs, tuple) or not all(
            isinstance(artifact_id, str) and ARTIFACT_ID_RE.fullmatch(artifact_id)
            for artifact_id in event.artifact_refs
        ):
            raise AIPBenchError(
                ErrorCode.ARTIFACT_NOT_FOUND,
                "artifact references must be canonical content identifiers",
            )

    @staticmethod
    def _is_json_native(value: Any) -> bool:
        if value is None or isinstance(value, (str, bool)):
            return True
        if type(value) is int:
            return True
        if type(value) is float:
            return math.isfinite(value)
        if isinstance(value, list):
            return all(ArthurRuntime._is_json_native(item) for item in value)
        if isinstance(value, dict):
            return all(
                isinstance(key, str) and ArthurRuntime._is_json_native(item)
                for key, item in value.items()
            )
        return False

    def _response_for(self, *, event: ParticipantEvent, transition: Transition) -> dict[str, Any]:
        reply: ProtocolReply | None = transition.reply
        return {
            "api_version": "aip/1",
            "public_state": dict(transition.public_state),
            "reason_code": transition.reason_code,
            "reply": None
            if reply is None
            else {"kind": reply.kind, "payload": dict(reply.payload)},
            "sequence": event.sequence,
            "session_id": self.session_id,
            "status": "CONTINUE"
            if transition.terminal_status is None
            else transition.terminal_status.value,
        }

    def _finalize(self, *, transition: Transition) -> None:
        assert transition.terminal_status is not None
        lifecycle_by_status = {
            TerminalStatus.ACCEPT: SessionLifecycle.ACCEPTED,
            TerminalStatus.REJECT: SessionLifecycle.REJECTED,
            TerminalStatus.TIMEOUT: SessionLifecycle.TIMEOUT,
            TerminalStatus.SYSTEM_ERROR: SessionLifecycle.SYSTEM_ERROR,
        }
        self.lifecycle = lifecycle_by_status[transition.terminal_status]
        seed_reveal = {
            "algorithm": "HMAC-SHA256-PRF",
            "commitment": self.prg.commitment,
            "seed_hex": self.prg.seed.hex(),
        }
        _write_json(self.run_dir / "official" / "seed_reveal.json", seed_reveal)
        (self.run_dir / "official" / "transcript.root").write_text(
            self.event_log.transcript_root + "\n", encoding="ascii", newline="\n"
        )
        artifact_entries = self.artifact_store.validate_index()
        assert self.decision_elapsed_ms is not None
        result = {
            "artifact_index_digest": digest_json(artifact_entries),
            "case_id": self.generated_case.case_id,
            "coin_commitment": self.prg.commitment,
            "decision_duration_ms": self.decision_elapsed_ms,
            "duration_ms": (time.monotonic_ns() - self.started_ns) // 1_000_000,
            "events_received": self.events_received,
            "generation_metadata_digest": self.generation_metadata_digest,
            "instance_digest": self.instance_digest,
            "milestones": dict(transition.milestones),
            "mode": self.mode.value,
            "reason_code": transition.reason_code
            or (
                ErrorCode.PROTOCOL_ACCEPT
                if transition.terminal_status is TerminalStatus.ACCEPT
                else "PROTOCOL_REJECT"
            ),
            "run_id": self.run_id,
            "schema_version": "aip-result/1",
            "seed_commitment_document_digest": digest_json(self.seed_commitment_document),
            "seed_reveal": self.prg.seed.hex(),
            "session_id": self.session_id,
            "session_digest": digest_json(self.get_session()),
            "signing_public_key_digest": digest_json(self.signing_public_key_document),
            "private_instance_digest": self.private_instance_digest,
            "protocol_digest": self.protocol_digest,
            "task_id": self.generated_case.task_id,
            "task_manifest_digest": self.task_manifest_digest,
            "task_version": self.generated_case.task_version,
            "terminal_status": transition.terminal_status.value,
            "transcript_root": self.event_log.transcript_root,
        }
        result_bytes = canonical_json_bytes(result)
        _write_json(self.run_dir / "official" / "result.json", result)
        (self.run_dir / "official" / "result.sig").write_text(
            self.signer.sign(result_bytes) + "\n", encoding="ascii", newline="\n"
        )
        metrics = {
            **dict(self.plugin.protocol.terminal_metrics(state=self.state)),
            "duration_ms": result["duration_ms"],
            "events_received": self.events_received,
        }
        _write_json(self.run_dir / "official" / "metrics.json", metrics)
        self.terminal_result = result


__all__ = ["ArthurRuntime", "RuntimeArthurContext", "RuntimeSecrets", "_read_json", "_write_json"]
