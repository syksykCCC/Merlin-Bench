"""C01: systematic affine subcube."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from aipbench.tasks.image_size_lower_bound_cases.common import (
    CircuitBlueprint,
    CircuitBuilder,
    DeterministicStream,
    hide_outputs,
    integer_parameter,
    make_blueprint,
)

CASE_ID: Final = "c01"
DEFAULT_PARAMETERS: Final[Mapping[str, Any]] = {"dimension": 8, "num_inputs": 10, "num_outputs": 12}


def build(stream: DeterministicStream, parameters: Mapping[str, Any]) -> CircuitBlueprint:
    if set(parameters) != set(DEFAULT_PARAMETERS):
        raise ValueError("c01 parameters must be exactly dimension, num_inputs, num_outputs")
    dimension = integer_parameter(parameters, "dimension", minimum=4, maximum=16)
    num_inputs = integer_parameter(parameters, "num_inputs", minimum=dimension, maximum=16)
    num_outputs = integer_parameter(parameters, "num_outputs", minimum=dimension, maximum=64)
    builder = CircuitBuilder(num_inputs)
    inputs = list(range(num_inputs))
    stream.shuffle(inputs)
    logical = inputs[:dimension] + [builder.const(0)] * (num_outputs - dimension)
    outputs = hide_outputs(builder, logical, stream)
    return make_blueprint(
        builder=builder,
        outputs=outputs,
        image_size=1 << dimension,
        metadata={"mathematical_family": "systematic_affine_subcube", "dimension": dimension},
    )


__all__ = ["CASE_ID", "DEFAULT_PARAMETERS", "build"]
