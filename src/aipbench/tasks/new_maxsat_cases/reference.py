"""Maintainer reference routines for structured new MaxSAT cases."""

from __future__ import annotations

from collections import deque
from collections.abc import Mapping, Sequence
from typing import Any

from aipbench.tasks.shared.maxflow import solve_maxflow

ParityFactor = tuple[tuple[int, ...], bool, bool, int]
IsingFactor = tuple[int, int, bool, int]


def _ising_layer_energy(width: int, factors: Sequence[IsingFactor]) -> list[int]:
    state_count = 1 << width
    incidence: list[list[int]] = [[] for _ in range(width)]
    parities = [False] * len(factors)
    cost = 0
    for factor_index, (left, right, preferred_parity, weight) in enumerate(factors):
        if not 0 <= left < right < width or weight <= 0:
            raise ValueError("invalid within-layer Ising factor")
        incidence[left].append(factor_index)
        incidence[right].append(factor_index)
        if preferred_parity:
            cost += weight
    energies = [0] * state_count
    energies[0] = cost
    gray = 0
    for counter in range(1, state_count):
        flipped = (counter & -counter).bit_length() - 1
        gray ^= 1 << flipped
        for factor_index in incidence[flipped]:
            _left, _right, preferred_parity, weight = factors[factor_index]
            if parities[factor_index] == preferred_parity:
                cost += weight
            else:
                cost -= weight
            parities[factor_index] = not parities[factor_index]
        energies[gray] = cost
    return energies


def solve_layered_ising(
    *,
    layer_width: int,
    within_layers: Sequence[Sequence[IsingFactor]],
    between_layers: Sequence[Sequence[IsingFactor]],
) -> tuple[tuple[bool, ...], int]:
    """Exact min-sum transfer DP for clique layers joined by matchings."""

    if not 2 <= layer_width <= 16 or len(between_layers) + 1 != len(within_layers):
        raise ValueError("invalid layered Ising profile")
    state_count = 1 << layer_width
    layer_energies = [_ising_layer_energy(layer_width, factors) for factors in within_layers]
    scores = layer_energies[0]
    predecessors: list[list[int]] = []
    for layer_index, matching in enumerate(between_layers):
        if len(matching) != layer_width:
            raise ValueError("adjacent Ising layers must form one perfect matching")
        left_positions = {factor[0] for factor in matching}
        right_positions = {factor[1] for factor in matching}
        if left_positions != set(range(layer_width)) or right_positions != set(range(layer_width)):
            raise ValueError("invalid inter-layer matching")

        transformed = scores.copy()
        arguments = list(range(state_count))
        right_of_left: list[int] = [0] * layer_width
        for left, right, preferred_parity, weight in matching:
            right_of_left[left] = right
            bit = 1 << left
            next_scores = [0] * state_count
            next_arguments = [0] * state_count
            penalty_00 = weight if preferred_parity else 0
            penalty_10 = 0 if preferred_parity else weight
            penalty_01 = penalty_10
            penalty_11 = penalty_00
            for base in range(state_count):
                if base & bit:
                    continue
                zero = transformed[base]
                one = transformed[base | bit]
                if zero + penalty_00 <= one + penalty_10:
                    next_scores[base] = zero + penalty_00
                    next_arguments[base] = arguments[base]
                else:
                    next_scores[base] = one + penalty_10
                    next_arguments[base] = arguments[base | bit]
                if zero + penalty_01 <= one + penalty_11:
                    next_scores[base | bit] = zero + penalty_01
                    next_arguments[base | bit] = arguments[base]
                else:
                    next_scores[base | bit] = one + penalty_11
                    next_arguments[base | bit] = arguments[base | bit]
            transformed = next_scores
            arguments = next_arguments

        next_scores = [0] * state_count
        parents = [0] * state_count
        energy = layer_energies[layer_index + 1]
        for current_mask in range(state_count):
            matching_mask = 0
            for left, right in enumerate(right_of_left):
                matching_mask |= ((current_mask >> right) & 1) << left
            next_scores[current_mask] = transformed[matching_mask] + energy[current_mask]
            parents[current_mask] = arguments[matching_mask]
        predecessors.append(parents)
        scores = next_scores

    state = min(range(state_count), key=scores.__getitem__)
    optimum = scores[state]
    layer_states = [0] * len(within_layers)
    layer_states[-1] = state
    for layer_index in range(len(within_layers) - 1, 0, -1):
        state = predecessors[layer_index - 1][state]
        layer_states[layer_index - 1] = state
    assignment = tuple(
        bool((state_mask >> position) & 1)
        for state_mask in layer_states
        for position in range(layer_width)
    )
    return assignment, optimum


