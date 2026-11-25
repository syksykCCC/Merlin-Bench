"""C04: an uncolored, enlarged CFI parity pair."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from aipbench.tasks.new_graph_non_isomorphism_cases.common import (
    LogicalGraph,
    NewDeterministicStream,
    PairBlueprint,
)
from aipbench.tasks.shared.graph_non_isomorphism_cases import c05 as cfi_primitives

CASE_ID: Final = "c04"
DEFAULT_PARAMETERS: Final[Mapping[str, Any]] = {"lift_factor": 12}


def _uncolored(graph: LogicalGraph) -> LogicalGraph:
    return LogicalGraph(graph.num_vertices, (0,) * graph.num_vertices, graph.edges)


def build(stream: NewDeterministicStream, parameters: Mapping[str, Any]) -> PairBlueprint:
    if set(parameters) != set(DEFAULT_PARAMETERS):
        raise ValueError("unsupported new GNI c04 parameters")
    factor = parameters["lift_factor"]
    if isinstance(factor, bool) or not isinstance(factor, int) or not 4 <= factor <= 24:
        raise ValueError("c04 lift_factor must lie in [4,24]")
    base = cfi_primitives._cyclic_lift(cfi_primitives._gq_incidence_graph(), factor, stream)
    even = cfi_primitives._conditioned_twists(len(base.edges), 0, stream)
    odd = cfi_primitives._conditioned_twists(len(base.edges), 1, stream)
    graph0 = _uncolored(cfi_primitives._cfi_graph(base, even))
    graph1 = _uncolored(cfi_primitives._cfi_graph(base, odd))
    return PairBlueprint(
        graph0,
        graph1,
        {
            "construction": "uncolored_cfi_parity",
            "lift_factor": factor,
            "base_num_vertices": base.num_vertices,
            "base_num_edges": len(base.edges),
        },
    )


__all__ = ["CASE_ID", "DEFAULT_PARAMETERS", "build"]
