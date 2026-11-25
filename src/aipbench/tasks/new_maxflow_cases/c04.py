"""C04: a wide layered unit-capacity permutation network."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from aipbench.tasks.new_maxflow_cases.common import (
    CaseBlueprint,
    LogicalEdge,
    NewMaxFlowStream,
    integer_parameter,
)

CASE_ID: Final = "c04"
DEFAULT_PARAMETERS: Final[Mapping[str, Any]] = {
    "num_columns": 64,
    "column_width": 64,
    "matchings_per_transition": 3,
}


def build(stream: NewMaxFlowStream, parameters: Mapping[str, Any]) -> CaseBlueprint:
    num_columns = integer_parameter(parameters, "num_columns", minimum=2)
    column_width = integer_parameter(parameters, "column_width", minimum=2)
    matchings_per_transition = integer_parameter(parameters, "matchings_per_transition", minimum=2)
    if matchings_per_transition > column_width:
        raise ValueError("matchings_per_transition cannot exceed column_width")

    source = 0
    first_grid_vertex = 1
    sink = first_grid_vertex + num_columns * column_width

    def grid_vertex(column: int, row: int) -> int:
        return first_grid_vertex + column * column_width + row

    edges: list[LogicalEdge] = []
    for row in range(column_width):
        edges.append(LogicalEdge(source, grid_vertex(0, row), 1))
        edges.append(LogicalEdge(grid_vertex(num_columns - 1, row), sink, 1))

    transition_offsets: list[tuple[int, ...]] = []
    for column in range(num_columns - 1):
        nonzero_offsets = list(range(1, column_width))
        stream.shuffle(nonzero_offsets)
        offsets = (0, *nonzero_offsets[: matchings_per_transition - 1])
        transition_offsets.append(offsets)
        for offset in offsets:
            edges.extend(
                LogicalEdge(
                    grid_vertex(column, row),
                    grid_vertex(column + 1, (row + offset) % column_width),
                    1,
                )
                for row in range(column_width)
            )

    return CaseBlueprint(
        num_vertices=sink + 1,
        source=source,
        sink=sink,
        edges=tuple(edges),
        reference_flow_value=column_width,
        reference_source_side_cut=frozenset({source}),
        metadata={
            "mathematical_family": "layered_permutation_unit_network",
            "num_columns": num_columns,
            "column_width": column_width,
            "matchings_per_transition": matchings_per_transition,
            "transition_offsets": [list(offsets) for offsets in transition_offsets],
            "maximum_flow_is_non_unique": True,
        },
    )