def solve_public_layered_ising(
    public_instance: Mapping[str, Any],
) -> tuple[list[int], int]:
    """Recover hidden clique layers and solve C06 using public clauses only."""

    groups: dict[tuple[int, int, int], list[list[int]]] = {}
    for clause in public_instance["soft_clauses"]:
        literals = clause["literals"]
        if len(literals) != 2:
            raise ValueError("layered Ising reference expects binary soft clauses")
        variables = tuple(sorted(abs(literal) for literal in literals))
        groups.setdefault((*variables, clause["weight"]), []).append(literals)

    factors: list[tuple[int, int, bool, int]] = []
    adjacency: dict[int, set[int]] = {}
    for (left, right, weight), clauses in groups.items():
        if len(clauses) != 2:
            raise ValueError("each Ising factor must contain two weighted clauses")
        costs: dict[int, int] = {}
        for parity in (0, 1):
            values = (False, bool(parity))
            unsatisfied = sum(
                not any(
                    values[0 if abs(literal) == left else 1] == (literal > 0) for literal in clause
                )
                for clause in clauses
            )
            costs[parity] = unsatisfied * weight
        preferred = min(costs, key=costs.__getitem__)
        if costs[preferred] != 0 or costs[1 - preferred] != weight:
            raise ValueError("invalid paired-clause Ising factor")
        factors.append((left, right, bool(preferred), weight))
        adjacency.setdefault(left, set()).add(right)
        adjacency.setdefault(right, set()).add(left)

    common_counts = {
        (left, right): len(adjacency[left] & adjacency[right])
        for left, right, _preferred, _weight in factors
    }
    max_common = max(common_counts.values())
    layer_width = max_common + 2
    within_edges = {
        (left, right)
        for left, right, _preferred, _weight in factors
        if common_counts[(left, right)] == max_common
    }
    within_adjacency: dict[int, set[int]] = {variable: set() for variable in adjacency}
    for left, right in within_edges:
        within_adjacency[left].add(right)
        within_adjacency[right].add(left)
    components: list[list[int]] = []
    component_of: dict[int, int] = {}
    unseen = set(within_adjacency)
    while unseen:
        root = unseen.pop()
        component = {root}
        queue: deque[int] = deque([root])
        while queue:
            variable = queue.popleft()
            for neighbor in within_adjacency[variable]:
                if neighbor in unseen:
                    unseen.remove(neighbor)
                    component.add(neighbor)
                    queue.append(neighbor)
        ordered = sorted(component)
        if len(ordered) != layer_width:
            raise ValueError("within-layer factors do not form equal cliques")
        component_index = len(components)
        components.append(ordered)
        component_of.update({variable: component_index for variable in ordered})

    component_adjacency: list[set[int]] = [set() for _ in components]
    for left, right, _preferred, _weight in factors:
        left_component = component_of[left]
        right_component = component_of[right]
        if left_component != right_component:
            component_adjacency[left_component].add(right_component)
            component_adjacency[right_component].add(left_component)
    endpoints = [
        index for index, neighbors in enumerate(component_adjacency) if len(neighbors) == 1
    ]
    if len(endpoints) != 2:
        raise ValueError("Ising component quotient is not one path")
    order = [endpoints[0]]
    previous = -1
    while len(order) < len(components):
        candidates = component_adjacency[order[-1]] - {previous}
        if len(candidates) != 1:
            raise ValueError("Ising layer path is ambiguous")
        previous, current = order[-1], next(iter(candidates))
        order.append(current)

    position_maps = [
        {variable: position for position, variable in enumerate(components[index])}
        for index in order
    ]
    ordered_component = {component: layer for layer, component in enumerate(order)}
    within_layers: list[list[IsingFactor]] = [[] for _ in order]
    between_layers: list[list[IsingFactor]] = [[] for _ in range(len(order) - 1)]
    for left, right, preferred, weight in factors:
        left_component = component_of[left]
        right_component = component_of[right]
        left_layer = ordered_component[left_component]
        right_layer = ordered_component[right_component]
        if left_layer == right_layer:
            positions = position_maps[left_layer]
            first, second = sorted((positions[left], positions[right]))
            within_layers[left_layer].append((first, second, preferred, weight))
        else:
            if abs(left_layer - right_layer) != 1:
                raise ValueError("factor skips an Ising layer")
            if left_layer > right_layer:
                left, right = right, left
                left_layer, right_layer = right_layer, left_layer
            between_layers[left_layer].append(
                (
                    position_maps[left_layer][left],
                    position_maps[right_layer][right],
                    preferred,
                    weight,
                )
            )

    logical_assignment, optimum = solve_layered_ising(
        layer_width=layer_width,
        within_layers=within_layers,
        between_layers=between_layers,
    )
    public_assignment = [0] * public_instance["num_variables"]
    for layer, component in enumerate(order):
        for position, variable in enumerate(components[component]):
            public_assignment[variable - 1] = int(
                logical_assignment[layer * layer_width + position]
            )
    return public_assignment, optimum


