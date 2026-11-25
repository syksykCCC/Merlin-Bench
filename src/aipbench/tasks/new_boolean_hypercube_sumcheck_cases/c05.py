"""C05: monomer--dimer weights on a hidden cylindrical strip."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from .common import DeterministicStream, Factor, FactorBlueprint, integer_parameter, normalized_edge

CASE_ID: Final = "c05"
DEFAULT_PARAMETERS: Final[Mapping[str, Any]] = {"rows": 6, "columns": 30}


def build(stream: DeterministicStream, parameters: Mapping[str, Any]) -> FactorBlueprint:
    if set(parameters) != set(DEFAULT_PARAMETERS):
        raise ValueError("c05 parameters must be exactly rows and columns")
    rows = integer_parameter(parameters, "rows", minimum=4, maximum=10)
    columns = integer_parameter(parameters, "columns", minimum=4, maximum=60)
    logical_vertices = rows * columns

    def vertex(row: int, column: int) -> int:
        return column * rows + row

    edges: set[tuple[int, int]] = set()
    for column in range(columns):
        for row in range(rows):
            edges.add(normalized_edge(vertex(row, column), vertex((row + 1) % rows, column)))
            if column + 1 < columns:
                edges.add(normalized_edge(vertex(row, column), vertex(row, column + 1)))
    graph_edges = tuple(sorted(edges))
    if len(graph_edges) > 400:
        raise ValueError("c05 exceeds the variable envelope")
    factors = [
        Factor((edge_id,), (1, 2 + stream.randbelow(7))) for edge_id in range(len(graph_edges))
    ]
    incident: list[list[int]] = [[] for _ in range(logical_vertices)]
    for edge_id, (first, second) in enumerate(graph_edges):
        incident[first].append(edge_id)
        incident[second].append(edge_id)
    for scope in incident:
        factors.append(
            Factor(
                tuple(scope),
                tuple(int(index.bit_count() <= 1) for index in range(1 << len(scope))),
            )
        )
    return FactorBlueprint(
        len(graph_edges),
        tuple(factors),
        {
            "mathematical_family": "cylindrical_monomer_dimer",
            "logical_vertices": logical_vertices,
            "logical_edges": len(graph_edges),
        },
    )


__all__ = ["CASE_ID", "DEFAULT_PARAMETERS", "build"]
