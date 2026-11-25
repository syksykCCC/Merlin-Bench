"""C02: a weighted signed-equivalence model on a hidden expander."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from .common import (
    DeterministicStream,
    Factor,
    FactorBlueprint,
    integer_parameter,
    signed_table,
    two_cycle_edges,
)

CASE_ID: Final = "c02"
DEFAULT_PARAMETERS: Final[Mapping[str, Any]] = {"num_variables": 360}


def build(stream: DeterministicStream, parameters: Mapping[str, Any]) -> FactorBlueprint:
    if set(parameters) != set(DEFAULT_PARAMETERS):
        raise ValueError("c02 parameters must be exactly num_variables")
    count = integer_parameter(parameters, "num_variables", minimum=32, maximum=400)
    labels = [stream.randbelow(2) for _ in range(count)]
    factors = [
        Factor(edge, signed_table(stream, disequality=bool(labels[edge[0]] ^ labels[edge[1]])))
        for edge in two_cycle_edges(stream, count)
    ]
    factors.extend(
        Factor((variable,), (1 + stream.randbelow(7), 1 + stream.randbelow(7)))
        for variable in range(count)
    )
    return FactorBlueprint(
        count,
        tuple(factors),
        {"mathematical_family": "signed_equivalence_expander"},
    )


__all__ = ["CASE_ID", "DEFAULT_PARAMETERS", "build"]
