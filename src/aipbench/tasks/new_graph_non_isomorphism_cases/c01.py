"""C01: connected odd prism versus bipartite Moebius ladder."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from aipbench.tasks.new_graph_non_isomorphism_cases.common import (
    LogicalGraph,
    NewDeterministicStream,
    PairBlueprint,
)
from aipbench.tasks.shared.graph_non_isomorphism_cases.common import normalized_edges

CASE_ID: Final = "c01"
DEFAULT_PARAMETERS: Final[Mapping[str, Any]] = {"min_r": 701, "max_r": 1001}


def _prism(r: int) -> LogicalGraph:
    edges: set[tuple[int, int]] = set()
    for layer in range(2):
        offset = layer * r
        for index in range(r):
            other = offset + (index + 1) % r
            edges.add((min(offset + index, other), max(offset + index, other)))
    edges.update((index, r + index) for index in range(r))
    return LogicalGraph(2 * r, (0,) * (2 * r), normalized_edges(edges))


def _moebius_ladder(r: int) -> LogicalGraph:
    order = 2 * r
    edges = {
        (min(index, (index + 1) % order), max(index, (index + 1) % order)) for index in range(order)
    }
    edges.update((index, index + r) for index in range(r))
    return LogicalGraph(order, (0,) * order, normalized_edges(edges))


def build(stream: NewDeterministicStream, parameters: Mapping[str, Any]) -> PairBlueprint:
    if set(parameters) != set(DEFAULT_PARAMETERS):
        raise ValueError("unsupported new GNI c01 parameters")
    minimum = parameters["min_r"]
    maximum = parameters["max_r"]
    if (
        isinstance(minimum, bool)
        or not isinstance(minimum, int)
        or isinstance(maximum, bool)
        or not isinstance(maximum, int)
        or minimum < 3
        or maximum < minimum
    ):
        raise ValueError("invalid c01 range")
    odd_values = list(range(minimum | 1, maximum + 1, 2))
    if not odd_values:
        raise ValueError("c01 range contains no odd value")
    r = odd_values[stream.randbelow(len(odd_values))]
    return PairBlueprint(
        _prism(r),
        _moebius_ladder(r),
        {"construction": "connected_prism_moebius", "r": r},
    )


__all__ = ["CASE_ID", "DEFAULT_PARAMETERS", "build"]