def solve_parity_components(
    *, num_free_variables: int, factors: Sequence[ParityFactor]
) -> tuple[tuple[bool, ...], int]:
    """Optimize weighted affine-parity factors component by component."""

    variable_factors: list[list[int]] = [[] for _ in range(num_free_variables + 1)]
    for factor_index, (variables, _rhs, _prefer_true, weight) in enumerate(factors):
        if weight <= 0 or len(variables) < 1 or len(set(variables)) != len(variables):
            raise ValueError("invalid parity factor")
        for variable in variables:
            if not 1 <= variable <= num_free_variables:
                raise ValueError("parity factor variable outside free range")
            variable_factors[variable].append(factor_index)

    assignment = [False] * num_free_variables
    total_cost = 0
    unseen = set(range(1, num_free_variables + 1))
    while unseen:
        root = next(iter(unseen))
        component_variables: set[int] = {root}
        component_factors: set[int] = set()
        queue: deque[int] = deque([root])
        unseen.remove(root)
        while queue:
            variable = queue.popleft()
            for factor_index in variable_factors[variable]:
                component_factors.add(factor_index)
                for neighbor in factors[factor_index][0]:
                    if neighbor in unseen:
                        unseen.remove(neighbor)
                        component_variables.add(neighbor)
                        queue.append(neighbor)
        ordered_variables = sorted(component_variables)
        if len(ordered_variables) > 24:
            raise ValueError("parity component exceeds exact reference width")
        local_of = {variable: index for index, variable in enumerate(ordered_variables)}
        ordered_factors = sorted(component_factors)
        incidence: list[list[int]] = [[] for _ in ordered_variables]
        values: list[bool] = []
        weights: list[int] = []
        preferences: list[bool] = []
        current_cost = 0
        for local_factor, factor_index in enumerate(ordered_factors):
            variables, rhs, prefer_true, weight = factors[factor_index]
            values.append(rhs)
            weights.append(weight)
            preferences.append(prefer_true)
            if rhs != prefer_true:
                current_cost += weight
            for variable in variables:
                incidence[local_of[variable]].append(local_factor)
        best_cost = current_cost
        best_gray = 0
        gray = 0
        for counter in range(1, 1 << len(ordered_variables)):
            flipped = (counter & -counter).bit_length() - 1
            gray ^= 1 << flipped
            for local_factor in incidence[flipped]:
                if values[local_factor] == preferences[local_factor]:
                    current_cost += weights[local_factor]
                else:
                    current_cost -= weights[local_factor]
                values[local_factor] = not values[local_factor]
            if current_cost < best_cost:
                best_cost = current_cost
                best_gray = gray
        for local, variable in enumerate(ordered_variables):
            assignment[variable - 1] = bool((best_gray >> local) & 1)
        total_cost += best_cost
    return tuple(assignment), total_cost


