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
    random_nonzero_values,
    require_integer,
    sub_gate,
    sum_reduction,
)


def _rule110(left: int, center: int, right: int) -> int:
    return (center + right - center * right - left * center * right) % MODULUS


def build(stream: DeterministicStream, parameters: Mapping[str, Any]) -> CircuitBlueprint:
    length = require_integer(parameters, "ring_length", minimum=2, maximum=256)
    time_steps = require_integer(parameters, "time_steps", minimum=1, maximum=16)
    if length & (length - 1):
        raise ValueError("ring_length must be a power of two")
    initial = [stream.integer(2) for _ in range(length)]
    inputs = padded_values(initial)
    layers: list[tuple[Any, ...]] = []
    child_width = len(inputs)
    for _ in range(time_steps):
        stage = padded_stage(
            [copy_gate(index) for index in range(length)]
            + [mul_gate(index, (index + 1) % length) for index in range(length)],
            child_width,
        )
        layers.append(stage)
        cr_base = length
        stage = padded_stage(
            [add_gate(index, (index + 1) % length) for index in range(length)]
            + [copy_gate(cr_base + index) for index in range(length)]
            + [mul_gate((index - 1) % length, cr_base + index) for index in range(length)],
            len(stage),
        )
        layers.append(stage)
        lcr_base = 2 * length
        stage = padded_stage(
            [sub_gate(index, length + index) for index in range(length)]
            + [copy_gate(lcr_base + index) for index in range(length)],
            len(stage),
        )
        layers.append(stage)
        stage = padded_stage(
            [sub_gate(index, length + index) for index in range(length)], len(stage)
        )
        layers.append(stage)
        child_width = len(stage)

    weights = random_nonzero_values(stream, length)
    stage = padded_stage([copy_gate(index, weights[index]) for index in range(length)], child_width)
    layers.append(stage)
    layers.extend(sum_reduction(len(stage)))

    state = initial
    for _ in range(time_steps):
        state = [
            _rule110(state[(index - 1) % length], state[index], state[(index + 1) % length])
            for index in range(length)
        ]
    result = sum(value * weight for value, weight in zip(state, weights, strict=True))
    return CircuitBlueprint(inputs, tuple(layers), result % MODULUS)
