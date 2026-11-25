"""C06: a deep width-two layered diagnostic network."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from aipbench.tasks.new_maxflow_cases.common import (
    CaseBlueprint,
    LogicalEdge,
    NewMaxFlowStream,
    integer_parameter,
)

CASE_ID: Final = "c06"
DEFAULT_PARAMETERS: Final[Mapping[str, Any]] = {
    "num_layers": 3_000,
    "layer_width": 2,
}


def build(stream: NewMaxFlowStream, parameters: Mapping[str, Any]) -> CaseBlueprint:
    num_layers = integer_parameter(parameters, "num_layers", minimum=2)
    layer_width = integer_parameter(parameters, "layer_width", minimum=2)
    if layer_width != 2:
        raise ValueError("C06 currently requires layer_width=2")

    source = 0
    first_layer_vertex = 1
    sink = first_layer_vertex + num_layers * layer_width

    def layer_vertex(layer: int, offset: int) -> int:
        return first_layer_vertex + layer * layer_width + offset

    edges: list[LogicalEdge] = []
    for offset in range(layer_width):
        edges.append(LogicalEdge(source, layer_vertex(0, offset), 1))
        edges.append(LogicalEdge(layer_vertex(num_layers - 1, offset), sink, 1))

    for layer in range(num_layers - 1):
        for tail_offset in range(layer_width):
            for head_offset in range(layer_width):
                edges.append(
                    LogicalEdge(
                        layer_vertex(layer, tail_offset),
                        layer_vertex(layer + 1, head_offset),
                        1,
                    )
                )

    del stream
    return CaseBlueprint(
        num_vertices=sink + 1,
        source=source,
        sink=sink,
        edges=tuple(edges),
        reference_flow_value=layer_width,
        reference_source_side_cut=frozenset({source}),
        metadata={
            "mathematical_family": "deep_width_two_layered_diagnostic",
            "num_layers": num_layers,
            "layer_width": layer_width,
            "source_sink_distance": num_layers + 1,
            "maximum_flow_is_non_unique": True,
            "general_hardness_claimed": False,
        },
    )
