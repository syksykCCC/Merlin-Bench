"""Scaled C07 with a dense closure-product MLE expansion layer."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from aipbench.tasks.shared.gkr_layered_circuit_cases import c07 as base_c07
from aipbench.tasks.shared.gkr_layered_circuit_cases.common import (
    MODULUS,
    CircuitBlueprint,
    DeterministicStream,
    Gate,
    is_power_of_two,
    random_nonzero_values,
    require_integer,
)

DEFAULT_PARAMETERS: Final[Mapping[str, Any]] = {
    "num_vertices": 16,
    "squarings": 4,
    "expansion_width": 1 << 18,
}

_EXPANDED_FORWARD_LAYER: Final = 0


def build(stream: DeterministicStream, parameters: Mapping[str, Any]) -> CircuitBlueprint:
    num_vertices = require_integer(parameters, "num_vertices", minimum=2, maximum=16)
    squarings = require_integer(parameters, "squarings", minimum=1, maximum=4)
    expansion_width = require_integer(
        parameters,
        "expansion_width",
        minimum=8192,
        maximum=1 << 18,
    )
    if not is_power_of_two(expansion_width):
        raise ValueError("expansion_width must be a power of two")

    base = base_c07.build(
        stream,
        {"num_vertices": num_vertices, "squarings": squarings},
    )
    forward_layers = list(base.forward_layers)
    active = forward_layers[_EXPANDED_FORWARD_LAYER]
    if expansion_width < len(active):
        raise ValueError("expansion_width cannot truncate the active layer")
    child_width = len(base.input_values)
    if not is_power_of_two(child_width):
        raise AssertionError("the expanded layer must have a power-of-two child width")

    alpha, beta, gamma = random_nonzero_values(stream, 3)
    child_mask = child_width - 1
    expanded = list(active)
    for index in range(len(active), expansion_width):
        left = (index ^ (index >> 8) ^ (index >> 16) ^ 0xA7) & child_mask
        right = (37 * index + (index >> 5) + 0x53) & child_mask
        expanded.append(
            Gate(
                (alpha + 0x7FEB352D * index) % MODULUS,
                (beta + 0x846CA68B * index) % MODULUS,
                (gamma + 0x9E3779B9 * index) % MODULUS,
                left,
                right,
            )
        )
    forward_layers[_EXPANDED_FORWARD_LAYER] = tuple(expanded)
    return CircuitBlueprint(
        input_values=base.input_values,
        forward_layers=tuple(forward_layers),
        semantic_output=base.semantic_output,
    )


__all__ = ["DEFAULT_PARAMETERS", "build"]
