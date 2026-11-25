"""Registry for the six opaque T2.4 case distributions."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from aipbench.tasks.image_size_lower_bound_cases import c01, c02, c03, c04, c05, c06
from aipbench.tasks.image_size_lower_bound_cases.common import CaseDefinition


def _definition(case_id: str, parameters: Mapping[str, Any], builder: Any) -> CaseDefinition:
    return CaseDefinition(case_id, dict(parameters), builder)


CASE_DEFINITIONS: Final[Mapping[str, CaseDefinition]] = {
    c01.CASE_ID: _definition(c01.CASE_ID, c01.DEFAULT_PARAMETERS, c01.build),
    c02.CASE_ID: _definition(c02.CASE_ID, c02.DEFAULT_PARAMETERS, c02.build),
    c03.CASE_ID: _definition(c03.CASE_ID, c03.DEFAULT_PARAMETERS, c03.build),
    c04.CASE_ID: _definition(c04.CASE_ID, c04.DEFAULT_PARAMETERS, c04.build),
    c05.CASE_ID: _definition(c05.CASE_ID, c05.DEFAULT_PARAMETERS, c05.build),
    c06.CASE_ID: _definition(c06.CASE_ID, c06.DEFAULT_PARAMETERS, c06.build),
}

CASE_PARAMETERS: Final[Mapping[str, Mapping[str, Any]]] = {
    case_id: definition.parameters for case_id, definition in CASE_DEFINITIONS.items()
}

__all__ = ["CASE_DEFINITIONS", "CASE_PARAMETERS"]
