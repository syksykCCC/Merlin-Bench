"""C03: many parallel shards in a large-integer serial network."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from aipbench.tasks.new_maxflow_cases.common import (
    CaseBlueprint,
    LogicalEdge,
    NewMaxFlowStream,
    integer_parameter,
    positive_composition,
)

CASE_ID: Final = "c03"
DEFAULT_PARAMETERS: Final[Mapping[str, Any]] = {
    "num_segments": 256,
    "bundle_edges": 72,
    "bandwidth": 3_000_000_007,
    "return_edges": 512,
    "max_return_capacity": 1_000_000,
}


def build(stream: NewMaxFlowStream, parameters: Mapping[str, Any]) -> CaseBlueprint:
    num_segments = integer_parameter(parameters, "num_segments", minimum=2)
    bundle_edges = integer_parameter(parameters, "bundle_edges", minimum=2)
    bandwidth = integer_parameter(parameters, "bandwidth", minimum=bundle_edges)
    return_edges = integer_parameter(parameters, "return_edges", minimum=0)
    max_return_capacity = integer_parameter(parameters, "max_return_capacity", minimum=1)
    maximum_return_pairs = num_segments * (num_segments - 1) // 2
    if return_edges > maximum_return_pairs:
        raise ValueError("too many distinct backward edges for the serial network")

    edges: list[LogicalEdge] = []
    for segment in range(num_segments):
        shards = positive_composition(bandwidth, bundle_edges, stream)
        edges.extend(LogicalEdge(segment, segment + 1, capacity) for capacity in shards)

    backward_pairs: set[tuple[int, int]] = set()
    while len(backward_pairs) < return_edges:
        tail = 2 + stream.randbelow(num_segments - 1)
        head = stream.randbelow(tail - 1)
        backward_pairs.add((tail, head))
    ordered_backward_pairs = sorted(backward_pairs)
    stream.shuffle(ordered_backward_pairs)
    edges.extend(
        LogicalEdge(tail, head, stream.randint(1, max_return_capacity))
        for tail, head in ordered_backward_pairs
    )

    return CaseBlueprint(
        num_vertices=num_segments + 1,
        source=0,
        sink=num_segments,
        edges=tuple(edges),
        reference_flow_value=bandwidth,
        reference_source_side_cut=frozenset({0}),
        metadata={
            "mathematical_family": "parallel_sharded_serial_network",
            "num_segments": num_segments,
            "bundle_edges": bundle_edges,
            "bandwidth": bandwidth,
            "return_edges": return_edges,
            "all_forward_bundles_sum_to_bandwidth": True,
        },
    )
