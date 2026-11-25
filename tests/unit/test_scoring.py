from __future__ import annotations

import json
from pathlib import Path

from aipbench.scoring import score_run


def _write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def test_scorer_uses_only_official_result_and_audit(tmp_path: Path) -> None:
    _write(
        tmp_path / "official" / "result.json",
        {"terminal_status": "REJECT", "milestones": {"rounds_completed": 3, "rounds_total": 6}},
    )
    _write(
        tmp_path / "official" / "audit.json",
        {"audit_passed": True, "official_result": "FAIL", "signed_terminal_status": "REJECT"},
    )
    _write(
        tmp_path / "workspace" / "final_report.json",
        {"accepted": True, "primary_score": 1},
    )
    assert score_run(tmp_path) == {
        "audit_passed": True,
        "partial_progress": 0.5,
        "primary_score": 0,
        "terminal_status": "REJECT",
    }


def test_scorer_requires_signed_accept_and_passing_audit(tmp_path: Path) -> None:
    _write(
        tmp_path / "official" / "result.json",
        {"terminal_status": "ACCEPT", "milestones": {}},
    )
    _write(
        tmp_path / "official" / "audit.json",
        {"audit_passed": True, "official_result": "PASS", "signed_terminal_status": "ACCEPT"},
    )
    assert score_run(tmp_path)["primary_score"] == 1
