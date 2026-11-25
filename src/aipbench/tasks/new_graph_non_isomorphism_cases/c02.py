"""C02: connected Cartesian amplifications of the Shrikhande/rook pair."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from aipbench.tasks.new_graph_non_isomorphism_cases.common import (
    NewDeterministicStream,
    PairBlueprint,
    cartesian_product,
    cycle_graph,
)
from aipbench.tasks.shared.graph_non_isomorphism_cases.common import rook_graph, shrikhande_graph

CASE_ID: Final = "c02"
DEFAULT_PARAMETERS: Final[Mapping[str, Any]] = {
    "min_cycle_length": 89,
    "max_cycle_length": 127,
}


def build(stream: NewDeterministicStream, parameters: Mapping[str, Any]) -> PairBlueprint:
    if set(parameters) != set(DEFAULT_PARAMETERS):
        raise ValueError("unsupported new GNI c02 parameters")
    minimum = parameters["min_cycle_length"]
    maximum = parameters["max_cycle_length"]
    if (
        isinstance(minimum, bool)
        or not isinstance(minimum, int)
        or isinstance(maximum, bool)
        or not isinstance(maximum, int)
        or minimum < 5
        or maximum < minimum
    ):
        raise ValueError("invalid c02 cycle range")
    odd_lengths = list(range(minimum | 1, maximum + 1, 2))
    length = odd_lengths[stream.randbelow(len(odd_lengths))]
    cycle = cycle_graph(length)
    return PairBlueprint(
        cartesian_product(shrikhande_graph(), cycle),
        cartesian_product(rook_graph(), cycle),
        {
            "construction": "connected_srg_cartesian_cycle",
            "cycle_length": length,
            "root_order": 16,
        },
    )


__all__ = ["CASE_ID", "DEFAULT_PARAMETERS", "build"]
