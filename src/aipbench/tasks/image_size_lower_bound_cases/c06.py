"""C06: greedy projection onto independent sets of a rectangular grid."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from aipbench.tasks.image_size_lower_bound_cases.common import (
    CircuitBlueprint,
    CircuitBuilder,
    DeterministicStream,
    hide_outputs,
    integer_parameter,
    make_blueprint,
)

CASE_ID: Final = "c06"
DEFAULT_PARAMETERS: Final[Mapping[str, Any]] = {"rows": 3, "columns": 4}


def count_grid_independent_sets(rows: int, columns: int) -> int:
    masks = [mask for mask in range(1 << rows) if not mask & (mask << 1)]
    counts = {mask: 1 for mask in masks}
    for _ in range(1, columns):
        counts = {
            mask: sum(value for previous, value in counts.items() if not mask & previous)
            for mask in masks
        }
    return sum(counts.values())


def build(stream: DeterministicStream, parameters: Mapping[str, Any]) -> CircuitBlueprint:
    if set(parameters) != set(DEFAULT_PARAMETERS):
        raise ValueError("c06 parameters must be exactly rows and columns")
    rows = integer_parameter(parameters, "rows", minimum=2, maximum=4)
    columns = integer_parameter(parameters, "columns", minimum=2, maximum=8)
    vertex_count = rows * columns
    if vertex_count > 16:
        raise ValueError("c06 exceeds the task-wide input envelope")
    builder = CircuitBuilder(vertex_count)
    input_wires = list(range(vertex_count))
    stream.shuffle(input_wires)
    scan_order = list(range(vertex_count))
    stream.shuffle(scan_order)
    scan_position = {vertex: index for index, vertex in enumerate(scan_order)}
    selected: list[int | None] = [None] * vertex_count
    for vertex in scan_order:
        row, column = divmod(vertex, columns)
        neighbors = []
        for other_row, other_column in (
            (row - 1, column),
            (row + 1, column),
            (row, column - 1),
            (row, column + 1),
        ):
            if 0 <= other_row < rows and 0 <= other_column < columns:
                neighbor = other_row * columns + other_column
                if scan_position[neighbor] < scan_position[vertex]:
                    neighbor_wire = selected[neighbor]
                    assert neighbor_wire is not None
                    neighbors.append(builder.not_(neighbor_wire))
        selected[vertex] = builder.and_many([input_wires[vertex], *neighbors])
    logical = [wire for wire in selected if wire is not None]
    outputs = hide_outputs(builder, logical, stream)
    return make_blueprint(
        builder=builder,
        outputs=outputs,
        image_size=count_grid_independent_sets(rows, columns),
        metadata={
            "mathematical_family": "grid_independent_sets",
            "rows": rows,
            "columns": columns,
        },
    )


__all__ = ["CASE_ID", "DEFAULT_PARAMETERS", "build", "count_grid_independent_sets"]
