"""C03: round-robin grants are mutually exclusive."""

from collections.abc import Mapping

from aipbench.tasks.drat_bounded_hardware_cases.common import (
    DeterministicStream,
    HardwareBlueprint,
    build_arbiter_mutex,
    finish_blueprint,
)


def build(stream: DeterministicStream, parameters: Mapping[str, int]) -> HardwareBlueprint:
    if parameters:
        raise ValueError("c03 accepts no parameters")
    agents, horizon = 6 + stream.randbelow(2), 20 + stream.randbelow(3)
    return finish_blueprint(
        title="Round-robin mutual exclusion",
        builder=build_arbiter_mutex(agents, horizon),
        horizon=horizon,
        features={"component": "arbiter", "agents": agents, "horizon": horizon},
    )
