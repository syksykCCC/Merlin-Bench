"""Stable runtime and protocol error codes."""

from __future__ import annotations


class ErrorCode:
    PROTOCOL_ACCEPT = "PROTOCOL_ACCEPT"
    INVALID_EVENT_KIND = "INVALID_EVENT_KIND"
    INVALID_PAYLOAD = "INVALID_PAYLOAD"
    INVALID_SEQUENCE = "INVALID_SEQUENCE"
    SESSION_NOT_ACTIVE = "SESSION_NOT_ACTIVE"
    SESSION_TERMINAL = "SESSION_TERMINAL"
    ARTIFACT_NOT_FOUND = "ARTIFACT_NOT_FOUND"
    ARTIFACT_HASH_MISMATCH = "ARTIFACT_HASH_MISMATCH"
    BUDGET_EXCEEDED = "BUDGET_EXCEEDED"
    CLAIM_ROUTE_INVALID = "CLAIM_ROUTE_INVALID"
    CERTIFICATE_INVALID = "CERTIFICATE_INVALID"
    ROUND_DEGREE_EXCEEDED = "ROUND_DEGREE_EXCEEDED"
    ROUND_CONSISTENCY_FAILED = "ROUND_CONSISTENCY_FAILED"
    FINAL_ORACLE_CHECK_FAILED = "FINAL_ORACLE_CHECK_FAILED"
    INSTANCE_DIGEST_MISMATCH = "INSTANCE_DIGEST_MISMATCH"
    TASK_MANIFEST_DIGEST_MISMATCH = "TASK_MANIFEST_DIGEST_MISMATCH"
    COIN_COMMITMENT_MISMATCH = "COIN_COMMITMENT_MISMATCH"
    SIGNATURE_INVALID = "SIGNATURE_INVALID"
    EVENT_CHAIN_INVALID = "EVENT_CHAIN_INVALID"
    TRANSCRIPT_REPLAY_FAILED = "TRANSCRIPT_REPLAY_FAILED"
    SYSTEM_BACKEND_ERROR = "SYSTEM_BACKEND_ERROR"


class AIPBenchError(Exception):
    """Base exception carrying a stable public reason code."""

    def __init__(self, code: str, message: str = "", *, http_status: int = 400) -> None:
        super().__init__(message or code)
        self.code = code
        self.message = message or code
        self.http_status = http_status


class ManifestError(AIPBenchError):
    def __init__(self, message: str) -> None:
        super().__init__("MANIFEST_INVALID", message)


class SessionTerminalError(AIPBenchError):
    def __init__(self) -> None:
        super().__init__(ErrorCode.SESSION_TERMINAL, http_status=409)


class AuthenticationError(AIPBenchError):
    def __init__(self) -> None:
        super().__init__("AUTHENTICATION_FAILED", http_status=401)
