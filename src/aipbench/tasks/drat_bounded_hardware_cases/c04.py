"""C04: a continuously requesting client receives a bounded grant."""

from collections.abc import Mapping

from aipbench.tasks.drat_bounded_hardware_cases.common import (
    DeterministicStream,
    HardwareBlueprint,
    build_arbiter_fairness,
    finish_blueprint,
)


def build(stream: DeterministicStream, parameters: Mapping[str, int]) -> HardwareBlueprint:
    if parameters:
        raise ValueError("c04 accepts no parameters")
    agents, horizon = 7 + stream.randbelow(2), 22 + stream.randbelow(3)
    return finish_blueprint(
        title="Round-robin bounded fairness",
        builder=build_arbiter_fairness(agents, horizon),
        horizon=horizon,
        features={"component": "arbiter", "agents": agents, "horizon": horizon},
    )
