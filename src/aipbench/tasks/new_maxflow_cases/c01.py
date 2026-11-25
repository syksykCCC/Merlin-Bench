"""C01: independent two-edge channels for protocol calibration."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from aipbench.tasks.new_maxflow_cases.common import (
    CaseBlueprint,
    LogicalEdge,
    NewMaxFlowStream,
    integer_parameter,
)

CASE_ID: Final = "c01"
DEFAULT_PARAMETERS: Final[Mapping[str, Any]] = {
    "min_channels": 8,
    "max_channels": 16,
    "min_capacity": 3,
    "max_capacity": 29,
}


def build(stream: NewMaxFlowStream, parameters: Mapping[str, Any]) -> CaseBlueprint:
    min_channels = integer_parameter(parameters, "min_channels", minimum=2)
    max_channels = integer_parameter(parameters, "max_channels", minimum=2)
    min_capacity = integer_parameter(parameters, "min_capacity", minimum=1)
    max_capacity = integer_parameter(parameters, "max_capacity", minimum=1)
    if max_channels < min_channels or max_capacity < min_capacity:
        raise ValueError("invalid C01 parameter interval")

    channel_count = stream.randint(min_channels, max_channels)
    source = 0
    sink = channel_count + 1
    capacities = [stream.randint(min_capacity, max_capacity) for _ in range(channel_count)]
    edges: list[LogicalEdge] = []
    for offset, capacity in enumerate(capacities, start=1):
        edges.append(LogicalEdge(source, offset, capacity))
        edges.append(LogicalEdge(offset, sink, capacity))

    flow_value = sum(capacities)
    return CaseBlueprint(
        num_vertices=channel_count + 2,
        source=source,
        sink=sink,
        edges=tuple(edges),
        reference_flow_value=flow_value,
        reference_source_side_cut=frozenset({source}),
        metadata={
            "mathematical_family": "independent_two_edge_channels",
            "channel_count": channel_count,
            "all_source_edges_saturable": True,
        },
    )
