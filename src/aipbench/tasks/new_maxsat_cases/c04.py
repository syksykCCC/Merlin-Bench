"""C04: maximum-weight closure compiled through local CNF gates."""

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

CASE_ID: Final = "c04"
DEFAULT_PARAMETERS: Final[Mapping[str, Any]] = {
    "num_layers": 64,
    "layer_width": 96,
    "adjacent_degree": 4,
    "skip_degree": 1,
    "min_weight": 1,
    "max_weight": 4093,
}


def _offsets(stream: NewMaxSatStream, *, width: int, degree: int) -> list[int]:
    if degree > width:
        raise ValueError("gadget-closure degree exceeds layer width")
    candidates = list(range(width))
    stream.shuffle(candidates)
    return candidates[:degree]


def build(stream: NewMaxSatStream, parameters: Mapping[str, Any]) -> CaseBlueprint:
    num_layers = integer_parameter(parameters, "num_layers", minimum=3)
    layer_width = integer_parameter(parameters, "layer_width", minimum=2)
    adjacent_degree = integer_parameter(parameters, "adjacent_degree", minimum=2)
    skip_degree = integer_parameter(parameters, "skip_degree", minimum=0)
    min_weight = integer_parameter(parameters, "min_weight", minimum=1)
    max_weight = integer_parameter(parameters, "max_weight", minimum=1)
    if adjacent_degree > layer_width or skip_degree > layer_width:
        raise ValueError("gadget-closure degree exceeds layer width")
    if max_weight < min_weight:
        raise ValueError("invalid weight interval")

    num_core_variables = num_layers * layer_width
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
        for variable in range(1, num_core_variables + 1)
    ]
    core_assignment, optimum = solve_implication_closure(
        num_variables=num_core_variables,
        implications=implications,
        preferences=preferences,
    )

    constant = num_core_variables + len(implications) + 1
    assignment = list(core_assignment)
    assignment.extend(core_assignment[antecedent - 1] for antecedent, _ in implications)
    assignment.append(True)
    hard_clauses: list[Clause] = [Clause((constant,))]
    for edge_index, (antecedent, consequent) in enumerate(implications):
        auxiliary = num_core_variables + edge_index + 1
        # With constant=true, the first three clauses encode auxiliary=antecedent.
        # The final clause then enforces the logical closure edge.
        hard_clauses.extend(
            (
                Clause((-antecedent, -constant, auxiliary)),
                Clause((antecedent, -auxiliary)),
                Clause((constant, -auxiliary)),
                Clause((-auxiliary, consequent)),
            )
        )
    soft_clauses = tuple(
        SoftClause((variable if prefer_true else -variable,), weight)
        for variable, prefer_true, weight in preferences
    )
    return CaseBlueprint(
        num_variables=len(assignment),
        hard_clauses=tuple(hard_clauses),
        soft_clauses=soft_clauses,
        threshold=optimum,
        reference_assignment=tuple(assignment),
        reference_cost=optimum,
        metadata={
            "mathematical_family": "locally_compiled_maximum_weight_closure",
            "num_core_variables": num_core_variables,
            "num_gate_auxiliaries": len(implications),
            "num_implications": len(implications),
            "num_layers": num_layers,
            "layer_width": layer_width,
            "certified_optimum": optimum,
            "optimality_certificate": "gadget_elimination_plus_integer_min_cut",
        },
    )


__all__ = ["CASE_ID", "DEFAULT_PARAMETERS", "build"]
