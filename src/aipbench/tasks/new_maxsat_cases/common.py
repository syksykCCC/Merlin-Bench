"""Shared primitives for the independent new Weighted Partial MaxSAT task."""

from __future__ import annotations

from typing import Final

from aipbench.tasks.shared.maxsat_cases.common import (
    CaseBlueprint,
    CaseDefinition,
    Clause,
    DeterministicStream,
    FinalizedCase,
    SoftClause,
    integer_parameter,
)
from aipbench.tasks.shared.maxsat_cases.common import finalize_blueprint as _finalize_blueprint


class NewMaxSatStream(DeterministicStream):
    """Deterministic stream with a task-specific domain."""

    _DOMAIN: Final = b"aipbench/new-weighted-partial-maxsat/generator/v1\x00"


def finalize_blueprint(*, blueprint: CaseBlueprint, stream: NewMaxSatStream) -> FinalizedCase:
    return _finalize_blueprint(blueprint=blueprint, stream=stream)


__all__ = [
    "CaseBlueprint",
    "CaseDefinition",
    "Clause",
    "FinalizedCase",
    "NewMaxSatStream",
    "SoftClause",
    "finalize_blueprint",
    "integer_parameter",
]
