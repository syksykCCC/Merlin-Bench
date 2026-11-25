"""C04: a two-spin model on a hidden cylindrical strip."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from .common import (
    DeterministicStream,
    Factor,
    FactorBlueprint,
    integer_parameter,
    normalized_edge,
    random_nonzero_table,
)

CASE_ID: Final = "c04"
DEFAULT_PARAMETERS: Final[Mapping[str, Any]] = {"rows": 12, "columns": 33}


def build(stream: DeterministicStream, parameters: Mapping[str, Any]) -> FactorBlueprint:
    if set(parameters) != set(DEFAULT_PARAMETERS):
        raise ValueError("c04 parameters must be exactly rows and columns")
    rows = integer_parameter(parameters, "rows", minimum=4, maximum=16)
    columns = integer_parameter(parameters, "columns", minimum=4, maximum=80)
    count = rows * columns
    if count > 400:
        raise ValueError("c04 exceeds the variable envelope")

    def vertex(row: int, column: int) -> int:
        return column * rows + row

    edges: set[tuple[int, int]] = set()
    for column in range(columns):
        for row in range(rows):
            edges.add(normalized_edge(vertex(row, column), vertex((row + 1) % rows, column)))
            if column + 1 < columns:
                edges.add(normalized_edge(vertex(row, column), vertex(row, column + 1)))
    factors = [Factor((variable,), random_nonzero_table(stream, 1)) for variable in range(count)]
    factors.extend(Factor(edge, random_nonzero_table(stream, 2)) for edge in sorted(edges))
    return FactorBlueprint(
        count,
        tuple(factors),
        {"mathematical_family": "cylindrical_two_spin", "rows": rows, "columns": columns},
    )


__all__ = ["CASE_ID", "DEFAULT_PARAMETERS", "build"]
