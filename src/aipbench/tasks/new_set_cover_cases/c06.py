"""C06: calibrated width-16 weighted hitting-set tree."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Final

from aipbench.tasks.new_set_cover_cases.common import (
    CaseBlueprint,
    NewSetCoverStream,
    WeightedCandidate,
    integer_parameter,
)

CASE_ID: Final = "c06"
DEFAULT_PARAMETERS: Final[Mapping[str, Any]] = {
    "num_bags": 109,
    "bag_width": 16,
    "overlap_width": 6,
    "clauses_per_bag": 34,
    "branching_factor": 3,
    "min_weight": 23,
    "max_weight": 1_597,
}


def solve_weighted_bag_tree(
    *,
    bags: Sequence[Sequence[int]],
    clauses_by_bag: Sequence[Sequence[Sequence[int]]],
    parents: Sequence[int],
    weights: Sequence[int],
) -> tuple[int, ...]:
    """Solve a running-intersection bag tree by exact bottom-up separator DP."""

    if not bags or len(bags) != len(clauses_by_bag) or len(bags) != len(parents):
        raise ValueError("tree bags, clause groups, and parents must align")
    width = len(bags[0])
    if not 1 <= width <= 20 or parents[0] != -1:
        raise ValueError("invalid bag width or root parent")
    children: list[list[int]] = [[] for _ in bags]
    for child, parent in enumerate(parents[1:], start=1):
        if not 0 <= parent < child:
            raise ValueError("parents must precede children")
        children[parent].append(child)

    valid_masks: list[list[int]] = []
    for raw_bag, raw_clauses in zip(bags, clauses_by_bag, strict=True):
        bag = tuple(raw_bag)
        if len(bag) != width or len(set(bag)) != width:
            raise ValueError("tree bag width is inconsistent")
        position = {variable: index for index, variable in enumerate(bag)}
        clause_masks = []
        for clause in raw_clauses:
            mask = 0
            for variable in clause:
                if variable not in position:
                    raise ValueError("a tree clause escapes its bag")
                mask |= 1 << position[variable]
            if not mask:
                raise ValueError("empty tree hitting-set clause")
            clause_masks.append(mask)
        valid = bytearray(b"\x01") * (1 << width)
        full = (1 << width) - 1
        for clause_mask in clause_masks:
            disjoint = full ^ clause_mask
            submask = disjoint
            while True:
                valid[submask] = 0
                if submask == 0:
                    break
                submask = (submask - 1) & disjoint
        valid_masks.append([mask for mask, feasible in enumerate(valid) if feasible])

    dp: list[dict[int, int]] = [{} for _ in bags]
    edge_choice: dict[tuple[int, int], dict[int, int]] = {}
    for bag_index in range(len(bags) - 1, -1, -1):
        bag = tuple(bags[bag_index])
        parent_index = parents[bag_index]
        parent_bag = set() if parent_index < 0 else set(bags[parent_index])
        introduced_positions = tuple(
            position for position, variable in enumerate(bag) if variable not in parent_bag
        )
        base_cost: dict[int, int] = {}
        for mask in valid_masks[bag_index]:
            base_cost[mask] = sum(
                weights[bag[position]]
                for position in introduced_positions
                if (mask >> position) & 1
            )
        for child in children[bag_index]:
            child_bag = tuple(bags[child])
            overlap = tuple(sorted(set(bag) & set(child_bag)))
            parent_positions = tuple(bag.index(variable) for variable in overlap)
            child_positions = tuple(child_bag.index(variable) for variable in overlap)
            best: dict[int, tuple[int, int]] = {}
            for child_mask, cost in dp[child].items():
                key = sum(
                    ((child_mask >> position) & 1) << key_position
                    for key_position, position in enumerate(child_positions)
                )
                if key not in best or cost < best[key][0]:
                    best[key] = (cost, child_mask)
            edge_choice[(bag_index, child)] = {
                key: child_mask for key, (_cost, child_mask) in best.items()
            }
            next_cost: dict[int, int] = {}
            for mask, cost in base_cost.items():
                key = sum(
                    ((mask >> position) & 1) << key_position
                    for key_position, position in enumerate(parent_positions)
                )
                if key in best:
                    next_cost[mask] = cost + best[key][0]
            base_cost = next_cost
        if not base_cost:
            raise ValueError("tree hitting-set instance is infeasible")
        dp[bag_index] = base_cost

    root_mask = min(dp[0], key=dp[0].get)
    chosen: set[int] = set()
    stack = [(0, root_mask)]
    while stack:
        bag_index, mask = stack.pop()
        bag = tuple(bags[bag_index])
        chosen.update(variable for position, variable in enumerate(bag) if (mask >> position) & 1)
        for child in children[bag_index]:
            child_bag = tuple(bags[child])
            overlap = tuple(sorted(set(bag) & set(child_bag)))
            parent_positions = tuple(bag.index(variable) for variable in overlap)
            key = sum(
                ((mask >> position) & 1) << key_position
                for key_position, position in enumerate(parent_positions)
            )
            stack.append((child, edge_choice[(bag_index, child)][key]))
    return tuple(sorted(chosen))


def build(stream: NewSetCoverStream, parameters: Mapping[str, Any]) -> CaseBlueprint:
    num_bags = integer_parameter(parameters, "num_bags", minimum=4)
    width = integer_parameter(parameters, "bag_width", minimum=8)
    overlap = integer_parameter(parameters, "overlap_width", minimum=1)
    clauses_per_bag = integer_parameter(parameters, "clauses_per_bag", minimum=1)
    branching = integer_parameter(parameters, "branching_factor", minimum=2)
    min_weight = integer_parameter(parameters, "min_weight", minimum=1)
    max_weight = integer_parameter(parameters, "max_weight", minimum=1)
    if width != 16 or overlap != 6 or branching != 3 or max_weight < min_weight:
        raise ValueError("C06 requires its validated width-16 ternary profile")

    step = width - overlap
    num_variables = width + (num_bags - 1) * step
    weights = tuple(
        min_weight + stream.randbelow(max_weight - min_weight + 1) for _ in range(num_variables)
    )
    patterns = (
        (0, 1, 2, 3, 4, 5),
        (4, 5, 6, 7, 8, 9),
        (0, 1, 2, 7, 8, 9),
    )
    bags: list[tuple[int, ...]] = [tuple(range(width))]
    owned: list[tuple[int, ...]] = [tuple(range(10))]
    parents = [-1]
    next_variable = width
    for child in range(1, num_bags):
        parent = (child - 1) // branching
        child_ordinal = (child - 1) % branching
        shared = tuple(owned[parent][position] for position in patterns[child_ordinal])
        introduced = tuple(range(next_variable, next_variable + step))
        next_variable += step
        bags.append((*shared, *introduced))
        owned.append(introduced)
        parents.append(parent)

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

    reference = solve_weighted_bag_tree(
        bags=bags,
        clauses_by_bag=clauses_by_bag,
        parents=parents,
        weights=weights,
    )
    budget = sum(weights[variable] for variable in reference)
    marker_weight = budget + 1
    incidence: list[set[int]] = [set() for _ in range(num_variables)]
    element = 0
    for clauses in clauses_by_bag:
        marker_index = len(incidence)
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
            "mathematical_family": "marked_width16_weighted_hitting_set_ternary_tree",
            "num_bags": num_bags,
            "bag_width": width,
            "overlap_width": overlap,
            "num_variables": num_variables,
            "num_markers": num_bags,
            "optimality_certificate": "exact_tree_separator_dynamic_program",
        },
    )


__all__ = ["CASE_ID", "DEFAULT_PARAMETERS", "build", "solve_weighted_bag_tree"]
