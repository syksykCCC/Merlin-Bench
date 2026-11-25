"""Shared primitives used by the current Merlin-Bench tasks."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .common import (
    MODULUS,
    CircuitBlueprint,
    DeterministicStream,
    add_gate,
    copy_gate,
    mul_gate,
    padded_stage,
    padded_values,
    random_values,
    require_integer,
    sum_reduction,
)


def build(stream: DeterministicStream, parameters: Mapping[str, Any]) -> CircuitBlueprint:
    batch = require_integer(parameters, "batch_size", minimum=1, maximum=4)
    order = require_integer(parameters, "matrix_order", minimum=2, maximum=8)
    if order & (order - 1):
        raise ValueError("matrix_order must be a power of two")
    cells = batch * order * order
    data = random_values(stream, 3 * cells)
    inputs = padded_values(data)

    def pos(matrix: int, item: int, row: int, column: int) -> int:
        return matrix * cells + item * order * order + row * order + column

    products = []
    for item in range(batch):
        for row in range(order):
            for column in range(order):
                for middle in range(order):
                    products.append(
                        mul_gate(
                            pos(0, item, row, middle),
                            pos(1, item, middle, column),
                        )
                    )
    products.extend(
        copy_gate(pos(2, item, row, column))
        for item in range(batch)
        for row in range(order)
        for column in range(order)
    )
    layers = [padded_stage(products, len(inputs))]
    output_cells = batch * order * order
    group = order
    while group > 1:
        previous_count = output_cells * group
        stage = []
        for base in range(0, previous_count, group):
            for offset in range(0, group, 2):
                stage.append(add_gate(base + offset, base + offset + 1))
        stage.extend(copy_gate(previous_count + index) for index in range(cells))
        layers.append(padded_stage(stage, len(layers[-1])))
        group //= 2

    triple = []
    for item in range(batch):
        for row in range(order):
            for column in range(order):
                reduced = item * order * order + row * order + column
                c_position = output_cells + item * order * order + column * order + row
                triple.append(mul_gate(reduced, c_position))
    layers.append(padded_stage(triple, len(layers[-1])))
    layers.extend(sum_reduction(len(layers[-1])))

    result = 0
    for item in range(batch):
        for row in range(order):
            for column in range(order):
                product_sum = (
                    sum(
                        data[pos(0, item, row, middle)] * data[pos(1, item, middle, column)]
                        for middle in range(order)
                    )
                    % MODULUS
                )
                result = (result + product_sum * data[pos(2, item, column, row)]) % MODULUS
    return CircuitBlueprint(inputs, tuple(layers), result)
