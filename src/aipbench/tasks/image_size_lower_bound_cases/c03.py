"""C03: Hamming ball obtained by truncating to the first r set bits."""

from __future__ import annotations

from collections.abc import Mapping
from math import comb
from typing import Any, Final

from aipbench.tasks.image_size_lower_bound_cases.common import (
    CircuitBlueprint,
    CircuitBuilder,
    DeterministicStream,
    hide_outputs,
    integer_parameter,
    make_blueprint,
)

CASE_ID: Final = "c03"
DEFAULT_PARAMETERS: Final[Mapping[str, Any]] = {"dimension": 12, "radius": 3}


def build(stream: DeterministicStream, parameters: Mapping[str, Any]) -> CircuitBlueprint:
    if set(parameters) != set(DEFAULT_PARAMETERS):
        raise ValueError("c03 parameters must be exactly dimension and radius")
    dimension = integer_parameter(parameters, "dimension", minimum=4, maximum=16)
    radius = integer_parameter(parameters, "radius", minimum=1, maximum=dimension)
    builder = CircuitBuilder(dimension)
    order = list(range(dimension))
    stream.shuffle(order)
    at_least = [builder.const(0) for _ in range(radius)]
    kept_by_input = [builder.const(0)] * dimension
    for input_wire in order:
        kept_by_input[input_wire] = builder.and_(input_wire, builder.not_(at_least[-1]))
        previous = list(at_least)
        for threshold in range(radius, 0, -1):
            added = (
                input_wire if threshold == 1 else builder.and_(previous[threshold - 2], input_wire)
            )
            at_least[threshold - 1] = builder.or_(previous[threshold - 1], added)
    outputs = hide_outputs(builder, kept_by_input, stream)
    image_size = sum(comb(dimension, weight) for weight in range(radius + 1))
    return make_blueprint(
        builder=builder,
        outputs=outputs,
        image_size=image_size,
        metadata={
            "mathematical_family": "truncated_hamming_ball",
            "dimension": dimension,
            "radius": radius,
        },
    )


__all__ = ["CASE_ID", "DEFAULT_PARAMETERS", "build"]
