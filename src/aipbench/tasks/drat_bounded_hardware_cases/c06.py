"""C06: a router never forwards without an available credit."""

from collections.abc import Mapping

from aipbench.tasks.drat_bounded_hardware_cases.common import (
    DeterministicStream,
    HardwareBlueprint,
    build_credit_forwarding,
    finish_blueprint,
)


def build(stream: DeterministicStream, parameters: Mapping[str, int]) -> HardwareBlueprint:
    if parameters:
        raise ValueError("c06 accepts no parameters")
    capacity, horizon = 12 + stream.randbelow(3), 36 + stream.randbelow(5)
    return finish_blueprint(
        title="Credit-router forwarding safety",
        builder=build_credit_forwarding(capacity, horizon),
        horizon=horizon,
        features={"component": "credit_router", "capacity": capacity, "horizon": horizon},
    )
