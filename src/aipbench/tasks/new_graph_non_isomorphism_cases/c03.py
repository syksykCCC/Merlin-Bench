"""C03: locally matched Latin-square graphs of two non-isomorphic groups."""

from __future__ import annotations

from collections.abc import Mapping
from math import prod
from typing import Any, Final

from aipbench.tasks.new_graph_non_isomorphism_cases.common import (
    LogicalGraph,
    NewDeterministicStream,
    PairBlueprint,
)
from aipbench.tasks.shared.graph_non_isomorphism_cases.common import normalized_edges

CASE_ID: Final = "c03"
DEFAULT_PARAMETERS: Final[Mapping[str, Any]] = {
    "left_moduli": [16, 2],
    "right_moduli": [8, 4],
}


def _decode(value: int, moduli: tuple[int, ...]) -> tuple[int, ...]:
    coordinates: list[int] = []
    for modulus in reversed(moduli):
        coordinates.append(value % modulus)
        value //= modulus
    return tuple(reversed(coordinates))


def _encode(coordinates: tuple[int, ...], moduli: tuple[int, ...]) -> int:
    value = 0
    for coordinate, modulus in zip(coordinates, moduli, strict=True):
        value = value * modulus + coordinate
    return value


def _add(first: int, second: int, moduli: tuple[int, ...]) -> int:
    left = _decode(first, moduli)
    right = _decode(second, moduli)
    return _encode(
        tuple((a + b) % modulus for a, b, modulus in zip(left, right, moduli, strict=True)),
        moduli,
    )


def _latin_square_graph(moduli: tuple[int, ...]) -> LogicalGraph:
    order = prod(moduli)
    edges: set[tuple[int, int]] = set()
    for row in range(order):
        vertices = [row * order + column for column in range(order)]
        for index, first in enumerate(vertices):
            for second in vertices[index + 1 :]:
                edges.add((first, second))
    for column in range(order):
        vertices = [row * order + column for row in range(order)]
        for index, first in enumerate(vertices):
            for second in vertices[index + 1 :]:
                edges.add((first, second))
    by_symbol: list[list[int]] = [[] for _ in range(order)]
    for row in range(order):
        for column in range(order):
            by_symbol[_add(row, column, moduli)].append(row * order + column)
    for vertices in by_symbol:
        for index, first in enumerate(vertices):
            for second in vertices[index + 1 :]:
                edges.add((min(first, second), max(first, second)))
    return LogicalGraph(order * order, (0,) * (order * order), normalized_edges(edges))


def _moduli(value: object, *, name: str) -> tuple[int, ...]:
    if (
        not isinstance(value, list)
        or not value
        or any(isinstance(item, bool) or not isinstance(item, int) or item < 2 for item in value)
    ):
        raise ValueError(f"{name} must be a nonempty list of moduli >= 2")
    return tuple(value)


def build(stream: NewDeterministicStream, parameters: Mapping[str, Any]) -> PairBlueprint:
    del stream
    if set(parameters) != set(DEFAULT_PARAMETERS):
        raise ValueError("unsupported new GNI c03 parameters")
    left = _moduli(parameters["left_moduli"], name="left_moduli")
    right = _moduli(parameters["right_moduli"], name="right_moduli")
    if prod(left) != prod(right) or prod(left) > 48:
        raise ValueError("c03 groups must have equal order at most 48")
    return PairBlueprint(
        _latin_square_graph(left),
        _latin_square_graph(right),
        {
            "construction": "matched_abelian_group_latin_square_graphs",
            "group_order": prod(left),
            "left_moduli": list(left),
            "right_moduli": list(right),
        },
    )


__all__ = ["CASE_ID", "DEFAULT_PARAMETERS", "build"]
