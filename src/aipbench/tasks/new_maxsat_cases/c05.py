"""C05: sparse affine factors compiled through complete XOR gates."""

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
from aipbench.tasks.new_maxsat_cases.reference import ParityFactor, solve_parity_components

CASE_ID: Final = "c05"
DEFAULT_PARAMETERS: Final[Mapping[str, Any]] = {
    "num_components": 320,
    "component_width": 16,
    "factors_per_component": 44,
    "min_weight": 1,
    "max_weight": 4093,
}


def _xor_clauses(left: int, right: int, output: int, rhs: bool) -> tuple[Clause, ...]:
    clauses: list[Clause] = []
    for left_value in (False, True):
        for right_value in (False, True):
            output_value = left_value ^ right_value ^ rhs
            forbidden = (left_value, right_value, not output_value)
            literals = tuple(
                -variable if value else variable
                for variable, value in zip((left, right, output), forbidden, strict=True)
            )
            clauses.append(Clause(literals))
    return tuple(clauses)


def build(stream: NewMaxSatStream, parameters: Mapping[str, Any]) -> CaseBlueprint:
    num_components = integer_parameter(parameters, "num_components", minimum=1)
    component_width = integer_parameter(parameters, "component_width", minimum=3)
    factors_per_component = integer_parameter(parameters, "factors_per_component", minimum=1)
    min_weight = integer_parameter(parameters, "min_weight", minimum=1)
    max_weight = integer_parameter(parameters, "max_weight", minimum=1)
    if component_width > 24:
        raise ValueError("parity component exceeds exact reference width")
    if max_weight < min_weight:
        raise ValueError("invalid weight interval")

    num_free_variables = num_components * component_width
    factors: list[ParityFactor] = []
    factor_inputs: list[tuple[int, int, int]] = []
    for component in range(num_components):
        variables = list(
            range(component * component_width + 1, (component + 1) * component_width + 1)
        )
        for factor_index in range(factors_per_component):
            if factor_index < component_width:
                chosen = (
                    variables[factor_index],
                    variables[(factor_index + 1) % component_width],
                    variables[(factor_index + 3) % component_width],
                )
            else:
                shuffled = variables.copy()
                stream.shuffle(shuffled)
                chosen = tuple(shuffled[:3])
            rhs = stream.random_bool()
            prefer_true = stream.random_bool()
            weight = stream.randint(min_weight, max_weight)
            factors.append((chosen, rhs, prefer_true, weight))
            factor_inputs.append(chosen)

    free_assignment, optimum = solve_parity_components(
        num_free_variables=num_free_variables, factors=factors
    )
    assignment = list(free_assignment)
    hard_clauses: list[Clause] = []
    soft_clauses: list[SoftClause] = []
    for factor_index, ((first, second, third), rhs, prefer_true, weight) in enumerate(factors):
        intermediate = num_free_variables + 2 * factor_index + 1
        output = intermediate + 1
        first_rhs = stream.random_bool()
        second_rhs = rhs ^ first_rhs
        intermediate_value = free_assignment[first - 1] ^ free_assignment[second - 1] ^ first_rhs
        output_value = intermediate_value ^ free_assignment[third - 1] ^ second_rhs
        assignment.extend((intermediate_value, output_value))
        hard_clauses.extend(_xor_clauses(first, second, intermediate, first_rhs))
        hard_clauses.extend(_xor_clauses(intermediate, third, output, second_rhs))
        soft_clauses.append(SoftClause((output if prefer_true else -output,), weight))

    return CaseBlueprint(
        num_variables=len(assignment),
        hard_clauses=tuple(hard_clauses),
        soft_clauses=tuple(soft_clauses),
        threshold=optimum,
        reference_assignment=tuple(assignment),
        reference_cost=optimum,
        metadata={
            "mathematical_family": "sparse_affine_parity_factor_components",
            "num_components": num_components,
            "component_width": component_width,
            "num_free_variables": num_free_variables,
            "num_factors": len(factors),
            "num_xor_gates": 2 * len(factors),
            "certified_optimum": optimum,
            "optimality_certificate": "componentwise_gray_code_enumeration",
        },
    )


__all__ = ["CASE_ID", "DEFAULT_PARAMETERS", "build"]
