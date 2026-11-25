"""Minimal case scorer with a deliberately narrow filesystem authority."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _load_object(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"official scoring input is not an object: {path.name}")
    return value


def score_run(run_dir: Path) -> dict[str, Any]:
    """Score one case using only ``official/result.json`` and ``official/audit.json``."""
    official = run_dir.resolve() / "official"
    result = _load_object(official / "result.json")
    audit = _load_object(official / "audit.json")
    audit_passed = audit.get("audit_passed") is True
    accepted = result.get("terminal_status") == "ACCEPT"
    matching_status = audit.get("signed_terminal_status") == result.get("terminal_status")
    primary_score = int(
        audit_passed and accepted and matching_status and audit.get("official_result") == "PASS"
    )
    milestones = result.get("milestones")
    partial_progress = 1.0 if primary_score else 0.0
    if isinstance(milestones, dict):
        completed = milestones.get("rounds_completed")
        total = milestones.get("rounds_total")
        if isinstance(completed, int) and isinstance(total, int) and total > 0:
            partial_progress = max(0.0, min(1.0, completed / total))
    return {
        "audit_passed": audit_passed,
        "partial_progress": partial_progress,
        "primary_score": primary_score,
        "terminal_status": result.get("terminal_status"),
    }


__all__ = ["score_run"]
