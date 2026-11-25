"""Registry for implemented New Structured Closest Vector cases."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Final

from aipbench.tasks.new_closest_vector_cases import c01, c02, c03, c04, c05, c06


@dataclass(frozen=True)
class CaseDefinition:
    parameters: Mapping[str, Any]
    builder: Any


CASE_DEFINITIONS: Final[Mapping[str, CaseDefinition]] = {
    c01.CASE_ID: CaseDefinition(dict(c01.DEFAULT_PARAMETERS), c01.build),
    c02.CASE_ID: CaseDefinition(dict(c02.DEFAULT_PARAMETERS), c02.build),
    c03.CASE_ID: CaseDefinition(dict(c03.DEFAULT_PARAMETERS), c03.build),
    c04.CASE_ID: CaseDefinition(dict(c04.DEFAULT_PARAMETERS), c04.build),
    c05.CASE_ID: CaseDefinition(dict(c05.DEFAULT_PARAMETERS), c05.build),
    c06.CASE_ID: CaseDefinition(dict(c06.DEFAULT_PARAMETERS), c06.build),
}
CASE_PARAMETERS: Final[Mapping[str, Mapping[str, Any]]] = {
    case_id: definition.parameters for case_id, definition in CASE_DEFINITIONS.items()
}

__all__ = ["CASE_DEFINITIONS", "CASE_PARAMETERS"]
