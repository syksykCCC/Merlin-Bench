"""Shared primitives used by the current Merlin-Bench tasks."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .common import (
    MODULUS,
    CircuitBlueprint,
    DeterministicStream,
    mul_gate,
    or_gate,
    padded_stage,
    padded_values,
    require_integer,
    sum_reduction,
)


def build(stream: DeterministicStream, parameters: Mapping[str, Any]) -> CircuitBlueprint:
    vertices = require_integer(parameters, "num_vertices", minimum=2, maximum=16)
    squarings = require_integer(parameters, "squarings", minimum=1, maximum=4)
    if vertices & (vertices - 1):
        raise ValueError("num_vertices must be a power of two")
    if 1 << squarings < vertices:
        raise ValueError("squarings must cover every simple path length")
    relation = [
        1 if row == column or stream.integer(4) == 0 else 0
        for row in range(vertices)
        for column in range(vertices)
    ]
    inputs = padded_values(relation)
    layers: list[tuple[Any, ...]] = []
    child_width = len(inputs)
    for _ in range(squarings):
        products = []
        for row in range(vertices):
            for column in range(vertices):
                for middle in range(vertices):
                    products.append(mul_gate(row * vertices + middle, middle * vertices + column))
        stage = padded_stage(products, child_width)
        layers.append(stage)
        group = vertices
        while group > 1:
            gates = []
            active_count = vertices * vertices * group
            for base in range(0, active_count, group):
                for offset in range(0, group, 2):
                    gates.append(or_gate(base + offset, base + offset + 1))
            stage = padded_stage(gates, len(stage))
            layers.append(stage)
            group //= 2
        child_width = len(stage)
    layers.extend(sum_reduction(child_width))

    current = relation
    for _ in range(squarings):
        next_relation = []
        for row in range(vertices):
            for column in range(vertices):
                next_relation.append(
                    int(
                        any(
                            current[row * vertices + middle] and current[middle * vertices + column]
                            for middle in range(vertices)
                        )
                    )
                )
        current = next_relation
    return CircuitBlueprint(inputs, tuple(layers), sum(current) % MODULUS)
