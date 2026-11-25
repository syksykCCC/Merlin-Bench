"""Shared primitives for the independent new max-flow distributions."""

from __future__ import annotations

from typing import Final

from aipbench.tasks.shared.maxflow_cases.common import (
    CaseBlueprint,
    CaseDefinition,
    DeterministicStream,
    FinalizedCase,
    LogicalEdge,
    integer_parameter,
    positive_composition,
)
from aipbench.tasks.shared.maxflow_cases.common import finalize_blueprint as _finalize_blueprint


class NewMaxFlowStream(DeterministicStream):
    """Deterministic stream with a task-specific domain."""

    _DOMAIN: Final = b"aipbench/new-maxflow/generator/v1\x00"


def finalize_blueprint(
    *, case_id: str, blueprint: CaseBlueprint, stream: NewMaxFlowStream
) -> FinalizedCase:
    finalized = _finalize_blueprint(case_id=case_id, blueprint=blueprint, stream=stream)
    metadata = dict(finalized.generation_metadata)
    metadata["generator"] = f"new-maxflow/{case_id}/v1"
    return FinalizedCase(
        public_instance=finalized.public_instance,
        private_instance=finalized.private_instance,
        generation_metadata=metadata,
    )


__all__ = [
    "CaseBlueprint",
    "CaseDefinition",
    "FinalizedCase",
    "LogicalEdge",
    "NewMaxFlowStream",
    "finalize_blueprint",
    "integer_parameter",
    "positive_composition",
]
