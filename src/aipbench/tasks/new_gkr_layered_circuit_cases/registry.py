"""Frozen case registry for the 600-second new GKR task."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Final

from aipbench.tasks.shared.gkr_layered_circuit_cases import c01, c02, c03, c04
from aipbench.tasks.shared.gkr_layered_circuit_cases.common import (
    CircuitBlueprint,
    DeterministicStream,
)

from . import c05, c06, c07


@dataclass(frozen=True)
class CaseDefinition:
    parameters: Mapping[str, Any]
    builder: Callable[[DeterministicStream, Mapping[str, Any]], CircuitBlueprint]


CASE_DEFINITIONS: Final[Mapping[str, CaseDefinition]] = {
    "c01": CaseDefinition({"vector_length": 64}, c01.build),
    "c02": CaseDefinition({"batch_size": 8, "time_steps": 6}, c02.build),
    "c03": CaseDefinition({"batch_size": 1, "matrix_order": 8}, c03.build),
    "c04": CaseDefinition({"vector_length": 128}, c04.build),
    "c05": CaseDefinition(c05.DEFAULT_PARAMETERS, c05.build),
    "c06": CaseDefinition(c06.DEFAULT_PARAMETERS, c06.build),
    "c07": CaseDefinition(c07.DEFAULT_PARAMETERS, c07.build),
}

CASE_PARAMETERS: Final[Mapping[str, Mapping[str, Any]]] = {
    case_id: definition.parameters for case_id, definition in CASE_DEFINITIONS.items()
}


__all__ = ["CASE_DEFINITIONS", "CASE_PARAMETERS", "CaseDefinition"]
