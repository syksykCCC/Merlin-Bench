"""C05: binary rank-one matrix variety."""

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

CASE_ID: Final = "c05"
DEFAULT_PARAMETERS: Final[Mapping[str, Any]] = {"left_dimension": 4, "right_dimension": 5}


def build(stream: DeterministicStream, parameters: Mapping[str, Any]) -> CircuitBlueprint:
    if set(parameters) != set(DEFAULT_PARAMETERS):
        raise ValueError("c05 parameters must be exactly left_dimension and right_dimension")
    left_dimension = integer_parameter(parameters, "left_dimension", minimum=2, maximum=8)
    right_dimension = integer_parameter(parameters, "right_dimension", minimum=2, maximum=8)
    if left_dimension + right_dimension > 16:
        raise ValueError("c05 exceeds the task-wide input envelope")
    builder = CircuitBuilder(left_dimension + right_dimension)
    inputs = list(range(builder.num_inputs))
    stream.shuffle(inputs)
    left = inputs[:left_dimension]
    right = inputs[left_dimension:]
    logical = [builder.and_(first, second) for first in left for second in right]
    outputs = hide_outputs(builder, logical, stream)
    image_size = 1 + ((1 << left_dimension) - 1) * ((1 << right_dimension) - 1)
    return make_blueprint(
        builder=builder,
        outputs=outputs,
        image_size=image_size,
        metadata={
            "mathematical_family": "binary_rank_one_matrices",
            "left_dimension": left_dimension,
            "right_dimension": right_dimension,
        },
    )


__all__ = ["CASE_ID", "DEFAULT_PARAMETERS", "build"]