def solve_public_parity_components(
    public_instance: Mapping[str, Any],
) -> tuple[list[int], int]:
    """Recover C05 XOR gadgets and optimize every public factor component."""

    groups: dict[tuple[int, int, int], list[list[int]]] = {}
    for clause in public_instance["hard_clauses"]:
        literals = clause["literals"]
        if len(literals) != 3:
            raise ValueError("parity reference expects ternary hard clauses")
        key = tuple(sorted(abs(literal) for literal in literals))
        groups.setdefault(key, []).append(literals)

    equations: list[tuple[tuple[int, int, int], bool]] = []
    variable_equations: dict[int, list[int]] = {}
    for variables, clauses in groups.items():
        if len(clauses) != 4:
            raise ValueError("each XOR gate must contain four clauses")
        forbidden_parities = {sum(literal < 0 for literal in literals) % 2 for literals in clauses}
        if len(forbidden_parities) != 1 or len({tuple(sorted(item)) for item in clauses}) != 4:
            raise ValueError("invalid complete XOR truth table")
        rhs = not bool(next(iter(forbidden_parities)))
        equation_index = len(equations)
        equations.append((variables, rhs))
        for variable in variables:
            variable_equations.setdefault(variable, []).append(equation_index)

    soft_by_output: dict[int, tuple[bool, int]] = {}
    for clause in public_instance["soft_clauses"]:
        literals = clause["literals"]
        if len(literals) != 1:
            raise ValueError("parity reference expects weighted unit outputs")
        literal = literals[0]
        soft_by_output[abs(literal)] = (literal > 0, clause["weight"])

    outputs = set(soft_by_output)
    intermediates = {
        variable
        for variable, memberships in variable_equations.items()
        if variable not in outputs and len(memberships) == 2
    }
    free_variables = sorted(set(variable_equations) - outputs - intermediates)
    compact_of = {variable: index + 1 for index, variable in enumerate(free_variables)}
    factors: list[ParityFactor] = []
    gate_records: list[tuple[int, int, int, int, int, bool, bool]] = []
    for output, (prefer_true, weight) in soft_by_output.items():
        memberships = variable_equations.get(output)
        if memberships is None or len(memberships) != 1:
            raise ValueError("each weighted output must belong to one XOR gate")
        second_equation = memberships[0]
        second_variables, second_rhs = equations[second_equation]
        middle_candidates = [
            variable
            for variable in second_variables
            if variable != output and variable in intermediates
        ]
        if len(middle_candidates) != 1:
            raise ValueError("weighted output does not expose one intermediate")
        middle = middle_candidates[0]
        third = next(variable for variable in second_variables if variable not in {output, middle})
        first_equation = next(
            index for index in variable_equations[middle] if index != second_equation
        )
        first_variables, first_rhs = equations[first_equation]
        first_inputs = [variable for variable in first_variables if variable != middle]
        if len(first_inputs) != 2 or any(
            variable not in compact_of for variable in [*first_inputs, third]
        ):
            raise ValueError("XOR chain inputs are not free variables")
        factor_variables = tuple(compact_of[variable] for variable in [*first_inputs, third])
        factors.append((factor_variables, first_rhs ^ second_rhs, prefer_true, weight))
        gate_records.append(
            (
                first_inputs[0],
                first_inputs[1],
                third,
                middle,
                output,
                first_rhs,
                second_rhs,
            )
        )

    compact_assignment, optimum = solve_parity_components(
        num_free_variables=len(free_variables), factors=factors
    )
    assignment = [0] * public_instance["num_variables"]
    for variable, compact in compact_of.items():
        assignment[variable - 1] = int(compact_assignment[compact - 1])
    for first, second, third, middle, output, first_rhs, second_rhs in gate_records:
        middle_value = bool(assignment[first - 1]) ^ bool(assignment[second - 1]) ^ first_rhs
        output_value = middle_value ^ bool(assignment[third - 1]) ^ second_rhs
        assignment[middle - 1] = int(middle_value)
        assignment[output - 1] = int(output_value)
    return assignment, optimum


