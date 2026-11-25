"""Shared primitives used by the current Merlin-Bench tasks."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .common import (
    CircuitBlueprint,
    DeterministicStream,
    mul_gate,
    padded_values,
    random_values,
    require_integer,
    sum_reduction,
)


def build(stream: DeterministicStream, parameters: Mapping[str, Any]) -> CircuitBlueprint:
    length = require_integer(parameters, "vector_length", minimum=2, maximum=256)
    if length & (length - 1):
        raise ValueError("vector_length must be a power of two")
    left = random_values(stream, length)
    right = random_values(stream, length)
    inputs = padded_values(left + right)
    layers = [tuple(mul_gate(index, length + index) for index in range(length))]
    layers.extend(sum_reduction(length))
    output = sum((x * y) % (2**61 - 1) for x, y in zip(left, right, strict=True))
    return CircuitBlueprint(inputs, tuple(layers), output % (2**61 - 1))
