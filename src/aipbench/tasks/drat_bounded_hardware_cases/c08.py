"""C08: writeback tags match their independently tracked shadow tags."""

from collections.abc import Mapping

from aipbench.tasks.drat_bounded_hardware_cases.common import (
    DeterministicStream,
    HardwareBlueprint,
    build_pipeline_writeback,
    finish_blueprint,
)


def build(stream: DeterministicStream, parameters: Mapping[str, int]) -> HardwareBlueprint:
    if parameters:
        raise ValueError("c08 accepts no parameters")
    stages, horizon = 14 + stream.randbelow(3), 44 + stream.randbelow(5)
    return finish_blueprint(
        title="Pipeline writeback consistency",
        builder=build_pipeline_writeback(stages, horizon),
        horizon=horizon,
        features={"component": "pipeline", "stages": stages, "horizon": horizon},
    )
