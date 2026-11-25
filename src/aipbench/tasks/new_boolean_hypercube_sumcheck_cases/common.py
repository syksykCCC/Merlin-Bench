"""Generators for the 600-second Boolean-hypercube Sum-Check task."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final

from aipbench.tasks.shared.boolean_hypercube_sumcheck_cases.common import (
    CaseDefinition,
    Factor,
    FactorBlueprint,
    FactorModel,
    FinalizedCase,
    integer_parameter,
    parse_public_instance,
    serialize_model,
)
from aipbench.tasks.shared.boolean_hypercube_sumcheck_cases.common import (
    DeterministicStream as BaseDeterministicStream,
)


class DeterministicStream(BaseDeterministicStream):
    """Task-separated deterministic stream."""

    _DOMAIN: Final = b"aipbench/new-boolean-hypercube-sumcheck/generator/v1\x00"


def normalized_edge(first: int, second: int) -> tuple[int, int]:
    if first == second:
        raise ValueError("self-loops are not allowed")
    return (min(first, second), max(first, second))


def two_cycle_edges(stream: DeterministicStream, count: int) -> tuple[tuple[int, int], ...]:
    """Return two edge-disjoint Hamilton cycles on one vertex set."""

    first = {normalized_edge(vertex, (vertex + 1) % count) for vertex in range(count)}
    for _ in range(128):
        order = list(range(count))
        stream.shuffle(order)
        second = {
            normalized_edge(order[index], order[(index + 1) % count]) for index in range(count)
        }
        if len(second) == count and first.isdisjoint(second):
            return tuple(sorted(first | second))
    raise ValueError("failed to construct edge-disjoint Hamilton cycles")


def rank_one_table(stream: DeterministicStream) -> tuple[int, ...]:
    left = (1 + stream.randbelow(7), 1 + stream.randbelow(7))
    right = (1 + stream.randbelow(7), 1 + stream.randbelow(7))
    return (
        left[0] * right[0],
        left[1] * right[0],
        left[0] * right[1],
        left[1] * right[1],
    )


def signed_table(stream: DeterministicStream, *, disequality: bool) -> tuple[int, ...]:
    first = 1 + stream.randbelow(7)
    second = 1 + stream.randbelow(7)
    return (0, first, second, 0) if disequality else (first, 0, 0, second)


def random_nonzero_table(stream: DeterministicStream, arity: int) -> tuple[int, ...]:
    return tuple(1 + stream.randbelow(3) for _ in range(1 << arity))


def _remap_factor(
    factor: Factor,
    *,
    variable_permutation: Sequence[int],
    gauge: Sequence[int],
    stream: DeterministicStream,
) -> Factor:
    axis_order = list(range(len(factor.scope)))
    stream.shuffle(axis_order)
    new_scope = tuple(variable_permutation[factor.scope[old_axis]] for old_axis in axis_order)
    reordered: list[int] = []
    for new_index in range(1 << len(new_scope)):
        old_index = 0
        for new_axis, old_axis in enumerate(axis_order):
            old_index |= ((new_index >> new_axis) & 1) << old_axis
        reordered.append(factor.values[old_index])
    gauged: list[int] = []
    for public_index in range(1 << len(new_scope)):
        source_index = 0
        for axis, variable in enumerate(new_scope):
            source_index |= (((public_index >> axis) & 1) ^ gauge[variable]) << axis
        gauged.append(reordered[source_index])
    return Factor(new_scope, tuple(gauged))


def finalize_blueprint(
    *, case_id: str, blueprint: FactorBlueprint, stream: DeterministicStream
) -> FinalizedCase:
    """Hide labels and axes without attempting generic high-treewidth elimination."""

    logical = FactorModel(blueprint.num_variables, blueprint.factors)
    serialize_model(logical)  # strict validation
    permutation = list(range(logical.num_variables))
    stream.shuffle(permutation)
    gauge = [stream.randbelow(2) for _ in range(logical.num_variables)]
    factors = [
        _remap_factor(
            factor,
            variable_permutation=permutation,
            gauge=gauge,
            stream=stream,
        )
        for factor in logical.factors
    ]
    stream.shuffle(factors)
    hidden = FactorModel(logical.num_variables, tuple(factors))
    public_instance = serialize_model(hidden)
    parse_public_instance(public_instance)
    return FinalizedCase(
        public_instance=public_instance,
        private_instance={},
        generation_metadata={
            "generator": f"new_boolean_hypercube_sumcheck/{case_id}/v1",
            "case_id": case_id,
            "num_variables": hidden.num_variables,
            "num_factors": len(hidden.factors),
            "profile": "600-second-calibration",
            **dict(blueprint.metadata),
        },
    )


__all__ = [
    "CaseDefinition",
    "DeterministicStream",
    "Factor",
    "FactorBlueprint",
    "FinalizedCase",
    "finalize_blueprint",
    "integer_parameter",
    "normalized_edge",
    "random_nonzero_table",
    "rank_one_table",
    "signed_table",
    "two_cycle_edges",
]
