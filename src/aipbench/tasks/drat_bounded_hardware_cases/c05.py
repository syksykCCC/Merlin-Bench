"""C05: credits and in-flight flits remain conserved."""

from collections.abc import Mapping

from aipbench.tasks.drat_bounded_hardware_cases.common import (
    DeterministicStream,
    HardwareBlueprint,
    build_credit_conservation,
    finish_blueprint,
)


def build(stream: DeterministicStream, parameters: Mapping[str, int]) -> HardwareBlueprint:
    if parameters:
        raise ValueError("c05 accepts no parameters")
    capacity, horizon = 6 + stream.randbelow(2), 22 + stream.randbelow(3)
    return finish_blueprint(
        title="Credit-router conservation",
        builder=build_credit_conservation(capacity, horizon),
        horizon=horizon,
        features={"component": "credit_router", "capacity": capacity, "horizon": horizon},
    )
