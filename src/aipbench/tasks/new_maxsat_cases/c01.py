"""C01: uniquely propagated two-literal calibration instance."""

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

CASE_ID: Final = "c01"
DEFAULT_PARAMETERS: Final[Mapping[str, Any]] = {
    "num_variables": 160,
    "num_soft_clauses": 240,
    "min_soft_weight": 1,
    "max_soft_weight": 31,
}


def _literal(variable: int, *, satisfied: bool, assignment: list[bool]) -> int:
    return variable if assignment[variable - 1] == satisfied else -variable


def build(stream: NewMaxSatStream, parameters: Mapping[str, Any]) -> CaseBlueprint:
    num_variables = integer_parameter(parameters, "num_variables", minimum=8)
    num_soft_clauses = integer_parameter(parameters, "num_soft_clauses", minimum=2)
    min_soft_weight = integer_parameter(parameters, "min_soft_weight", minimum=1)
    max_soft_weight = integer_parameter(parameters, "max_soft_weight", minimum=1)
    if max_soft_weight < min_soft_weight:
        raise ValueError("invalid soft-weight interval")

    assignment = [False] * num_variables
    truth_order = list(range(num_variables))
    stream.shuffle(truth_order)
    true_count = num_variables // 2 + stream.randbelow(3) - 1
    for index in truth_order[:true_count]:
        assignment[index] = True

    chain = list(range(1, num_variables + 1))
    stream.shuffle(chain)
    first = chain[0]
    hard_clauses = [Clause((_literal(first, satisfied=True, assignment=assignment),))]
    for left, right in zip(chain[:-1], chain[1:], strict=True):
        left_value = assignment[left - 1]
        right_value = assignment[right - 1]
        if left_value == right_value:
            hard_clauses.extend((Clause((-left, right)), Clause((left, -right))))
        else:
            hard_clauses.extend((Clause((left, right)), Clause((-left, -right))))

    soft_clauses: list[SoftClause] = []
    unsatisfied_count = 0
    for index in range(num_soft_clauses):
        arity = 2 + stream.randbelow(2)
        variables = list(range(1, num_variables + 1))
        stream.shuffle(variables)
        chosen = variables[:arity]
        should_be_unsatisfied = index % 7 == 0
        satisfying_literal_index = stream.randbelow(arity)
        literals: list[int] = []
        for literal_index, variable in enumerate(chosen):
            satisfied = not should_be_unsatisfied and literal_index == satisfying_literal_index
            literals.append(_literal(variable, satisfied=satisfied, assignment=assignment))
        weight = stream.randint(min_soft_weight, max_soft_weight)
        soft_clauses.append(SoftClause(tuple(literals), weight))
        if should_be_unsatisfied:
            unsatisfied_count += 1

    reference_cost = sum(
        clause.weight
        for clause in soft_clauses
        if not any(assignment[abs(literal) - 1] == (literal > 0) for literal in clause.literals)
    )
    if unsatisfied_count == 0 or reference_cost == 0:
        raise AssertionError("C01 must contain positive-cost soft clauses")

    return CaseBlueprint(
        num_variables=num_variables,
        hard_clauses=tuple(hard_clauses),
        soft_clauses=tuple(soft_clauses),
        threshold=reference_cost,
        reference_assignment=tuple(assignment),
        reference_cost=reference_cost,
        metadata={
            "mathematical_family": "anchored_binary_relation_chain",
            "logical_true_count": true_count,
            "chain_length": num_variables,
            "unique_hard_assignment": True,
            "soft_clause_arities": [2, 3],
            "unsatisfied_soft_clauses": unsatisfied_count,
            "certified_optimum": reference_cost,
            "optimality_certificate": "unique_hard_feasible_assignment",
        },
    )
