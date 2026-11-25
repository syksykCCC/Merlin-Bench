"""C04: separable nonlinear product of two-bit gamma blocks."""

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

CASE_ID: Final = "c04"
DEFAULT_PARAMETERS: Final[Mapping[str, Any]] = {"num_blocks": 6, "num_outputs": 24}


def build(stream: DeterministicStream, parameters: Mapping[str, Any]) -> CircuitBlueprint:
    if set(parameters) != set(DEFAULT_PARAMETERS):
        raise ValueError("c04 parameters must be exactly num_blocks and num_outputs")
    blocks = integer_parameter(parameters, "num_blocks", minimum=2, maximum=8)
    num_outputs = integer_parameter(parameters, "num_outputs", minimum=3 * blocks, maximum=64)
    builder = CircuitBuilder(2 * blocks)
    inputs = list(range(2 * blocks))
    stream.shuffle(inputs)
    logical: list[int] = []
    for block in range(blocks):
        first, second = inputs[2 * block : 2 * block + 2]
        logical.extend((first, second, builder.and_(first, second)))
    logical.extend([builder.const(0)] * (num_outputs - len(logical)))
    outputs = hide_outputs(builder, logical, stream)
    return make_blueprint(
        builder=builder,
        outputs=outputs,
        image_size=1 << (2 * blocks),
        metadata={"mathematical_family": "separable_nonlinear_product", "num_blocks": blocks},
    )


__all__ = ["CASE_ID", "DEFAULT_PARAMETERS", "build"]
