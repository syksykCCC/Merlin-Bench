"""C06: hidden clique-path Ising objective with exact transfer DP."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from aipbench.tasks.new_maxsat_cases.common import (
    CaseBlueprint,
    NewMaxSatStream,
    SoftClause,
    integer_parameter,
)
from aipbench.tasks.new_maxsat_cases.reference import IsingFactor, solve_layered_ising

CASE_ID: Final = "c06"
DEFAULT_PARAMETERS: Final[Mapping[str, Any]] = {
    "num_layers": 240,
    "layer_width": 16,
    "min_weight": 1,
    "max_weight": 4093,
}


def _soft_factor(
    left: int, right: int, preferred_parity: bool, weight: int
) -> tuple[SoftClause, SoftClause]:
    if preferred_parity:
        return SoftClause((left, right), weight), SoftClause((-left, -right), weight)
    return SoftClause((-left, right), weight), SoftClause((left, -right), weight)


def build(stream: NewMaxSatStream, parameters: Mapping[str, Any]) -> CaseBlueprint:
    num_layers = integer_parameter(parameters, "num_layers", minimum=2)
    layer_width = integer_parameter(parameters, "layer_width", minimum=2)
    min_weight = integer_parameter(parameters, "min_weight", minimum=1)
    max_weight = integer_parameter(parameters, "max_weight", minimum=1)
    if layer_width > 16:
        raise ValueError("layer width exceeds exact transfer reference")
    if max_weight < min_weight:
        raise ValueError("invalid weight interval")

    within_layers: list[list[IsingFactor]] = []
    for _layer in range(num_layers):
        factors: list[IsingFactor] = []
        for left in range(layer_width):
            for right in range(left + 1, layer_width):
                factors.append(
                    (
                        left,
                        right,
                        stream.random_bool(),
                        stream.randint(min_weight, max_weight),
                    )
                )
        within_layers.append(factors)

    between_layers: list[list[IsingFactor]] = []
    for _layer in range(num_layers - 1):
        permutation = list(range(layer_width))
        stream.shuffle(permutation)
        between_layers.append(
            [
                (
                    left,
                    permutation[left],
                    stream.random_bool(),
                    stream.randint(min_weight, max_weight),
                )
                for left in range(layer_width)
            ]
        )

    assignment, optimum = solve_layered_ising(
        layer_width=layer_width,
        within_layers=within_layers,
        between_layers=between_layers,
    )
    soft_clauses: list[SoftClause] = []
    for layer, factors in enumerate(within_layers):
        base = layer * layer_width
        for left, right, preferred, weight in factors:
            soft_clauses.extend(_soft_factor(base + left + 1, base + right + 1, preferred, weight))
    for layer, factors in enumerate(between_layers):
        left_base = layer * layer_width
        right_base = (layer + 1) * layer_width
        for left, right, preferred, weight in factors:
            soft_clauses.extend(
                _soft_factor(left_base + left + 1, right_base + right + 1, preferred, weight)
            )
    return CaseBlueprint(
        num_variables=num_layers * layer_width,
        hard_clauses=(),
        soft_clauses=tuple(soft_clauses),
        threshold=optimum,
        reference_assignment=assignment,
        reference_cost=optimum,
        metadata={
            "mathematical_family": "hidden_clique_path_ising",
            "num_layers": num_layers,
            "layer_width": layer_width,
            "num_pair_factors": len(soft_clauses) // 2,
            "certified_optimum": optimum,
            "optimality_certificate": "exact_min_sum_transfer_dynamic_program",
        },
    )


__all__ = ["CASE_ID", "DEFAULT_PARAMETERS", "build"]
