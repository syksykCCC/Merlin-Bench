"""C07: a flush clears every valid pipeline stage despite stalls."""

from collections.abc import Mapping

from aipbench.tasks.drat_bounded_hardware_cases.common import (
    DeterministicStream,
    HardwareBlueprint,
    build_pipeline_flush,
    finish_blueprint,
)


def build(stream: DeterministicStream, parameters: Mapping[str, int]) -> HardwareBlueprint:
    if parameters:
        raise ValueError("c07 accepts no parameters")
    stages, horizon = 9 + stream.randbelow(3), 30 + stream.randbelow(5)
    return finish_blueprint(
        title="Pipeline flush-stall safety",
        builder=build_pipeline_flush(stages, horizon),
        horizon=horizon,
        features={"component": "pipeline", "stages": stages, "horizon": horizon},
    )
