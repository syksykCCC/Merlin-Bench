"""C05: a sparse large cluster/interface unit-capacity network."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from aipbench.tasks.new_maxflow_cases.common import (
    CaseBlueprint,
    LogicalEdge,
    NewMaxFlowStream,
    integer_parameter,
)

CASE_ID: Final = "c05"
DEFAULT_PARAMETERS: Final[Mapping[str, Any]] = {
    "num_clusters": 48,
    "cluster_width": 128,
    "internal_matchings": 3,
}


def build(stream: NewMaxFlowStream, parameters: Mapping[str, Any]) -> CaseBlueprint:
    num_clusters = integer_parameter(parameters, "num_clusters", minimum=2)
    cluster_width = integer_parameter(parameters, "cluster_width", minimum=2)
    internal_matchings = integer_parameter(parameters, "internal_matchings", minimum=2)
    if internal_matchings > cluster_width:
        raise ValueError("internal_matchings cannot exceed cluster_width")

    source = 0
    first_cluster_vertex = 1
    sink = first_cluster_vertex + 2 * num_clusters * cluster_width

    def entry(cluster: int, index: int) -> int:
        return first_cluster_vertex + 2 * cluster * cluster_width + index

    def exit_vertex(cluster: int, index: int) -> int:
        return entry(cluster, 0) + cluster_width + index

    edges: list[LogicalEdge] = []
    for index in range(cluster_width):
        edges.append(LogicalEdge(source, entry(0, index), 1))
        edges.append(LogicalEdge(exit_vertex(num_clusters - 1, index), sink, 1))

    internal_offsets: list[tuple[int, ...]] = []
    for cluster in range(num_clusters):
        nonzero_offsets = list(range(1, cluster_width))
        stream.shuffle(nonzero_offsets)
        offsets = (0, *nonzero_offsets[: internal_matchings - 1])
        internal_offsets.append(offsets)
        for offset in offsets:
            edges.extend(
                LogicalEdge(
                    entry(cluster, index),
                    exit_vertex(cluster, (index + offset) % cluster_width),
                    1,
                )
                for index in range(cluster_width)
            )

    interface_offsets: list[int] = []
    for cluster in range(num_clusters - 1):
        offset = stream.randbelow(cluster_width)
        interface_offsets.append(offset)
        edges.extend(
            LogicalEdge(
                exit_vertex(cluster, index),
                entry(cluster + 1, (index + offset) % cluster_width),
                1,
            )
            for index in range(cluster_width)
        )

    return CaseBlueprint(
        num_vertices=sink + 1,
        source=source,
        sink=sink,
        edges=tuple(edges),
        reference_flow_value=cluster_width,
        reference_source_side_cut=frozenset({source}),
        metadata={
            "mathematical_family": "sparse_cluster_interface_unit_network",
            "num_clusters": num_clusters,
            "cluster_width": cluster_width,
            "internal_matchings": internal_matchings,
            "internal_offsets": [list(offsets) for offsets in internal_offsets],
            "interface_offsets": interface_offsets,
            "maximum_flow_is_non_unique": True,
        },
    )
