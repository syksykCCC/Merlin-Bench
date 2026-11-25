"""Registry for implemented New List Graph Homomorphism cases."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final

from aipbench.tasks.new_homomorphism_cases import c01, c02, c03, c04, c05, c06
from aipbench.tasks.shared.homomorphism_cases.common import CaseDefinition

CASE_DEFINITIONS: Final[Mapping[str, CaseDefinition]] = {
    c01.CASE_ID: CaseDefinition(
        case_id=c01.CASE_ID,
        parameters=dict(c01.DEFAULT_PARAMETERS),
        builder=c01.build,
    ),
    c02.CASE_ID: CaseDefinition(
        case_id=c02.CASE_ID,
        parameters=dict(c02.DEFAULT_PARAMETERS),
        builder=c02.build,
    ),
    c03.CASE_ID: CaseDefinition(
        case_id=c03.CASE_ID,
        parameters=dict(c03.DEFAULT_PARAMETERS),
        builder=c03.build,
    ),
    c04.CASE_ID: CaseDefinition(
        case_id=c04.CASE_ID,
        parameters=dict(c04.DEFAULT_PARAMETERS),
        builder=c04.build,
    ),
    c05.CASE_ID: CaseDefinition(
        case_id=c05.CASE_ID,
        parameters=dict(c05.DEFAULT_PARAMETERS),
        builder=c05.build,
    ),
    c06.CASE_ID: CaseDefinition(
        case_id=c06.CASE_ID,
        parameters=dict(c06.DEFAULT_PARAMETERS),
        builder=c06.build,
    ),
}
CASE_PARAMETERS: Final[Mapping[str, Mapping[str, object]]] = {
    case_id: definition.parameters for case_id, definition in CASE_DEFINITIONS.items()
}

__all__ = ["CASE_DEFINITIONS", "CASE_PARAMETERS"]
