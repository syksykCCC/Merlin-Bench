"""Scaled C05 with one dense, semantically inert GKR expansion layer."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from aipbench.tasks.shared.gkr_layered_circuit_cases import c05 as base_c05
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
    "records": 8,
    "payload_fields": 4,
    "expansion_width": 1 << 19,
}

_EXPANDED_FORWARD_LAYER: Final = 2


def build(stream: DeterministicStream, parameters: Mapping[str, Any]) -> CircuitBlueprint:
    records = require_integer(parameters, "records", minimum=2, maximum=16)
    payload_fields = require_integer(parameters, "payload_fields", minimum=1, maximum=8)
    expansion_width = require_integer(
        parameters,
        "expansion_width",
        minimum=256,
        maximum=1 << 19,
    )
    if not is_power_of_two(expansion_width):
        raise ValueError("expansion_width must be a power of two")

    base = base_c05.build(
        stream,
        {"records": records, "payload_fields": payload_fields},
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
        left = index & child_mask
        right = ((index >> 6) ^ (17 * index) ^ 0x2D) & child_mask
        expanded.append(
            Gate(
                (alpha + 0x9E3779B1 * index) % MODULUS,
                (beta + 0x85EBCA77 * index) % MODULUS,
                (gamma + 0xC2B2AE3D * index) % MODULUS,
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
