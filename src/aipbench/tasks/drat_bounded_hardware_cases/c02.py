"""C02: FIFO controller never acknowledges an underflowing pop."""

from collections.abc import Mapping

from aipbench.tasks.drat_bounded_hardware_cases.common import (
    DeterministicStream,
    HardwareBlueprint,
    build_fifo_underflow,
    finish_blueprint,
)


def build(stream: DeterministicStream, parameters: Mapping[str, int]) -> HardwareBlueprint:
    if parameters:
        raise ValueError("c02 accepts no parameters")
    depth, horizon = 10 + stream.randbelow(3), 28 + stream.randbelow(5)
    return finish_blueprint(
        title="FIFO underflow safety",
        builder=build_fifo_underflow(depth, horizon),
        horizon=horizon,
        features={"component": "fifo", "depth": depth, "horizon": horizon},
    )
