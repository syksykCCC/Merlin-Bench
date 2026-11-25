"""C06: an ice-rule tensor network on a hidden torus."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from .common import DeterministicStream, Factor, FactorBlueprint, integer_parameter

CASE_ID: Final = "c06"
DEFAULT_PARAMETERS: Final[Mapping[str, Any]] = {"rows": 6, "columns": 24}


def build(stream: DeterministicStream, parameters: Mapping[str, Any]) -> FactorBlueprint:
    if set(parameters) != set(DEFAULT_PARAMETERS):
        raise ValueError("c06 parameters must be exactly rows and columns")
    rows = integer_parameter(parameters, "rows", minimum=4, maximum=10)
    columns = integer_parameter(parameters, "columns", minimum=4, maximum=40)
    sites = rows * columns
    directed_edges: list[tuple[int, int]] = []
    for row in range(rows):
        for column in range(columns):
            tail = row * columns + column
            directed_edges.append((tail, row * columns + (column + 1) % columns))
            directed_edges.append((tail, ((row + 1) % rows) * columns + column))
    if len(directed_edges) > 400:
        raise ValueError("c06 exceeds the variable envelope")
    incident: list[list[int]] = [[] for _ in range(sites)]
    for edge_id, (tail, head) in enumerate(directed_edges):
        incident[tail].append(edge_id)
        incident[head].append(edge_id)
    factors: list[Factor] = []
    for scope in incident:
        weights = [1 + stream.randbelow(3) for _ in range(6)]
        cursor = 0
        values: list[int] = []
        for assignment in range(16):
            if assignment.bit_count() == 2:
                values.append(weights[cursor])
                cursor += 1
            else:
                values.append(0)
        factors.append(Factor(tuple(scope), tuple(values)))
    factors.extend(
        Factor((edge_id,), (1, 1 + stream.randbelow(3))) for edge_id in range(len(directed_edges))
    )
    return FactorBlueprint(
        len(directed_edges),
        tuple(factors),
        {"mathematical_family": "six_vertex_torus", "rows": rows, "columns": columns},
    )


__all__ = ["CASE_ID", "DEFAULT_PARAMETERS", "build"]