def solve_implication_closure(
    *,
    num_variables: int,
    implications: Sequence[tuple[int, int]],
    preferences: Sequence[tuple[int, bool, int]],
) -> tuple[tuple[bool, ...], int]:
    """Solve weighted successor-closure through an exact integer minimum cut."""

    profits = [0] * num_variables
    for variable, prefer_true, weight in preferences:
        if not 1 <= variable <= num_variables or weight <= 0:
            raise ValueError("invalid closure preference")
        if prefer_true:
            profits[variable - 1] += weight
        else:
            profits[variable - 1] -= weight

    infinite_capacity = sum(abs(profit) for profit in profits) + 1
    source = num_variables
    sink = num_variables + 1
    edges: list[dict[str, int]] = []

    def add_edge(tail: int, head: int, capacity: int) -> None:
        edges.append(
            {
                "edge_id": len(edges),
                "tail": tail,
                "head": head,
                "capacity": capacity,
            }
        )

    for index, profit in enumerate(profits):
        if profit > 0:
            add_edge(source, index, profit)
        elif profit < 0:
            add_edge(index, sink, -profit)
    for antecedent, consequent in implications:
        if not 1 <= antecedent <= num_variables or not 1 <= consequent <= num_variables:
            raise ValueError("invalid closure implication")
        add_edge(antecedent - 1, consequent - 1, infinite_capacity)

    certificate = solve_maxflow(
        {
            "format_version": "aip-maxflow-instance/1",
            "directed": True,
            "num_vertices": num_variables + 2,
            "source": source,
            "sink": sink,
            "edges": edges,
        }
    )
    flow_value = certificate["flow_value"]
    if not isinstance(flow_value, int) or flow_value >= infinite_capacity:
        raise AssertionError("closure reference cut crossed an implication edge")
    source_side = set(certificate["source_side_cut"])
    assignment = tuple(index in source_side for index in range(num_variables))
    return assignment, flow_value


def solve_public_implication_closure(
    public_instance: Mapping[str, Any],
) -> tuple[list[int], int]:
    """Decode signed binary implications and solve using public data only."""

    num_variables = public_instance["num_variables"]
    if not isinstance(num_variables, int) or num_variables < 1:
        raise ValueError("invalid variable count")
    hard_clauses = public_instance["hard_clauses"]
    soft_clauses = public_instance["soft_clauses"]

    parity_graph: list[list[tuple[int, int]]] = [[] for _ in range(num_variables)]
    parsed_hard: list[tuple[int, int]] = []
    for clause in hard_clauses:
        literals = clause["literals"]
        if not isinstance(literals, list) or len(literals) != 2:
            raise ValueError("reference expects binary hard clauses")
        left, right = literals
        left_variable = abs(left) - 1
        right_variable = abs(right) - 1
        parity = 1 ^ int(left > 0) ^ int(right > 0)
        parity_graph[left_variable].append((right_variable, parity))
        parity_graph[right_variable].append((left_variable, parity))
        parsed_hard.append((left, right))

    complements: list[int | None] = [None] * num_variables
    for root in range(num_variables):
        if complements[root] is not None:
            continue
        complements[root] = 0
        queue: deque[int] = deque([root])
        while queue:
            variable = queue.popleft()
            for neighbor, parity in parity_graph[variable]:
                required = complements[variable] ^ parity
                if complements[neighbor] is None:
                    complements[neighbor] = required
                    queue.append(neighbor)
                elif complements[neighbor] != required:
                    raise ValueError("hard clauses are not a switched implication graph")

    implications: list[tuple[int, int]] = []
    for left, right in parsed_hard:
        normalized = []
        for literal in (left, right):
            variable = abs(literal)
            positive = int(literal > 0) ^ complements[variable - 1]
            normalized.append(variable if positive else -variable)
        negative = [literal for literal in normalized if literal < 0]
        positive = [literal for literal in normalized if literal > 0]
        if len(negative) != 1 or len(positive) != 1:
            raise ValueError("hard clause cannot be normalized as one implication")
        implications.append((-negative[0], positive[0]))

    preferences: list[tuple[int, bool, int]] = []
    for clause in soft_clauses:
        literals = clause["literals"]
        if not isinstance(literals, list) or len(literals) != 1:
            raise ValueError("reference expects weighted unit soft clauses")
        literal = literals[0]
        variable = abs(literal)
        prefer_true = bool(int(literal > 0) ^ complements[variable - 1])
        preferences.append((variable, prefer_true, clause["weight"]))

    normalized_assignment, optimum = solve_implication_closure(
        num_variables=num_variables,
        implications=implications,
        preferences=preferences,
    )
    public_assignment = [
        int(value ^ bool(complements[index])) for index, value in enumerate(normalized_assignment)
    ]
    return public_assignment, optimum


