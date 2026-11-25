"""C07: a memory-ten tail-biting convolutional-code enumerator."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from aipbench.tasks.field61 import MODULUS

from .common import DeterministicStream, Factor, FactorBlueprint, integer_parameter

CASE_ID: Final = "c07"
DEFAULT_PARAMETERS: Final[Mapping[str, Any]] = {"length": 160}


def build(stream: DeterministicStream, parameters: Mapping[str, Any]) -> FactorBlueprint:
    if set(parameters) != set(DEFAULT_PARAMETERS):
        raise ValueError("c07 parameters must be exactly length")
    length = integer_parameter(parameters, "length", minimum=16, maximum=200)
    if 2 * length > 400:
        raise ValueError("c07 exceeds the variable envelope")
    factors: list[Factor] = []
    for time in range(length):
        output = length + time
        scope = (output, time, (time - 3) % length, (time - 10) % length)
        values = []
        for assignment in range(16):
            bits = [(assignment >> axis) & 1 for axis in range(4)]
            values.append(int(bits[0] == (bits[1] ^ bits[2] ^ bits[3])))
        factors.append(Factor(scope, tuple(values)))
        factors.append(Factor((output,), (1, 2 + stream.randbelow(5))))
    for time in range(length):
        lam = 2 + stream.randbelow(5)
        factors.append(
            Factor(
                (time, (time + 1) % length),
                (1, lam, lam, lam * lam % MODULUS),
            )
        )
    return FactorBlueprint(
        2 * length,
        tuple(factors),
        {"mathematical_family": "tail_biting_memory_10", "logical_length": length},
    )


__all__ = ["CASE_ID", "DEFAULT_PARAMETERS", "build"]
