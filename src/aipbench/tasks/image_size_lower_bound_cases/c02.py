"""C02: hidden dense affine image of certified rank."""

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

CASE_ID: Final = "c02"
DEFAULT_PARAMETERS: Final[Mapping[str, Any]] = {"rank": 8, "num_inputs": 12, "num_outputs": 14}


def build(stream: DeterministicStream, parameters: Mapping[str, Any]) -> CircuitBlueprint:
    if set(parameters) != set(DEFAULT_PARAMETERS):
        raise ValueError("c02 parameters must be exactly rank, num_inputs, num_outputs")
    rank = integer_parameter(parameters, "rank", minimum=4, maximum=16)
    num_inputs = integer_parameter(parameters, "num_inputs", minimum=rank, maximum=16)
    num_outputs = integer_parameter(parameters, "num_outputs", minimum=rank, maximum=64)
    builder = CircuitBuilder(num_inputs)
    inputs = list(range(num_inputs))
    stream.shuffle(inputs)
    active = inputs[:rank]
    rows: list[list[int]] = [[active[index]] for index in range(rank)]
    for _ in range(num_outputs - rank):
        support = [wire for wire in active if stream.bit()]
        if len(support) < 2:
            support = [active[stream.randbelow(rank)], active[stream.randbelow(rank)]]
        rows.append(support)
    logical = [builder.xor_many(row) for row in rows]
    outputs = hide_outputs(builder, logical, stream)
    return make_blueprint(
        builder=builder,
        outputs=outputs,
        image_size=1 << rank,
        metadata={"mathematical_family": "hidden_dense_affine_image", "rank": rank},
    )


__all__ = ["CASE_ID", "DEFAULT_PARAMETERS", "build"]
