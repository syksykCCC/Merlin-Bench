"""C01: FIFO occupancy encoding never leaves its legal prefix states."""

from collections.abc import Mapping

from aipbench.tasks.drat_bounded_hardware_cases.common import (
    DeterministicStream,
    HardwareBlueprint,
    build_fifo_prefix,
    finish_blueprint,
)


def build(stream: DeterministicStream, parameters: Mapping[str, int]) -> HardwareBlueprint:
    if parameters:
        raise ValueError("c01 accepts no parameters")
    # Keep the entry case nontrivial but leave enough time for a model that
    # derives and checks its own DRUP invariant to upload before 600 seconds.
    depth, horizon = 4 + stream.randbelow(2), 20 + stream.randbelow(4)
    return finish_blueprint(
        title="FIFO occupancy safety",
        builder=build_fifo_prefix(depth, horizon),
        horizon=horizon,
        features={"component": "fifo", "depth": depth, "horizon": horizon},
    )
