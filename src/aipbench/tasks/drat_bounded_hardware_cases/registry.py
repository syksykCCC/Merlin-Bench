"""Frozen eight-case registry for bounded hardware safety."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Final

from aipbench.tasks.drat_bounded_hardware_cases import c01, c02, c03, c04, c05, c06, c07, c08
from aipbench.tasks.drat_bounded_hardware_cases.common import (
    DeterministicStream,
    HardwareBlueprint,
)


@dataclass(frozen=True)
class HardwareCaseDefinition:
    title: str
    difficulty: str
    parameters: Mapping[str, int]
    builder: Callable[[DeterministicStream, Mapping[str, int]], HardwareBlueprint]


CASE_DEFINITIONS: Final[dict[str, HardwareCaseDefinition]] = {
    "c01": HardwareCaseDefinition("FIFO occupancy safety", "H1", {}, c01.build),
    "c02": HardwareCaseDefinition("FIFO underflow safety", "H1", {}, c02.build),
    "c03": HardwareCaseDefinition("Round-robin mutual exclusion", "H2", {}, c03.build),
    "c04": HardwareCaseDefinition("Round-robin bounded fairness", "H2", {}, c04.build),
    "c05": HardwareCaseDefinition("Credit-router conservation", "H3", {}, c05.build),
    "c06": HardwareCaseDefinition("Credit-router forwarding safety", "H3", {}, c06.build),
    "c07": HardwareCaseDefinition("Pipeline flush-stall safety", "H4", {}, c07.build),
    "c08": HardwareCaseDefinition("Pipeline writeback consistency", "H4", {}, c08.build),
}

CASE_PARAMETERS: Final[dict[str, Mapping[str, int]]] = {
    case_id: definition.parameters for case_id, definition in CASE_DEFINITIONS.items()
}
CASE_TITLES: Final[dict[str, str]] = {
    case_id: definition.title for case_id, definition in CASE_DEFINITIONS.items()
}

__all__ = ["CASE_DEFINITIONS", "CASE_PARAMETERS", "CASE_TITLES", "HardwareCaseDefinition"]
