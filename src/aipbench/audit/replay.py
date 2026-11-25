"""Offline validation of signatures, commitments, artifacts, and protocol replay."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from aipbench.core.artifacts import ArtifactStore
from aipbench.core.canonical import canonical_json_bytes, digest_json, pretty_json_text
from aipbench.core.errors import AIPBenchError, ErrorCode
from aipbench.core.event_log import load_and_validate_event_log
from aipbench.core.models import (
    GeneratedCase,
    ParticipantEvent,
    SessionMode,
    TerminalStatus,
    Transition,
)
from aipbench.core.randomness import CommittedPRG, seed_commitment
from aipbench.core.runtime import RuntimeArthurContext
from aipbench.core.signing import verify_signature


@dataclass(frozen=True)
class ReplayOutcome:
    terminal_status: str
    reason_code: str
    milestones: Mapping[str, int | float | str]
    events_received: int


# Native verifier resource limits are wall-clock/process outcomes, not protocol
# semantics. Re-running the same signed submission can legitimately finish on a
# less-loaded machine (or time out on a more-loaded one), so these canonical
# terminal responses must be replayed from their signed outcome instead of
# invoking the external toolchain again. Keep this allowlist deliberately narrow:
# task id, reason code, public state, and milestones all remain fixed here, while
# the normal response comparison still validates every signed response field.
_NATIVE_RESOURCE_TERMINALS: Mapping[
    tuple[str, str], tuple[Mapping[str, Any], Mapping[str, int | float | str]]
] = {
    ("t3.dafny_verified_programs", "DAFNY_RESOURCE_EXCEEDED"): (
        {"phase": "terminal", "program_checked": False},
        {"program_submitted": 1, "native_verifier_checked": 0},
    ),
    ("t3.machine_checked_mathematics", "LEAN_RESOURCE_EXCEEDED"): (
        {"phase": "terminal", "proof_checked": False},
        {"proof_submitted": 1, "kernel_checked": 0},
    ),
    ("t3.drat_bounded_hardware_safety", "DRAT_RESOURCE_EXCEEDED"): (
        {"phase": "terminal", "proof_checked": False},
        {"proof_submitted": 1, "drat_checked": 0},
    ),
}


def _native_resource_transition(
    *, task_id: str, status: Any, reason_code: Any, state: Any
) -> Transition | None:
    if status != TerminalStatus.REJECT.value or not isinstance(reason_code, str):
        return None
    specification = _NATIVE_RESOURCE_TERMINALS.get((task_id, reason_code))
    if specification is None:
        return None
    public_state, milestones = specification
    return Transition(
        new_state=state,
        terminal_status=TerminalStatus.REJECT,
        reason_code=reason_code,
        public_state=dict(public_state),
        milestones=dict(milestones),
    )


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise AIPBenchError(ErrorCode.INVALID_PAYLOAD, f"{path.name} must contain a JSON object")
    return value


def _response_payload(
    *, session_id: str, event: ParticipantEvent, transition: Transition
) -> dict[str, Any]:
    return {
        "api_version": "aip/1",
        "public_state": dict(transition.public_state),
        "reason_code": transition.reason_code,
        "reply": None
        if transition.reply is None
        else {"kind": transition.reply.kind, "payload": dict(transition.reply.payload)},
        "sequence": event.sequence,
        "session_id": session_id,
        "status": "CONTINUE"
        if transition.terminal_status is None
        else transition.terminal_status.value,
    }


def _reject(state: Any, code: str, *, system: bool = False) -> Transition:
    return Transition(
        new_state=state,
        terminal_status=TerminalStatus.SYSTEM_ERROR if system else TerminalStatus.REJECT,
        reason_code=code,
        public_state={"phase": "terminal"},
    )


def _replay(
    *,
    plugin: Any,
    generated_case: GeneratedCase,
    session: Mapping[str, Any],
    manifest: Mapping[str, Any],
    seed: bytes,
    records: list[dict[str, Any]],
    artifact_store: ArtifactStore,
    indexed_artifact_ids: frozenset[str],
) -> ReplayOutcome:
    if len(records) % 2:
        raise AIPBenchError(ErrorCode.TRANSCRIPT_REPLAY_FAILED, "unpaired transcript event")
    prg = CommittedPRG(
        seed=seed,
        run_id=str(session["run_id"]),
        task_digest=digest_json(manifest),
    )
    context = RuntimeArthurContext(
        mode=SessionMode(str(session["mode"])), prg=prg, artifact_store=artifact_store
    )
    state = plugin.protocol.initialize(generated_case=generated_case, context=context)
    expected_sequence = 0
    events_received = 0
    max_events = int(manifest.get("resources", {}).get("max_events", 1000))
    terminal: Transition | None = None

    for offset in range(0, len(records), 2):
        merlin = records[offset]
        arthur = records[offset + 1]
        if merlin["direction"] != "MERLIN_TO_ARTHUR":
            raise AIPBenchError(ErrorCode.TRANSCRIPT_REPLAY_FAILED, "expected Merlin event")
        if arthur["direction"] != "ARTHUR_TO_MERLIN" or arthur["kind"] != "runtime.response":
            raise AIPBenchError(ErrorCode.TRANSCRIPT_REPLAY_FAILED, "expected Arthur response")
        if terminal is not None:
            raise AIPBenchError(ErrorCode.TRANSCRIPT_REPLAY_FAILED, "event after terminal state")
        event = ParticipantEvent(
            sequence=merlin["sequence"],
            kind=merlin["kind"],
            payload=merlin["payload"],
            artifact_refs=tuple(merlin.get("artifact_refs", ())),
        )
        events_received += 1
        context.bind_event(str(merlin["event_hash"]))
        recorded_payload = arthur.get("payload", {})
        recorded_status = recorded_payload.get("status")
        recorded_reason = recorded_payload.get("reason_code")
        if recorded_status == TerminalStatus.TIMEOUT.value:
            transition = Transition(
                new_state=state,
                terminal_status=TerminalStatus.TIMEOUT,
                reason_code=ErrorCode.BUDGET_EXCEEDED,
                public_state={"phase": "terminal"},
            )
        elif native_resource := _native_resource_transition(
            task_id=generated_case.task_id,
            status=recorded_status,
            reason_code=recorded_reason,
            state=state,
        ):
            transition = native_resource
        elif event.sequence != expected_sequence:
            transition = _reject(state, ErrorCode.INVALID_SEQUENCE)
        elif events_received > max_events:
            transition = _reject(state, ErrorCode.BUDGET_EXCEEDED)
        else:
            try:
                for artifact_id in event.artifact_refs:
                    if artifact_id not in indexed_artifact_ids:
                        raise AIPBenchError(
                            ErrorCode.ARTIFACT_NOT_FOUND,
                            "transcript references an artifact absent from the signed index",
                        )
                    artifact_store.resolve(artifact_id)
                transition = plugin.protocol.handle_event(
                    state=state,
                    event=event,
                    generated_case=generated_case,
                    context=context,
                )
            except AIPBenchError as exc:
                transition = _reject(state, exc.code)
            except Exception as exc:
                raise AIPBenchError(
                    ErrorCode.TRANSCRIPT_REPLAY_FAILED,
                    f"protocol raised unexpectedly during replay: {type(exc).__name__}",
                ) from exc
        if event.sequence == expected_sequence:
            expected_sequence += 1
        state = transition.new_state
        expected_response = _response_payload(
            session_id=str(session["session_id"]), event=event, transition=transition
        )
        if arthur["payload"] != expected_response:
            raise AIPBenchError(
                ErrorCode.TRANSCRIPT_REPLAY_FAILED, "Arthur reply differs from replay"
            )
        if transition.terminal_status is not None:
            terminal = transition

    if terminal is None:
        raise AIPBenchError(ErrorCode.TRANSCRIPT_REPLAY_FAILED, "transcript is not terminal")
    terminal_status = terminal.terminal_status
    assert terminal_status is not None
    return ReplayOutcome(
        terminal_status=terminal_status.value,
        reason_code=terminal.reason_code or "PROTOCOL_REJECT",
        milestones=terminal.milestones,
        events_received=events_received,
    )


def audit_run(
    run_dir: Path,
    *,
    registry: Any | None = None,
    write_report: bool = True,
    trusted_public_key_base64: str | None = None,
) -> dict[str, Any]:
    """Audit a completed run from disk without reusing its live protocol state."""
    run_dir = run_dir.resolve()
    checks: list[dict[str, Any]] = []

    def check(name: str, operation: Callable[[], Any]) -> Any | None:
        try:
            value = operation()
        except Exception as exc:
            checks.append(
                {
                    "detail": getattr(exc, "code", str(exc) or type(exc).__name__),
                    "name": name,
                    "valid": False,
                }
            )
            return None
        checks.append({"detail": "VALID", "name": name, "valid": True})
        return value

    result = check("RESULT_JSON", lambda: _load_json(run_dir / "official" / "result.json"))
    session = check("SESSION", lambda: _load_json(run_dir / "official" / "session.json"))
    manifest = check(
        "TASK_MANIFEST", lambda: _load_json(run_dir / "official" / "task_manifest.json")
    )
    public_instance = check(
        "PUBLIC_INSTANCE", lambda: _load_json(run_dir / "public" / "instance.json")
    )
    public_protocol = check(
        "PUBLIC_PROTOCOL", lambda: _load_json(run_dir / "public" / "protocol.json")
    )
    private_instance = check(
        "PRIVATE_INSTANCE", lambda: _load_json(run_dir / "private" / "instance.private.json")
    )
    generation_metadata = check(
        "GENERATION_METADATA", lambda: _load_json(run_dir / "private" / "generation.metadata.json")
    )
    records = check(
        "EVENT_CHAIN",
        lambda: load_and_validate_event_log(run_dir / "official" / "transcript.jsonl"),
    )

    if result is not None and manifest is not None:
        check(
            "TASK_MANIFEST_DIGEST",
            lambda: _require_equal(
                result.get("task_manifest_digest"),
                digest_json(manifest),
                ErrorCode.TASK_MANIFEST_DIGEST_MISMATCH,
            ),
        )
    if result is not None and public_instance is not None:
        check(
            "INSTANCE_DIGEST",
            lambda: _require_equal(
                result.get("instance_digest"),
                digest_json(public_instance),
                ErrorCode.INSTANCE_DIGEST_MISMATCH,
            ),
        )
    if result is not None and private_instance is not None:
        check(
            "PRIVATE_INSTANCE_DIGEST",
            lambda: _require_equal(
                result.get("private_instance_digest"),
                digest_json(private_instance),
                ErrorCode.INSTANCE_DIGEST_MISMATCH,
            ),
        )
    if result is not None and generation_metadata is not None:
        check(
            "GENERATION_METADATA_DIGEST",
            lambda: _require_equal(
                result.get("generation_metadata_digest"),
                digest_json(generation_metadata),
                ErrorCode.INSTANCE_DIGEST_MISMATCH,
            ),
        )
    if result is not None and public_protocol is not None:
        check(
            "PROTOCOL_DIGEST",
            lambda: _require_equal(
                result.get("protocol_digest"),
                digest_json(public_protocol),
                ErrorCode.INSTANCE_DIGEST_MISMATCH,
            ),
        )
    if result is not None and session is not None:

        def verify_session_binding() -> None:
            for key in (
                "run_id",
                "session_id",
                "task_id",
                "task_version",
                "case_id",
                "instance_digest",
                "task_manifest_digest",
                "coin_commitment",
                "protocol_digest",
                "mode",
            ):
                _require_equal(
                    session.get(key), result.get(key), ErrorCode.INSTANCE_DIGEST_MISMATCH
                )

            _require_equal(
                result.get("session_digest"),
                digest_json(session),
                ErrorCode.INSTANCE_DIGEST_MISMATCH,
            )

        check("SESSION_BINDING", verify_session_binding)
    if result is not None and manifest is not None:

        def verify_manifest_binding() -> None:
            _require_equal(
                result.get("task_id"), manifest.get("id"), ErrorCode.INSTANCE_DIGEST_MISMATCH
            )
            _require_equal(
                result.get("task_version"),
                manifest.get("version"),
                ErrorCode.INSTANCE_DIGEST_MISMATCH,
            )

        check("MANIFEST_BINDING", verify_manifest_binding)

        def verify_budget_result() -> None:
            duration_ms = result.get("duration_ms")
            decision_duration_ms = result.get("decision_duration_ms")
            if type(duration_ms) is not int or duration_ms < 0:
                raise AIPBenchError(ErrorCode.BUDGET_EXCEEDED)
            if (
                type(decision_duration_ms) is not int
                or not 0 <= decision_duration_ms <= duration_ms
            ):
                raise AIPBenchError(ErrorCode.BUDGET_EXCEEDED)
            wall_ms = int(manifest.get("resources", {}).get("wall_time_seconds", 0)) * 1000
            if result.get("terminal_status") == TerminalStatus.TIMEOUT.value:
                if (
                    result.get("reason_code") != ErrorCode.BUDGET_EXCEEDED
                    or decision_duration_ms < wall_ms
                ):
                    raise AIPBenchError(ErrorCode.BUDGET_EXCEEDED)
            elif decision_duration_ms > wall_ms:
                raise AIPBenchError(ErrorCode.BUDGET_EXCEEDED)

        check("BUDGET_ACCOUNTING", verify_budget_result)
    if result is not None:

        def verify_result_signature() -> None:
            public_key = _load_json(run_dir / "official" / "signing_public_key.json")
            if public_key.get("algorithm") != "Ed25519":
                raise AIPBenchError(ErrorCode.SIGNATURE_INVALID)
            _require_equal(
                result.get("signing_public_key_digest"),
                digest_json(public_key),
                ErrorCode.SIGNATURE_INVALID,
            )
            signature = (run_dir / "official" / "result.sig").read_text(encoding="ascii").strip()
            embedded_public_key = public_key["public_key"]
            verification_key = (
                trusted_public_key_base64
                if trusted_public_key_base64 is not None
                else embedded_public_key
            )
            if trusted_public_key_base64 is not None and embedded_public_key != verification_key:
                raise AIPBenchError(ErrorCode.SIGNATURE_INVALID)
            if not verify_signature(
                public_key_base64=verification_key,
                data=canonical_json_bytes(result),
                signature_base64=signature,
            ):
                raise AIPBenchError(ErrorCode.SIGNATURE_INVALID)

        check("SIGNATURE", verify_result_signature)

    revealed_seed: bytes | None = None
    if result is not None and session is not None and manifest is not None:

        def verify_coins() -> bytes:
            reveal = _load_json(run_dir / "official" / "seed_reveal.json")
            commitment_document = _load_json(run_dir / "official" / "seed_commitment.json")
            if (
                reveal.get("algorithm") != "HMAC-SHA256-PRF"
                or commitment_document.get("algorithm") != "HMAC-SHA256-PRF"
                or commitment_document.get("model") != "committed_prg"
            ):
                raise AIPBenchError(ErrorCode.COIN_COMMITMENT_MISMATCH)
            _require_equal(
                result.get("seed_commitment_document_digest"),
                digest_json(commitment_document),
                ErrorCode.COIN_COMMITMENT_MISMATCH,
            )
            seed = bytes.fromhex(reveal["seed_hex"])
            expected = seed_commitment(
                seed=seed,
                run_id=session["run_id"],
                task_digest=digest_json(manifest),
            )
            values = {
                expected,
                reveal.get("commitment"),
                commitment_document.get("commitment"),
                session.get("coin_commitment"),
                result.get("coin_commitment"),
            }
            if len(values) != 1 or result.get("seed_reveal") != seed.hex():
                raise AIPBenchError(ErrorCode.COIN_COMMITMENT_MISMATCH)
            return seed

        revealed_seed = check("COIN_COMMITMENT", verify_coins)

    transcript_root: str | None = None
    if records is not None and result is not None:

        def verify_root() -> str:
            root = records[-1]["event_hash"] if records else "sha256:" + ("0" * 64)
            file_root = (
                (run_dir / "official" / "transcript.root").read_text(encoding="ascii").strip()
            )
            if root != file_root or root != result.get("transcript_root"):
                raise AIPBenchError(ErrorCode.EVENT_CHAIN_INVALID)
            return root

        transcript_root = check("TRANSCRIPT_ROOT", verify_root)

    artifact_store: ArtifactStore | None = None
    artifact_entries: list[dict[str, Any]] | None = None
    if manifest is not None:

        def open_and_validate_artifacts() -> list[dict[str, Any]]:
            nonlocal artifact_store
            resources = manifest.get("resources")
            if not isinstance(resources, dict):
                raise AIPBenchError("MANIFEST_INVALID", "manifest resources must be an object")
            max_bytes = resources.get("max_artifact_bytes")
            if type(max_bytes) is not int or max_bytes <= 0:
                raise AIPBenchError("MANIFEST_INVALID", "invalid artifact byte budget")
            artifact_store = ArtifactStore(
                run_dir / "official" / "artifacts",
                max_total_bytes=max_bytes,
                read_only=True,
            )
            entries = artifact_store.validate_index()
            if result is not None:
                _require_equal(
                    result.get("artifact_index_digest"),
                    digest_json(entries),
                    ErrorCode.ARTIFACT_HASH_MISMATCH,
                )
            return entries

        artifact_entries = check("ARTIFACTS", open_and_validate_artifacts)

    replay_outcome: ReplayOutcome | None = None
    required_for_replay = all(
        item is not None
        for item in (
            result,
            session,
            manifest,
            public_instance,
            public_protocol,
            private_instance,
            generation_metadata,
            records,
            revealed_seed,
            artifact_store,
            artifact_entries,
        )
    )
    if required_for_replay:
        assert isinstance(result, dict)
        assert isinstance(session, dict)
        assert isinstance(manifest, dict)
        assert isinstance(public_instance, dict)
        assert isinstance(public_protocol, dict)
        assert isinstance(private_instance, dict)
        assert isinstance(generation_metadata, dict)
        assert isinstance(records, list)
        assert revealed_seed is not None
        assert artifact_store is not None
        assert isinstance(artifact_entries, list)
        if registry is None:
            from aipbench.registry import default_registry

            registry = default_registry()

        def do_replay() -> ReplayOutcome:
            plugin = registry.get(result["task_id"])
            generated_case = GeneratedCase(
                task_id=result["task_id"],
                task_version=result["task_version"],
                case_id=result["case_id"],
                public_instance=public_instance,
                private_instance=private_instance,
                generation_metadata=generation_metadata,
            )
            expected_protocol = plugin.protocol.public_protocol_description(
                generated_case=generated_case
            )
            if dict(plugin.manifest) != manifest:
                raise AIPBenchError(
                    ErrorCode.TRANSCRIPT_REPLAY_FAILED,
                    "signed task manifest does not match the registered plugin",
                )
            if result["case_id"] not in plugin.case_parameters:
                raise AIPBenchError(
                    ErrorCode.TRANSCRIPT_REPLAY_FAILED,
                    "signed case is not declared by the registered task plugin",
                )
            if expected_protocol != public_protocol:
                raise AIPBenchError(
                    ErrorCode.TRANSCRIPT_REPLAY_FAILED,
                    "public protocol does not match the registered task plugin",
                )
            outcome = _replay(
                plugin=plugin,
                generated_case=generated_case,
                session=session,
                manifest=manifest,
                seed=revealed_seed,
                records=records,
                artifact_store=artifact_store,
                indexed_artifact_ids=frozenset(entry["artifact_id"] for entry in artifact_entries),
            )
            expected = (
                result.get("terminal_status"),
                result.get("reason_code"),
                result.get("events_received"),
            )
            actual = (
                outcome.terminal_status,
                outcome.reason_code,
                outcome.events_received,
            )
            if expected != actual:
                raise AIPBenchError(
                    ErrorCode.TRANSCRIPT_REPLAY_FAILED, "replay terminal result mismatch"
                )
            return outcome

        replay_outcome = check("TRANSCRIPT_REPLAY", do_replay)

    audit_passed = all(item["valid"] for item in checks) and replay_outcome is not None
    terminal_status = result.get("terminal_status") if isinstance(result, dict) else None
    official_result = "PASS" if audit_passed and terminal_status == "ACCEPT" else "FAIL"
    report = {
        "audit_passed": audit_passed,
        "checks": checks,
        "official_result": official_result,
        "primary_score": 1 if official_result == "PASS" else 0,
        "schema_version": "aip-audit/1",
        "signing_key_trust": (
            "external" if trusted_public_key_base64 is not None else "run_directory"
        ),
        "signed_terminal_status": terminal_status,
        "transcript_root": transcript_root,
    }
    if write_report:
        path = run_dir / "official" / "audit.json"
        path.write_text(pretty_json_text(report), encoding="utf-8", newline="\n")
    return report


def _require_equal(actual: Any, expected: Any, code: str) -> None:
    if actual != expected:
        raise AIPBenchError(code)


__all__ = ["ReplayOutcome", "audit_run"]
