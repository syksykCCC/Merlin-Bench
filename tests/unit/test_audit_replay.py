from __future__ import annotations

import pytest

from aipbench.audit.replay import _native_resource_transition
from aipbench.core.models import TerminalStatus


@pytest.mark.parametrize(
    ("task_id", "reason_code", "public_state", "milestones"),
    (
        (
            "t3.dafny_verified_programs",
            "DAFNY_RESOURCE_EXCEEDED",
            {"phase": "terminal", "program_checked": False},
            {"program_submitted": 1, "native_verifier_checked": 0},
        ),
        (
            "t3.machine_checked_mathematics",
            "LEAN_RESOURCE_EXCEEDED",
            {"phase": "terminal", "proof_checked": False},
            {"proof_submitted": 1, "kernel_checked": 0},
        ),
        (
            "t3.drat_bounded_hardware_safety",
            "DRAT_RESOURCE_EXCEEDED",
            {"phase": "terminal", "proof_checked": False},
            {"proof_submitted": 1, "drat_checked": 0},
        ),
    ),
)
def test_native_resource_terminal_is_canonicalized(
    task_id: str,
    reason_code: str,
    public_state: dict[str, object],
    milestones: dict[str, int],
) -> None:
    state = object()
    transition = _native_resource_transition(
        task_id=task_id,
        status="REJECT",
        reason_code=reason_code,
        state=state,
    )
    assert transition is not None
    assert transition.new_state is state
    assert transition.terminal_status is TerminalStatus.REJECT
    assert transition.reason_code == reason_code
    assert transition.public_state == public_state
    assert transition.milestones == milestones


@pytest.mark.parametrize(
    ("task_id", "status", "reason_code"),
    (
        ("t3.dafny_verified_programs", "ACCEPT", "DAFNY_RESOURCE_EXCEEDED"),
        ("t3.dafny_verified_programs", "REJECT", "DAFNY_VERIFICATION_FAILED"),
        ("t3.machine_checked_mathematics", "REJECT", "DAFNY_RESOURCE_EXCEEDED"),
        ("unknown.task", "REJECT", "DAFNY_RESOURCE_EXCEEDED"),
    ),
)
def test_native_resource_terminal_rejects_non_allowlisted_combinations(
    task_id: str, status: str, reason_code: str
) -> None:
    assert (
        _native_resource_transition(
            task_id=task_id,
            status=status,
            reason_code=reason_code,
            state=object(),
        )
        is None
    )
