"""Registry for the seven Sum-Check cases."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from . import c01, c02, c03, c04, c05, c06, c07
from .common import CaseDefinition


def _definition(case_id: str, parameters: Mapping[str, Any], builder: Any) -> CaseDefinition:
    return CaseDefinition(case_id, dict(parameters), builder)


CASE_DEFINITIONS: Final[Mapping[str, CaseDefinition]] = {
    module.CASE_ID: _definition(module.CASE_ID, module.DEFAULT_PARAMETERS, module.build)
    for module in (c01, c02, c03, c04, c05, c06, c07)
}
CASE_PARAMETERS: Final[Mapping[str, Mapping[str, Any]]] = {
    case_id: definition.parameters for case_id, definition in CASE_DEFINITIONS.items()
}

__all__ = ["CASE_DEFINITIONS", "CASE_PARAMETERS"]