def solve_public_gadget_closure(
    public_instance: Mapping[str, Any],
) -> tuple[list[int], int]:
    """Eliminate the C04 local gates, then solve the recovered closure exactly."""

    num_variables = public_instance["num_variables"]
    hard_clauses = public_instance["hard_clauses"]
    unit_clauses = [clause for clause in hard_clauses if len(clause["literals"]) == 1]
    if len(unit_clauses) != 1:
        raise ValueError("gadget closure must have one hidden constant unit")
    constant_literal = unit_clauses[0]["literals"][0]
    constant_variable = abs(constant_literal)
    constant_value = constant_literal > 0

    remaining_variables = [
        variable for variable in range(1, num_variables + 1) if variable != constant_variable
    ]
    compact_of = {
        public_variable: compact + 1 for compact, public_variable in enumerate(remaining_variables)
    }

    def simplify_literal(literal: int) -> int:
        compact = compact_of[abs(literal)]
        return compact if literal > 0 else -compact

    simplified_hard: list[dict[str, Any]] = []
    for clause in hard_clauses:
        literals = clause["literals"]
        if len(literals) == 1:
            continue
        retained: list[int] = []
        satisfied = False
        for literal in literals:
            if abs(literal) == constant_variable:
                if constant_value == (literal > 0):
                    satisfied = True
                    break
            else:
                retained.append(simplify_literal(literal))
        if satisfied:
            continue
        if len(retained) != 2:
            raise ValueError("gadget elimination did not produce a binary closure clause")
        simplified_hard.append({"clause_id": clause["clause_id"], "literals": retained})

    simplified_soft: list[dict[str, Any]] = []
    for clause in public_instance["soft_clauses"]:
        literals = clause["literals"]
        if len(literals) != 1 or abs(literals[0]) == constant_variable:
            raise ValueError("gadget closure expects one preference per core variable")
        simplified_soft.append(
            {
                "clause_id": clause["clause_id"],
                "literals": [simplify_literal(literals[0])],
                "weight": clause["weight"],
            }
        )

    compact_assignment, optimum = solve_public_implication_closure(
        {
            "num_variables": len(remaining_variables),
            "hard_clauses": simplified_hard,
            "soft_clauses": simplified_soft,
        }
    )
    public_assignment = [0] * num_variables
    public_assignment[constant_variable - 1] = int(constant_value)
    for public_variable, compact in compact_of.items():
        public_assignment[public_variable - 1] = compact_assignment[compact - 1]
    return public_assignment, optimum


__all__ = [
    "solve_implication_closure",
    "solve_layered_ising",
    "solve_parity_components",
    "solve_public_gadget_closure",
    "solve_public_implication_closure",
    "solve_public_layered_ising",
    "solve_public_parity_components",
]
