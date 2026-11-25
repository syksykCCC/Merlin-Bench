"""Registry for the eight T3.1 challenge families."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from aipbench.tasks.machine_checked_mathematics_cases import (
    c01,
    c02,
    c03,
    c04,
    c05,
    c06,
    c07,
    c08,
)
from aipbench.tasks.machine_checked_mathematics_cases.common import CaseDefinition, solution_source


def _definition(module: Any) -> CaseDefinition:
    return CaseDefinition(
        case_id=module.CASE_ID,
        title=module.TITLE,
        parameters=dict(module.DEFAULT_PARAMETERS),
        builder=module.build,
        solver=module.solve,
        solution_renderer=getattr(module, "render_solution", solution_source),
    )


CASE_DEFINITIONS: Final[Mapping[str, CaseDefinition]] = {
    module.CASE_ID: _definition(module) for module in (c01, c02, c03, c04, c05, c06, c07, c08)
}

CASE_PARAMETERS: Final[Mapping[str, Mapping[str, Any]]] = {
    case_id: definition.parameters for case_id, definition in CASE_DEFINITIONS.items()
}
CASE_TITLES: Final[Mapping[str, str]] = {
    case_id: definition.title for case_id, definition in CASE_DEFINITIONS.items()
}

__all__ = ["CASE_DEFINITIONS", "CASE_PARAMETERS", "CASE_TITLES"]
