"""C04: marked width-16 weighted hitting-set path."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Final

from aipbench.tasks.new_set_cover_cases.common import (
    CaseBlueprint,
    NewSetCoverStream,
    WeightedCandidate,
    integer_parameter,
)

CASE_ID: Final = "c04"
DEFAULT_PARAMETERS: Final[Mapping[str, Any]] = {
    "num_bags": 124,
    "bag_width": 16,
    "overlap_width": 8,
    "clauses_per_bag": 32,
    "min_weight": 17,
    "max_weight": 997,
}


def solve_weighted_bag_path(
    *,
    bags: Sequence[Sequence[int]],
    clauses_by_bag: Sequence[Sequence[Sequence[int]]],
    weights: Sequence[int],
) -> tuple[int, ...]:
    """Solve a path-local weighted hitting set exactly by separator DP."""

    if not bags or len(bags) != len(clauses_by_bag):
        raise ValueError("bag path and clause groups must be nonempty and aligned")
    width = len(bags[0])
    if not 1 <= width <= 20 or any(len(bag) != width for bag in bags):
        raise ValueError("bag width is invalid or inconsistent")
    dp: dict[int, int] = {}
    histories: list[dict[int, int]] = []
    previous_bag: tuple[int, ...] | None = None
    for _bag_index, (raw_bag, raw_clauses) in enumerate(zip(bags, clauses_by_bag, strict=True)):
        bag = tuple(raw_bag)
        position = {variable: index for index, variable in enumerate(bag)}
        clause_masks = []
        for clause in raw_clauses:
            mask = 0
            for variable in clause:
                if variable not in position:
                    raise ValueError("a clause escapes its declared bag")
                mask |= 1 << position[variable]
            if not mask:
                raise ValueError("empty hitting-set clause")
            clause_masks.append(mask)
        valid = bytearray(b"\x01") * (1 << width)
        full = (1 << width) - 1
        for clause_mask in clause_masks:
            submask = full ^ clause_mask
            current = submask
            while True:
                valid[current] = 0
                if current == 0:
                    break
                current = (current - 1) & submask

        if previous_bag is None:
            costs = [0] * (1 << width)
            for mask in range(1, 1 << width):
                bit = mask & -mask
                index = bit.bit_length() - 1
                costs[mask] = costs[mask ^ bit] + weights[bag[index]]
            dp = {mask: costs[mask] for mask, feasible in enumerate(valid) if feasible}
            histories.append({mask: -1 for mask in dp})
            previous_bag = bag
            continue

        overlap = tuple(variable for variable in bag if variable in set(previous_bag))
        previous_positions = tuple(previous_bag.index(variable) for variable in overlap)
        current_positions = tuple(position[variable] for variable in overlap)
        introduced = tuple(variable for variable in bag if variable not in overlap)
        introduced_positions = tuple(position[variable] for variable in introduced)

        best: dict[int, tuple[int, int]] = {}
        for previous_mask, previous_cost in dp.items():
            key = sum(
                ((previous_mask >> bit_position) & 1) << key_position
                for key_position, bit_position in enumerate(previous_positions)
            )
            if key not in best or previous_cost < best[key][0]:
                best[key] = (previous_cost, previous_mask)
        introduced_cost = [0] * (1 << len(introduced))
        for mask in range(1, 1 << len(introduced)):
            bit = mask & -mask
            index = bit.bit_length() - 1
            introduced_cost[mask] = introduced_cost[mask ^ bit] + weights[introduced[index]]
        next_dp: dict[int, int] = {}
        parents: dict[int, int] = {}
        for mask, feasible in enumerate(valid):
            if not feasible:
                continue
            key = sum(
                ((mask >> bit_position) & 1) << key_position
                for key_position, bit_position in enumerate(current_positions)
            )
            predecessor = best.get(key)
            if predecessor is None:
                continue
            introduced_mask = sum(
                ((mask >> bit_position) & 1) << key_position
                for key_position, bit_position in enumerate(introduced_positions)
            )
            next_dp[mask] = predecessor[0] + introduced_cost[introduced_mask]
            parents[mask] = predecessor[1]
        if not next_dp:
            raise ValueError("bag path is infeasible")
        dp = next_dp
        histories.append(parents)
        previous_bag = bag

    state = min(dp, key=dp.get)
    chosen: set[int] = set()
    for bag_index in range(len(bags) - 1, -1, -1):
        bag = tuple(bags[bag_index])
        chosen.update(variable for position, variable in enumerate(bag) if (state >> position) & 1)
        state = histories[bag_index][state]
    return tuple(sorted(chosen))


def build(stream: NewSetCoverStream, parameters: Mapping[str, Any]) -> CaseBlueprint:
    num_bags = integer_parameter(parameters, "num_bags", minimum=3)
    width = integer_parameter(parameters, "bag_width", minimum=6)
    overlap = integer_parameter(parameters, "overlap_width", minimum=1)
    clauses_per_bag = integer_parameter(parameters, "clauses_per_bag", minimum=1)
    min_weight = integer_parameter(parameters, "min_weight", minimum=1)
    max_weight = integer_parameter(parameters, "max_weight", minimum=1)
    if width > 20 or not overlap < width or max_weight < min_weight:
        raise ValueError("invalid marked-path parameters")
    step = width - overlap
    num_variables = width + (num_bags - 1) * step
    if num_variables > 2_000 or num_bags * clauses_per_bag > 4_096:
        raise ValueError("marked-path profile exceeds its safe envelope")
    weights = tuple(
        min_weight + stream.randbelow(max_weight - min_weight + 1) for _ in range(num_variables)
    )
    bags = tuple(tuple(range(bag * step, bag * step + width)) for bag in range(num_bags))
    clauses_by_bag: list[tuple[tuple[int, ...], ...]] = []
    for bag in bags:
        clauses: list[tuple[int, ...]] = []
        order = list(bag)
        stream.shuffle(order)
        for offset in range(0, width, 4):
            clauses.append(tuple(order[offset : offset + 4]))
        while len(clauses) < clauses_per_bag:
            order = list(bag)
            stream.shuffle(order)
            size = 3 + stream.randbelow(2)
            clause = tuple(sorted(order[:size]))
            if clause not in clauses:
                clauses.append(clause)
        clauses_by_bag.append(tuple(clauses))
    reference = solve_weighted_bag_path(
        bags=bags,
        clauses_by_bag=clauses_by_bag,
        weights=weights,
    )
    budget = sum(weights[variable] for variable in reference)
    marker_weight = budget + 1
    incidence: list[set[int]] = [set() for _ in range(num_variables)]
    marker_indices: list[int] = []
    element = 0
    for clauses in clauses_by_bag:
        marker_index = len(incidence)
        marker_indices.append(marker_index)
        incidence.append(set())
        for clause in clauses:
            for variable in clause:
                incidence[variable].add(element)
            incidence[marker_index].add(element)
            element += 1
    candidates = tuple(
        WeightedCandidate(
            frozenset(elements),
            weights[index] if index < num_variables else marker_weight,
        )
        for index, elements in enumerate(incidence)
    )
    return CaseBlueprint(
        universe_size=element,
        candidates=candidates,
        budget=budget,
        reference_candidate_indices=reference,
        metadata={
            "mathematical_family": "marked_width16_weighted_hitting_set_path",
            "num_bags": num_bags,
            "bag_width": width,
            "overlap_width": overlap,
            "num_variables": num_variables,
            "num_markers": len(marker_indices),
            "optimality_certificate": "exact_separator_dynamic_program",
        },
    )


__all__ = ["CASE_ID", "DEFAULT_PARAMETERS", "build", "solve_weighted_bag_path"]
