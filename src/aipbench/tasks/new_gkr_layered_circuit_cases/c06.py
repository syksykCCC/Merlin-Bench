"""Scaled C06 with a dense periodic-state MLE expansion layer."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from aipbench.tasks.shared.gkr_layered_circuit_cases import c06 as base_c06
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
    "ring_length": 256,
    "time_steps": 4,
    "expansion_width": 1 << 19,
}

_EXPANDED_FORWARD_LAYER: Final = 1


def build(stream: DeterministicStream, parameters: Mapping[str, Any]) -> CircuitBlueprint:
    ring_length = require_integer(parameters, "ring_length", minimum=4, maximum=256)
    time_steps = require_integer(parameters, "time_steps", minimum=1, maximum=8)
    expansion_width = require_integer(
        parameters,
        "expansion_width",
        minimum=2048,
        maximum=1 << 19,
    )
    if not is_power_of_two(expansion_width):
        raise ValueError("expansion_width must be a power of two")

    base = base_c06.build(
        stream,
        {"ring_length": ring_length, "time_steps": time_steps},
    )
    forward_layers = list(base.forward_layers)
    active = forward_layers[_EXPANDED_FORWARD_LAYER]
    if expansion_width < len(active):
        raise ValueError("expansion_width cannot truncate the active layer")
    child_width = len(forward_layers[_EXPANDED_FORWARD_LAYER - 1])
    if not is_power_of_two(child_width):
        raise AssertionError("the expanded layer must have a power-of-two child width")

    alpha, beta, gamma = random_nonzero_values(stream, 3)
    child_mask = child_width - 1
    expanded = list(active)
    for index in range(len(active), expansion_width):
        left = (index ^ (index >> 9) ^ 0x151) & child_mask
        right = (29 * index + (index >> 4) + 0x6D) & child_mask
        expanded.append(
            Gate(
                (alpha + 0x27D4EB2D * index) % MODULUS,
                (beta + 0x165667B1 * index) % MODULUS,
                (gamma + 0xD3A2646C * index) % MODULUS,
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
