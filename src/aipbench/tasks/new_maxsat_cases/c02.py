"""C02: scaled weighted implication-closure instance."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from aipbench.tasks.new_maxsat_cases.common import (
    CaseBlueprint,
    Clause,
    NewMaxSatStream,
    SoftClause,
    integer_parameter,
)
from aipbench.tasks.new_maxsat_cases.reference import solve_implication_closure

CASE_ID: Final = "c02"
DEFAULT_PARAMETERS: Final[Mapping[str, Any]] = {
    "num_layers": 80,
    "layer_width": 150,
    "adjacent_degree": 8,
    "skip_degree": 2,
    "min_weight": 1,
    "max_weight": 997,
}


def _offsets(stream: NewMaxSatStream, *, width: int, degree: int) -> list[int]:
    if degree > width:
        raise ValueError("closure degree exceeds layer width")
    offsets = [0]
    if degree > 1:
        offsets.append(1)
    candidates = list(range(2, width))
    stream.shuffle(candidates)
    offsets.extend(candidates[: degree - len(offsets)])
    stream.shuffle(offsets)
    return offsets


def build(stream: NewMaxSatStream, parameters: Mapping[str, Any]) -> CaseBlueprint:
    num_layers = integer_parameter(parameters, "num_layers", minimum=3)
    layer_width = integer_parameter(parameters, "layer_width", minimum=4)
    adjacent_degree = integer_parameter(parameters, "adjacent_degree", minimum=2)
    skip_degree = integer_parameter(parameters, "skip_degree", minimum=0)
    min_weight = integer_parameter(parameters, "min_weight", minimum=1)
    max_weight = integer_parameter(parameters, "max_weight", minimum=1)
    if max_weight < min_weight:
        raise ValueError("invalid weight interval")
    if adjacent_degree > layer_width or skip_degree > layer_width:
        raise ValueError("closure degree exceeds layer width")

    num_variables = num_layers * layer_width
    implications: list[tuple[int, int]] = []
    for layer in range(num_layers - 1):
        offsets = _offsets(stream, width=layer_width, degree=adjacent_degree)
        for position in range(layer_width):
            antecedent = layer * layer_width + position + 1
            for offset in offsets:
                consequent = (layer + 1) * layer_width + (position + offset) % layer_width + 1
                implications.append((antecedent, consequent))
    for layer in range(num_layers - 2):
        offsets = _offsets(stream, width=layer_width, degree=skip_degree)
        for position in range(layer_width):
            antecedent = layer * layer_width + position + 1
            for offset in offsets:
                consequent = (layer + 2) * layer_width + (position + offset) % layer_width + 1
                implications.append((antecedent, consequent))

    preferences = [
        (variable, stream.random_bool(), stream.randint(min_weight, max_weight))
        for variable in range(1, num_variables + 1)
    ]
    assignment, optimum = solve_implication_closure(
        num_variables=num_variables,
        implications=implications,
        preferences=preferences,
    )
    hard_clauses = tuple(
        Clause((-antecedent, consequent)) for antecedent, consequent in implications
    )
    soft_clauses = tuple(
        SoftClause((variable if prefer_true else -variable,), weight)
        for variable, prefer_true, weight in preferences
    )
    return CaseBlueprint(
        num_variables=num_variables,
        hard_clauses=hard_clauses,
        soft_clauses=soft_clauses,
        threshold=optimum,
        reference_assignment=assignment,
        reference_cost=optimum,
        metadata={
            "mathematical_family": "weighted_successor_closure",
            "num_layers": num_layers,
            "layer_width": layer_width,
            "num_implications": len(implications),
            "weighted_unit_preferences": len(preferences),
            "certified_optimum": optimum,
            "optimality_certificate": "integer_min_cut",
        },
    )


__all__ = ["CASE_ID", "DEFAULT_PARAMETERS", "build"]
