"""C03: bounded-window weighted CNF with an exact dynamic program."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Final

from aipbench.tasks.new_maxsat_cases.common import (
    CaseBlueprint,
    Clause,
    NewMaxSatStream,
    SoftClause,
    integer_parameter,
)

CASE_ID: Final = "c03"
DEFAULT_PARAMETERS: Final[Mapping[str, Any]] = {
    "num_variables": 2_400,
    "window_width": 12,
    "hard_clauses_per_step": 3,
    "soft_clauses_per_step": 4,
    "min_weight": 1,
    "max_weight": 101,
}


def _clause_satisfied(literals: Sequence[int], *, mask: int, low_variable: int) -> bool:
    return any(
        bool((mask >> (abs(literal) - low_variable)) & 1) == (literal > 0) for literal in literals
    )


def solve_bounded_window(
    *,
    num_variables: int,
    window_width: int,
    hard_clauses: Sequence[Clause],
    soft_clauses: Sequence[SoftClause],
) -> tuple[tuple[bool, ...], int]:
    """Return an exact optimum when every clause spans at most ``window_width``."""

    if not 1 <= window_width <= num_variables:
        raise ValueError("invalid bounded-window width")
    hard_by_last: list[list[Clause]] = [[] for _ in range(num_variables)]
    soft_by_last: list[list[SoftClause]] = [[] for _ in range(num_variables)]
    for clause in hard_clauses:
        variables = [abs(literal) for literal in clause.literals]
        if max(variables) - min(variables) >= window_width:
            raise ValueError("hard clause exceeds bounded-window width")
        hard_by_last[max(variables) - 1].append(clause)
    for clause in soft_clauses:
        variables = [abs(literal) for literal in clause.literals]
        if max(variables) - min(variables) >= window_width:
            raise ValueError("soft clause exceeds bounded-window width")
        soft_by_last[max(variables) - 1].append(clause)

    infinity = sum(clause.weight for clause in soft_clauses) + 1
    previous = [0]
    back_choices: list[bytearray] = []
    for last_index in range(num_variables):
        active_size = min(last_index + 1, window_width)
        low_variable = last_index - active_size + 2
        state_count = 1 << active_size
        current = [infinity] * state_count
        choices = bytearray(state_count)
        lower_mask = (1 << (active_size - 1)) - 1
        for mask in range(state_count):
            if last_index < window_width:
                predecessor = mask & lower_mask
                value = previous[predecessor]
            else:
                shared = (mask & lower_mask) << 1
                if previous[shared] <= previous[shared | 1]:
                    predecessor = shared
                    value = previous[shared]
                else:
                    predecessor = shared | 1
                    value = previous[shared | 1]
                    choices[mask] = 1
            if value >= infinity or any(
                not _clause_satisfied(
                    clause.literals,
                    mask=mask,
                    low_variable=low_variable,
                )
                for clause in hard_by_last[last_index]
            ):
                continue
            current[mask] = value + sum(
                clause.weight
                for clause in soft_by_last[last_index]
                if not _clause_satisfied(
                    clause.literals,
                    mask=mask,
                    low_variable=low_variable,
                )
            )
        previous = current
        back_choices.append(choices)

    optimum = min(previous)
    if optimum >= infinity:
        raise ValueError("bounded-window hard formula is unsatisfiable")
    mask = previous.index(optimum)
    assignment = [False] * num_variables
    final_size = min(num_variables, window_width)
    final_low = num_variables - final_size
    for offset in range(final_size):
        assignment[final_low + offset] = bool((mask >> offset) & 1)
    for last_index in range(num_variables - 1, window_width - 1, -1):
        dropped = int(back_choices[last_index][mask])
        assignment[last_index - window_width] = bool(dropped)
        mask = ((mask & ((1 << (window_width - 1)) - 1)) << 1) | dropped
    return tuple(assignment), optimum


def _sample_variables(
    stream: NewMaxSatStream,
    *,
    last_variable: int,
    window_width: int,
    arity: int,
) -> list[int]:
    first_variable = max(1, last_variable - window_width + 1)
    earlier = list(range(first_variable, last_variable))
    stream.shuffle(earlier)
    chosen = [last_variable, *earlier[: arity - 1]]
    stream.shuffle(chosen)
    return chosen


def build(stream: NewMaxSatStream, parameters: Mapping[str, Any]) -> CaseBlueprint:
    num_variables = integer_parameter(parameters, "num_variables", minimum=8)
    window_width = integer_parameter(parameters, "window_width", minimum=2)
    hard_per_step = integer_parameter(parameters, "hard_clauses_per_step", minimum=1)
    soft_per_step = integer_parameter(parameters, "soft_clauses_per_step", minimum=1)
    min_weight = integer_parameter(parameters, "min_weight", minimum=1)
    max_weight = integer_parameter(parameters, "max_weight", minimum=1)
    if window_width > num_variables or window_width > 16:
        raise ValueError("unsupported bounded-window width")
    if max_weight < min_weight:
        raise ValueError("invalid weight interval")

    planted = [stream.random_bool() for _ in range(num_variables)]
    hard_clauses: list[Clause] = []
    soft_clauses: list[SoftClause] = []
    for last_variable in range(1, num_variables + 1):
        available = min(last_variable, window_width)
        if available >= 2:
            for _ in range(hard_per_step):
                arity = min(3, available)
                variables = _sample_variables(
                    stream,
                    last_variable=last_variable,
                    window_width=window_width,
                    arity=arity,
                )
                satisfying_index = stream.randbelow(arity)
                literals = []
                for index, variable in enumerate(variables):
                    positive = planted[variable - 1]
                    if index != satisfying_index and stream.random_bool():
                        positive = not positive
                    literals.append(variable if positive else -variable)
                hard_clauses.append(Clause(tuple(literals)))
        for _ in range(soft_per_step):
            arity = 1 + stream.randbelow(min(3, available))
            variables = _sample_variables(
                stream,
                last_variable=last_variable,
                window_width=window_width,
                arity=arity,
            )
            literals = tuple(
                variable if stream.random_bool() else -variable for variable in variables
            )
            soft_clauses.append(SoftClause(literals, stream.randint(min_weight, max_weight)))

    assignment, optimum = solve_bounded_window(
        num_variables=num_variables,
        window_width=window_width,
        hard_clauses=hard_clauses,
        soft_clauses=soft_clauses,
    )
    return CaseBlueprint(
        num_variables=num_variables,
        hard_clauses=tuple(hard_clauses),
        soft_clauses=tuple(soft_clauses),
        threshold=optimum,
        reference_assignment=assignment,
        reference_cost=optimum,
        metadata={
            "mathematical_family": "bounded_window_weighted_cnf",
            "window_width": window_width,
            "num_hard_clauses": len(hard_clauses),
            "num_soft_clauses": len(soft_clauses),
            "certified_optimum": optimum,
            "optimality_certificate": "exact_path_decomposition_dynamic_program",
        },
    )


__all__ = ["CASE_ID", "DEFAULT_PARAMETERS", "build", "solve_bounded_window"]
