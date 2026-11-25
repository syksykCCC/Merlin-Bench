"""C01: rank-one factors on a hidden four-regular graph."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from .common import (
    DeterministicStream,
    Factor,
    FactorBlueprint,
    integer_parameter,
    rank_one_table,
    two_cycle_edges,
)

CASE_ID: Final = "c01"
DEFAULT_PARAMETERS: Final[Mapping[str, Any]] = {"num_variables": 384}


def build(stream: DeterministicStream, parameters: Mapping[str, Any]) -> FactorBlueprint:
    if set(parameters) != set(DEFAULT_PARAMETERS):
        raise ValueError("c01 parameters must be exactly num_variables")
    count = integer_parameter(parameters, "num_variables", minimum=32, maximum=400)
    factors = tuple(Factor(edge, rank_one_table(stream)) for edge in two_cycle_edges(stream, count))
    return FactorBlueprint(count, factors, {"mathematical_family": "rank_one_expander"})


__all__ = ["CASE_ID", "DEFAULT_PARAMETERS", "build"]
