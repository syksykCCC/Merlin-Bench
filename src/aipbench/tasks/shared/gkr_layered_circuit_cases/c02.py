"""Shared primitives used by the current Merlin-Bench tasks."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

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

RAILS: Final = 6


def build(stream: DeterministicStream, parameters: Mapping[str, Any]) -> CircuitBlueprint:
    batch = require_integer(parameters, "batch_size", minimum=1, maximum=16)
    time_steps = require_integer(parameters, "time_steps", minimum=2, maximum=16)
    data = random_values(stream, batch * RAILS)
    # Per batch: alpha, beta, gamma, u_0, u_1, eta.
    inputs = padded_values(data)
    child_width = len(inputs)
    layers: list[tuple[Any, ...]] = []
    for _ in range(time_steps - 2):
        products = [copy_gate(index) for index in range(batch * RAILS)]
        for item in range(batch):
            base = item * RAILS
            products.extend([mul_gate(base, base + 4), mul_gate(base + 1, base + 3)])
        stage = padded_stage(products, child_width)
        layers.append(stage)
        product_base = batch * RAILS

        partial: list[Any] = []
        for item in range(batch):
            base = item * RAILS
            partial.extend(
                [
                    copy_gate(base),
                    copy_gate(base + 1),
                    copy_gate(base + 2),
                    copy_gate(base + 4),
                    add_gate(product_base + 2 * item, product_base + 2 * item + 1),
                    copy_gate(base + 5),
                ]
            )
        stage = padded_stage(partial, len(stage))
        layers.append(stage)

        complete: list[Any] = []
        for item in range(batch):
            base = item * RAILS
            complete.extend(
                [
                    copy_gate(base),
                    copy_gate(base + 1),
                    copy_gate(base + 2),
                    copy_gate(base + 3),
                    add_gate(base + 4, base + 2),
                    copy_gate(base + 5),
                ]
            )
        stage = padded_stage(complete, len(stage))
        layers.append(stage)
        child_width = len(stage)

    weighted = [mul_gate(item * RAILS + 4, item * RAILS + 5) for item in range(batch)]
    stage = padded_stage(weighted, child_width)
    layers.append(stage)
    layers.extend(sum_reduction(len(stage)))

    result = 0
    for item in range(batch):
        alpha, beta, gamma, previous, current, eta = data[item * RAILS : (item + 1) * RAILS]
        for _ in range(time_steps - 2):
            previous, current = current, (alpha * current + beta * previous + gamma) % MODULUS
        result = (result + eta * current) % MODULUS
    return CircuitBlueprint(inputs, tuple(layers), result)
