"""Frozen eight-case registry for Dafny-verified programs."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Final

from aipbench.tasks.dafny_verified_program_cases import c01, c02, c03, c04, c05, c06, c07, c08
from aipbench.tasks.dafny_verified_program_cases.common import (
    DafnyCaseBlueprint,
    DeterministicStream,
)


@dataclass(frozen=True)
class DafnyCaseDefinition:
    title: str
    difficulty: str
    parameters: Mapping[str, int]
    builder: Callable[[DeterministicStream, Mapping[str, int]], DafnyCaseBlueprint]


CASE_DEFINITIONS: Final[dict[str, DafnyCaseDefinition]] = {
    "c01": DafnyCaseDefinition("Stable partition preservation", "H1", {}, c01.build),
    "c02": DafnyCaseDefinition("Boundary-safe lower-bound search", "H1", {}, c02.build),
    "c03": DafnyCaseDefinition("Capacity-constrained reservation update", "H2", {}, c03.build),
    "c04": DafnyCaseDefinition("Precedence-constrained earliest schedule", "H2", {}, c04.build),
    "c05": DafnyCaseDefinition("Dependency-order validation", "H3", {}, c05.build),
    "c06": DafnyCaseDefinition("Audited priority firewall batch evaluation", "H3", {}, c06.build),
    "c07": DafnyCaseDefinition(
        "Reference-counted handle-table invariant preservation", "H4", {}, c07.build
    ),
    "c08": DafnyCaseDefinition("Free-list memory-pool invariant preservation", "H4", {}, c08.build),
}

CASE_PARAMETERS: Final[dict[str, Mapping[str, int]]] = {
    case_id: definition.parameters for case_id, definition in CASE_DEFINITIONS.items()
}
CASE_TITLES: Final[dict[str, str]] = {
    case_id: definition.title for case_id, definition in CASE_DEFINITIONS.items()
}


__all__ = [
    "CASE_DEFINITIONS",
    "CASE_PARAMETERS",
    "CASE_TITLES",
    "DafnyCaseDefinition",
]
