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
    sub_gate,
    sum_reduction,
)


def _fwht_stage(offset: int, length: int, bit: int) -> list[Any]:
    gates: list[Any] = [None] * length
    for index in range(length):
        if index & bit:
            continue
        other = index | bit
        gates[index] = add_gate(offset + index, offset + other)
        gates[other] = sub_gate(offset + index, offset + other)
    return gates


def build(stream: DeterministicStream, parameters: Mapping[str, Any]) -> CircuitBlueprint:
    length = require_integer(parameters, "vector_length", minimum=2, maximum=256)
    if length & (length - 1):
        raise ValueError("vector_length must be a power of two")
    left = random_values(stream, length)
    right = random_values(stream, length)
    digest = random_values(stream, length)
    inputs = padded_values(left + right + digest)
    layers: list[tuple[Any, ...]] = []
    child_width = len(inputs)
    bit = 1
    while bit < length:
        gates = _fwht_stage(0, length, bit)
        gates.extend(_fwht_stage(length, length, bit))
        gates.extend(copy_gate(2 * length + index) for index in range(length))
        stage = padded_stage(gates, child_width)
        layers.append(stage)
        child_width = len(stage)
        bit <<= 1

    pointwise = [mul_gate(index, length + index) for index in range(length)]
    pointwise.extend(copy_gate(2 * length + index) for index in range(length))
    stage = padded_stage(pointwise, child_width)
    layers.append(stage)
    child_width = len(stage)

    bit = 1
    while bit < length:
        gates = _fwht_stage(0, length, bit)
        gates.extend(copy_gate(length + index) for index in range(length))
        stage = padded_stage(gates, child_width)
        layers.append(stage)
        child_width = len(stage)
        bit <<= 1

    inverse = pow(length, MODULUS - 2, MODULUS)
    scaled = [copy_gate(index, inverse) for index in range(length)]
    scaled.extend(copy_gate(length + index) for index in range(length))
    stage = padded_stage(scaled, child_width)
    layers.append(stage)
    multiplied = [mul_gate(index, length + index) for index in range(length)]
    stage = padded_stage(multiplied, len(stage))
    layers.append(stage)
    layers.extend(sum_reduction(len(stage)))

    result = 0
    for z in range(length):
        convolution = sum(left[x] * right[x ^ z] for x in range(length)) % MODULUS
        result = (result + convolution * digest[z]) % MODULUS
    return CircuitBlueprint(inputs, tuple(layers), result)
