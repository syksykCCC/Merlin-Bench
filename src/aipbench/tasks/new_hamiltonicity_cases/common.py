"""Scaled graph builders for the new Hamiltonicity task."""

from __future__ import annotations

from collections.abc import Mapping
from itertools import combinations
from typing import Any, Final

from aipbench.tasks.shared.hamiltonicity_bind_open_cases.c03 import _euler_edge_order
from aipbench.tasks.shared.hamiltonicity_bind_open_cases.c06 import reflected_combinations
from aipbench.tasks.shared.hamiltonicity_bind_open_cases.common import (
    DeterministicStream,
    GraphBlueprint,
    LogicalGraph,
    integer_parameter,
    normalized_edges,
    validate_hamilton_cycle,
)

CASE_DEFAULTS: Final[Mapping[str, Mapping[str, Any]]] = {
    "c01": {"num_vertices": 1_000},
    "c02": {"part_size": 128},
    "c03": {"num_variables": 64, "num_clauses": 272},
    "c04": {"num_variables": 80, "num_equations": 80},
    "c05": {"num_variables": 40, "num_clauses": 320},
    "c06": {"num_variables": 160},
    "c07": {"num_variables": 23, "num_equations": 23},
}


def _sample_distinct(stream: DeterministicStream, count: int, upper: int) -> tuple[int, ...]:
    """Sample ``count`` distinct integers without depending on set iteration order."""

    values: list[int] = []
    while len(values) < count:
        candidate = stream.randbelow(upper)
        if candidate not in values:
            values.append(candidate)
    return tuple(values)


def _quiet_planted_clauses(
    stream: DeterministicStream,
    *,
    num_variables: int,
    num_clauses: int,
    assignment: tuple[bool, ...],
) -> tuple[tuple[tuple[int, bool], ...], ...]:
    """Generate a sign-balanced planted 3-CNF with no duplicate clauses.

    A quarter of clauses have three planted-true literals and the remainder have
    exactly one.  Thus every literal position is planted-true with probability
    one half; the public signs do not carry the majority bias of naive planting.
    """

    clauses: list[tuple[tuple[int, bool], ...]] = []
    seen: set[tuple[tuple[int, bool], ...]] = set()
    while len(clauses) < num_clauses:
        variables = _sample_distinct(stream, 3, num_variables)
        satisfied_position = stream.randbelow(4)
        literals = tuple(
            (
                variable,
                assignment[variable]
                == (satisfied_position == 0 or index == satisfied_position - 1),
            )
            for index, variable in enumerate(variables)
        )
        canonical = tuple(sorted(literals))
        if canonical in seen:
            continue
        seen.add(canonical)
        clauses.append(literals)
    return tuple(clauses)


def _lift_directed_cycle(
    *,
    num_directed_vertices: int,
    arcs: set[tuple[int, int]],
    directed_cycle: tuple[int, ...],
    metadata: Mapping[str, Any],
) -> GraphBlueprint:
    """Apply the standard forced three-vertex directed-to-undirected lift."""

    if len(directed_cycle) != num_directed_vertices or set(directed_cycle) != set(
        range(num_directed_vertices)
    ):
        raise ValueError("directed witness must visit every logical vertex exactly once")
    for index, source in enumerate(directed_cycle):
        target = directed_cycle[(index + 1) % len(directed_cycle)]
        if (source, target) not in arcs:
            raise ValueError("directed witness uses a missing arc")

    def incoming(vertex: int) -> int:
        return 3 * vertex

    def middle(vertex: int) -> int:
        return 3 * vertex + 1

    def outgoing(vertex: int) -> int:
        return 3 * vertex + 2

    edges = [
        edge
        for vertex in range(num_directed_vertices)
        for edge in (
            (incoming(vertex), middle(vertex)),
            (middle(vertex), outgoing(vertex)),
        )
    ]
    edges.extend((outgoing(source), incoming(target)) for source, target in arcs)
    cycle = tuple(
        lifted
        for vertex in directed_cycle
        for lifted in (incoming(vertex), middle(vertex), outgoing(vertex))
    )
    graph = LogicalGraph(
        3 * num_directed_vertices,
        normalized_edges(3 * num_directed_vertices, edges),
    )
    validate_hamilton_cycle(graph, cycle)
    return GraphBlueprint(graph, cycle, metadata)


def _quiet_planted_3sat_lift(
    stream: DeterministicStream, parameters: Mapping[str, Any]
) -> GraphBlueprint:
    """A Hamiltonian lift whose intended traversals encode a planted 3-CNF."""

    num_variables = integer_parameter(parameters, "num_variables", minimum=16, maximum=128)
    num_clauses = integer_parameter(parameters, "num_clauses", minimum=64, maximum=340)
    assignment = tuple(bool(stream.randbelow(2)) for _ in range(num_variables))
    clauses = _quiet_planted_clauses(
        stream,
        num_variables=num_variables,
        num_clauses=num_clauses,
        assignment=assignment,
    )

    return _cnf_lift_from_witness(
        clauses=clauses,
        assignment=assignment,
        metadata={
            "mathematical_family": "quiet_planted_3cnf_directed_lift",
            "num_variables": num_variables,
            "num_clauses": num_clauses,
        },
    )


def _cnf_lift_from_witness(
    *,
    clauses: tuple[tuple[tuple[int, bool], ...], ...],
    assignment: tuple[bool, ...],
    metadata: Mapping[str, Any],
) -> GraphBlueprint:
    """Reduce a witnessed CNF to directed Hamiltonicity and apply the 3-lift."""

    num_variables = len(assignment)
    num_clauses = len(clauses)
    occurrences: list[list[tuple[int, bool]]] = [[] for _ in range(num_variables)]
    for clause_id, clause in enumerate(clauses):
        for variable, positive in clause:
            occurrences[variable].append((clause_id, positive))
    if any(not variable_occurrences for variable_occurrences in occurrences):
        raise ValueError("sampled formula leaves an unused variable")

    next_vertex = 0
    rows: list[tuple[int, ...]] = []
    for variable_occurrences in occurrences:
        row = tuple(range(next_vertex, next_vertex + len(variable_occurrences) + 1))
        next_vertex += len(row)
        rows.append(row)
    clause_vertices = tuple(range(next_vertex, next_vertex + num_clauses))
    next_vertex += num_clauses
    source = next_vertex
    sink = next_vertex + 1
    num_directed_vertices = next_vertex + 2

    arcs: set[tuple[int, int]] = set()
    for variable, row in enumerate(rows):
        for slot, (clause_id, positive) in enumerate(occurrences[variable]):
            left, right = row[slot], row[slot + 1]
            arcs.add((left, right))
            arcs.add((right, left))
            clause_vertex = clause_vertices[clause_id]
            if positive:
                arcs.add((left, clause_vertex))
                arcs.add((clause_vertex, right))
            else:
                arcs.add((right, clause_vertex))
                arcs.add((clause_vertex, left))

    arcs.update((source, endpoint) for endpoint in (rows[0][0], rows[0][-1]))
    for first, second in zip(rows, rows[1:], strict=False):
        arcs.update(
            (exit_vertex, entry_vertex)
            for exit_vertex in (first[0], first[-1])
            for entry_vertex in (second[0], second[-1])
        )
    arcs.update((endpoint, sink) for endpoint in (rows[-1][0], rows[-1][-1]))
    arcs.add((sink, source))

    chosen_occurrence: dict[int, tuple[int, int]] = {}
    for clause_id, clause in enumerate(clauses):
        for variable, positive in clause:
            if positive == assignment[variable]:
                chosen_occurrence[clause_id] = (
                    variable,
                    occurrences[variable].index((clause_id, positive)),
                )
                break
    if len(chosen_occurrence) != num_clauses:
        raise ValueError("planted assignment does not satisfy every clause")

    directed_order: list[int] = [source]
    for variable, row in enumerate(rows):
        slots = range(len(row) - 1) if assignment[variable] else range(len(row) - 2, -1, -1)
        directed_order.append(row[0] if assignment[variable] else row[-1])
        for slot in slots:
            occurrence = occurrences[variable][slot]
            if chosen_occurrence.get(occurrence[0]) == (variable, slot):
                directed_order.append(clause_vertices[occurrence[0]])
            directed_order.append(row[slot + 1] if assignment[variable] else row[slot])
    directed_order.append(sink)

    return _lift_directed_cycle(
        num_directed_vertices=num_directed_vertices,
        arcs=arcs,
        directed_cycle=tuple(directed_order),
        metadata={**metadata, "logical_directed_vertices": num_directed_vertices},
    )


def _gf2_rank(rows: list[int]) -> int:
    """Return the rank of bit-packed rows over GF(2)."""

    basis: dict[int, int] = {}
    for row in rows:
        reduced = row
        while reduced:
            pivot = reduced.bit_length() - 1
            if pivot not in basis:
                basis[pivot] = reduced
                break
            reduced ^= basis[pivot]
    return len(basis)


def _affine_parity_lift(
    stream: DeterministicStream, parameters: Mapping[str, Any]
) -> GraphBlueprint:
    """Encode a full-rank sparse affine GF(2) system through grouped 3-CNF."""

    num_variables = integer_parameter(parameters, "num_variables", minimum=16, maximum=96)
    num_equations = integer_parameter(
        parameters, "num_equations", minimum=num_variables, maximum=num_variables
    )
    assignment = tuple(bool(stream.randbelow(2)) for _ in range(num_variables))

    column_permutation = list(range(num_variables))
    row_permutation = list(range(num_equations))
    stream.shuffle(column_permutation)
    stream.shuffle(row_permutation)
    equation_variables = [
        tuple(sorted(column_permutation[(row + offset) % num_variables] for offset in (0, 1, 2)))
        for row in row_permutation
    ]
    masks = [sum(1 << variable for variable in triple) for triple in equation_variables]
    if _gf2_rank(masks) != num_variables:
        raise ValueError("the sparse parity template unexpectedly lost rank")

    clauses: list[tuple[tuple[int, bool], ...]] = []
    for variables in equation_variables:
        right_hand_side = sum(assignment[variable] for variable in variables) % 2
        for forbidden_bits in range(8):
            if forbidden_bits.bit_count() % 2 == right_hand_side:
                continue
            clauses.append(
                tuple(
                    (variable, not bool(forbidden_bits >> index & 1))
                    for index, variable in enumerate(variables)
                )
            )

    return _cnf_lift_from_witness(
        clauses=tuple(clauses),
        assignment=assignment,
        metadata={
            "mathematical_family": "full_rank_affine_parity_cnf_directed_lift",
            "num_variables": num_variables,
            "num_equations": num_equations,
            "num_clauses": len(clauses),
        },
    )


def _biased_planted_3sat_lift(
    stream: DeterministicStream, parameters: Mapping[str, Any]
) -> GraphBlueprint:
    """A dense-occurrence planted CNF whose hidden assignment has a weak signal."""

    num_variables = integer_parameter(parameters, "num_variables", minimum=16, maximum=96)
    num_clauses = integer_parameter(parameters, "num_clauses", minimum=64, maximum=330)
    if 3 * num_clauses < 12 * num_variables:
        raise ValueError("biased planted profile needs at least twelve occurrences per variable")
    assignment = tuple(bool(stream.randbelow(2)) for _ in range(num_variables))
    clauses: list[tuple[tuple[int, bool], ...]] = []
    seen: set[tuple[tuple[int, bool], ...]] = set()
    while len(clauses) < num_clauses:
        variables = _sample_distinct(stream, 3, num_variables)
        # Seven eighths of clauses have two planted-true literals; the remainder
        # have one.  Across the frozen profile this gives a useful but noisy
        # literal-frequency estimator rather than directly publishing a witness.
        true_count = 1 if stream.randbelow(8) == 0 else 2
        positions = list(range(3))
        stream.shuffle(positions)
        true_positions = set(positions[:true_count])
        clause = tuple(
            (variable, assignment[variable] == (index in true_positions))
            for index, variable in enumerate(variables)
        )
        canonical = tuple(sorted(clause))
        if canonical in seen:
            continue
        seen.add(canonical)
        clauses.append(clause)

    blueprint = _cnf_lift_from_witness(
        clauses=tuple(clauses),
        assignment=assignment,
        metadata={
            "mathematical_family": "weakly_biased_planted_3cnf_directed_lift",
            "num_variables": num_variables,
            "num_clauses": num_clauses,
            "planted_true_literal_probability": "5/8",
        },
    )
    if blueprint.graph.num_vertices > 4_096:
        raise ValueError("biased planted lift exceeds the vertex envelope")
    return blueprint


def _implication_ring_lift(
    stream: DeterministicStream, parameters: Mapping[str, Any]
) -> GraphBlueprint:
    """Lift a uniquely witnessed 2-CNF implication ring to Hamiltonicity."""

    num_variables = integer_parameter(parameters, "num_variables", minimum=32, maximum=190)
    assignment = tuple(bool(stream.randbelow(2)) for _ in range(num_variables))
    ring_order = list(range(num_variables))
    stream.shuffle(ring_order)
    clauses: list[tuple[tuple[int, bool], ...]] = []
    for index, first in enumerate(ring_order):
        second = ring_order[(index + 1) % num_variables]
        if assignment[first] == assignment[second]:
            clauses.extend(
                (
                    ((first, False), (second, True)),
                    ((first, True), (second, False)),
                )
            )
        else:
            clauses.extend(
                (
                    ((first, True), (second, True)),
                    ((first, False), (second, False)),
                )
            )
    anchor = ring_order[0]
    clauses.append(((anchor, assignment[anchor]),))

    blueprint = _cnf_lift_from_witness(
        clauses=tuple(clauses),
        assignment=assignment,
        metadata={
            "mathematical_family": "anchored_2cnf_implication_ring_directed_lift",
            "num_variables": num_variables,
            "num_clauses": len(clauses),
            "binary_clauses": 2 * num_variables,
            "unit_clauses": 1,
        },
    )
    if blueprint.graph.num_vertices > 4_096:
        raise ValueError("implication-ring lift exceeds the vertex envelope")
    return blueprint


def _forbid_boolean_row(
    variables: tuple[int, ...], values: tuple[bool, ...]
) -> tuple[tuple[int, bool], ...]:
    """Return the clause that is false on exactly the specified local row."""

    return tuple((variable, not value) for variable, value in zip(variables, values, strict=True))


def _xor_gate_clauses(
    first: int, second: int, output: int
) -> tuple[tuple[tuple[int, bool], ...], ...]:
    """Four 3-clauses encoding ``output = first XOR second`` exactly."""

    variables = (first, second, output)
    return tuple(
        _forbid_boolean_row(variables, values)
        for values in (
            (False, False, True),
            (False, True, False),
            (True, False, False),
            (True, True, True),
        )
    )


def _xor_relation_clauses(
    first: int, second: int, right_hand_side: bool
) -> tuple[tuple[tuple[int, bool], ...], ...]:
    """Two binary clauses encoding ``first XOR second = right_hand_side``."""

    variables = (first, second)
    return tuple(
        _forbid_boolean_row(variables, values)
        for values in ((False, False), (True, True))
        if (values[0] ^ values[1]) != right_hand_side
    ) + tuple(
        _forbid_boolean_row(variables, values)
        for values in ((False, True), (True, False))
        if (values[0] ^ values[1]) != right_hand_side
    )


def _cloaked_dense_xor_lift(
    stream: DeterministicStream, parameters: Mapping[str, Any]
) -> GraphBlueprint:
    """Hide a full-rank five-XOR system behind auxiliary XOR gates and CNF."""

    num_variables = integer_parameter(parameters, "num_variables", minimum=11, maximum=23)
    num_equations = integer_parameter(
        parameters, "num_equations", minimum=num_variables, maximum=num_variables
    )
    column_permutation = list(range(num_variables))
    row_permutation = list(range(num_equations))
    stream.shuffle(column_permutation)
    stream.shuffle(row_permutation)
    equation_variables = [
        tuple(column_permutation[(row + offset) % num_variables] for offset in (0, 1, 2, 3, 4))
        for row in row_permutation
    ]
    masks = [sum(1 << variable for variable in row) for row in equation_variables]
    if _gf2_rank(masks) != num_variables:
        raise ValueError("the five-XOR circulant template unexpectedly lost rank")

    original_assignment = tuple(bool(stream.randbelow(2)) for _ in range(num_variables))
    full_assignment = list(original_assignment)
    clauses: list[tuple[tuple[int, bool], ...]] = []
    for variables in equation_variables:
        first_auxiliary = len(full_assignment)
        full_assignment.append(
            original_assignment[variables[0]] ^ original_assignment[variables[1]]
        )
        second_auxiliary = len(full_assignment)
        full_assignment.append(full_assignment[first_auxiliary] ^ original_assignment[variables[2]])
        third_auxiliary = len(full_assignment)
        full_assignment.append(
            full_assignment[second_auxiliary] ^ original_assignment[variables[3]]
        )
        clauses.extend(_xor_gate_clauses(variables[0], variables[1], first_auxiliary))
        clauses.extend(_xor_gate_clauses(first_auxiliary, variables[2], second_auxiliary))
        clauses.extend(_xor_gate_clauses(second_auxiliary, variables[3], third_auxiliary))
        right_hand_side = bool(sum(original_assignment[variable] for variable in variables) % 2)
        clauses.extend(_xor_relation_clauses(third_auxiliary, variables[4], right_hand_side))

    blueprint = _cnf_lift_from_witness(
        clauses=tuple(clauses),
        assignment=tuple(full_assignment),
        metadata={
            "mathematical_family": "auxiliary_cloaked_full_rank_five_xor_directed_lift",
            "original_variables": num_variables,
            "auxiliary_variables": len(full_assignment) - num_variables,
            "num_equations": num_equations,
            "num_clauses": len(clauses),
        },
    )
    if blueprint.graph.num_vertices > 4_096:
        raise ValueError("cloaked five-XOR lift exceeds the vertex envelope")
    return blueprint


def _wheel(parameters: Mapping[str, Any]) -> GraphBlueprint:
    n = integer_parameter(parameters, "num_vertices", minimum=100, maximum=4_096)
    edges = [(0, vertex) for vertex in range(1, n)]
    edges.extend((vertex, vertex + 1) for vertex in range(1, n - 1))
    edges.append((1, n - 1))
    graph = LogicalGraph(n, normalized_edges(n, edges))
    return GraphBlueprint(graph, tuple(range(n)), {"mathematical_family": "wheel"})


def _complete_bipartite(parameters: Mapping[str, Any]) -> GraphBlueprint:
    q = integer_parameter(parameters, "part_size", minimum=16, maximum=256)
    n = 2 * q
    edges = [(left, q + right) for left in range(q) for right in range(q)]
    cycle = tuple(vertex for index in range(q) for vertex in (index, q + index))
    return GraphBlueprint(
        LogicalGraph(n, normalized_edges(n, edges)),
        cycle,
        {"mathematical_family": "balanced_complete_bipartite", "part_size": q},
    )


def _line_graph(parameters: Mapping[str, Any]) -> GraphBlueprint:
    q = integer_parameter(parameters, "root_vertices", minimum=32, maximum=1_024)
    root_edges = normalized_edges(
        q,
        [(vertex, (vertex + step) % q) for vertex in range(q) for step in (1, 2, q - 2, q - 1)],
    )
    incidence: list[list[int]] = [[] for _ in range(q)]
    for edge_id, (first, second) in enumerate(root_edges):
        incidence[first].append(edge_id)
        incidence[second].append(edge_id)
    line_edges: set[tuple[int, int]] = set()
    for incident in incidence:
        for first, second in combinations(incident, 2):
            line_edges.add((min(first, second), max(first, second)))
    graph = LogicalGraph(len(root_edges), normalized_edges(len(root_edges), line_edges))
    return GraphBlueprint(
        graph,
        _euler_edge_order(q, root_edges),
        {
            "mathematical_family": "line_graph_of_even_degree_root",
            "root_vertices": q,
            "root_edges": len(root_edges),
        },
    )


def _cartesian_cycles(parameters: Mapping[str, Any]) -> GraphBlueprint:
    first_length = integer_parameter(parameters, "first_length", minimum=4, maximum=128)
    second_length = integer_parameter(parameters, "second_length", minimum=4, maximum=128)
    if first_length % 2:
        raise ValueError("first_length must be even")
    n = first_length * second_length
    if n > 4_096:
        raise ValueError("Cartesian product exceeds the vertex envelope")

    def vertex(first: int, second: int) -> int:
        return first * second_length + second

    edges = []
    for first in range(first_length):
        for second in range(second_length):
            edges.append((vertex(first, second), vertex((first + 1) % first_length, second)))
            edges.append((vertex(first, second), vertex(first, (second + 1) % second_length)))
    cycle = tuple(
        vertex(first, second)
        for first in range(first_length)
        for second in (range(second_length) if first % 2 == 0 else range(second_length - 1, -1, -1))
    )
    return GraphBlueprint(
        LogicalGraph(n, normalized_edges(n, edges)),
        cycle,
        {
            "mathematical_family": "cartesian_product_of_cycles",
            "factor_lengths": [first_length, second_length],
        },
    )


def _halin(parameters: Mapping[str, Any]) -> GraphBlueprint:
    branches = integer_parameter(parameters, "branches", minimum=4, maximum=512)
    leaves_per_branch = integer_parameter(parameters, "leaves_per_branch", minimum=3, maximum=8)
    root = 0
    internal = list(range(1, branches + 1))
    next_vertex = branches + 1
    branch_leaves: list[list[int]] = []
    leaves: list[int] = []
    edges: list[tuple[int, int]] = [(root, vertex) for vertex in internal]
    for branch in internal:
        current = list(range(next_vertex, next_vertex + leaves_per_branch))
        next_vertex += leaves_per_branch
        branch_leaves.append(current)
        leaves.extend(current)
        edges.extend((branch, leaf) for leaf in current)
    for index, leaf in enumerate(leaves):
        edges.append((leaf, leaves[(index + 1) % len(leaves)]))

    # Delete the outer edge from the last leaf of branch 0 to the first leaf of branch 1.
    # Traverse the complementary outer path; replace one within-branch outer edge for each
    # remaining internal vertex by a two-edge detour through that internal vertex.
    start = branch_leaves[0][-1]
    end = branch_leaves[1][0]
    leaf_position = {leaf: index for index, leaf in enumerate(leaves)}
    path = [start]
    cursor = (leaf_position[start] - 1) % len(leaves)
    while leaves[cursor] != end:
        path.append(leaves[cursor])
        cursor = (cursor - 1) % len(leaves)
    path.append(end)
    detour_edge = {
        frozenset((branch_leaves[index][1], branch_leaves[index][2])): internal[index]
        for index in range(2, branches)
    }
    expanded: list[int] = [path[0]]
    for first, second in zip(path, path[1:], strict=False):
        internal_vertex = detour_edge.get(frozenset((first, second)))
        if internal_vertex is not None:
            expanded.append(internal_vertex)
        expanded.append(second)
    cycle = (root, internal[0], *expanded, internal[1])
    graph = LogicalGraph(next_vertex, normalized_edges(next_vertex, edges))
    validate_hamilton_cycle(graph, cycle)
    return GraphBlueprint(
        graph,
        tuple(cycle),
        {
            "mathematical_family": "halin_graph",
            "tree_internal_vertices": branches + 1,
            "tree_leaves": len(leaves),
        },
    )


def _johnson(parameters: Mapping[str, Any]) -> GraphBlueprint:
    ground_size = integer_parameter(parameters, "ground_size", minimum=6, maximum=15)
    subset_size = integer_parameter(parameters, "subset_size", minimum=2, maximum=ground_size - 2)
    subsets = list(combinations(range(ground_size), subset_size))
    if len(subsets) > 4_096:
        raise ValueError("Johnson graph exceeds the vertex envelope")
    vertex_of = {subset: index for index, subset in enumerate(subsets)}
    edge_set: set[tuple[int, int]] = set()
    for subset_id, subset in enumerate(subsets):
        subset_set = set(subset)
        for removed in subset:
            for added in range(ground_size):
                if added in subset_set:
                    continue
                neighbor = tuple(sorted((subset_set - {removed}) | {added}))
                neighbor_id = vertex_of[neighbor]
                if subset_id < neighbor_id:
                    edge_set.add((subset_id, neighbor_id))
    gray = reflected_combinations(ground_size, subset_size)
    cycle = tuple(vertex_of[subset] for subset in gray)
    graph = LogicalGraph(len(subsets), normalized_edges(len(subsets), edge_set))
    validate_hamilton_cycle(graph, cycle)
    return GraphBlueprint(
        graph,
        cycle,
        {
            "mathematical_family": "johnson_graph",
            "ground_size": ground_size,
            "subset_size": subset_size,
        },
    )


def _planted_cubic(stream: DeterministicStream, parameters: Mapping[str, Any]) -> GraphBlueprint:
    n = integer_parameter(parameters, "num_vertices", minimum=100, maximum=4_096)
    if n % 2:
        raise ValueError("num_vertices must be even")
    cycle_edges = normalized_edges(n, [(vertex, (vertex + 1) % n) for vertex in range(n)])
    cycle_set = set(cycle_edges)
    matching: list[tuple[int, int]] | None = None
    for _ in range(256):
        order = list(range(n))
        stream.shuffle(order)
        candidate = [
            (min(order[index], order[index + 1]), max(order[index], order[index + 1]))
            for index in range(0, n, 2)
        ]
        if len(set(candidate)) == n // 2 and all(edge not in cycle_set for edge in candidate):
            matching = candidate
            break
    if matching is None:
        raise ValueError("failed to construct disjoint planted matching")
    return GraphBlueprint(
        LogicalGraph(n, normalized_edges(n, [*cycle_edges, *matching])),
        tuple(range(n)),
        {"mathematical_family": "planted_cubic_graph"},
    )


def build_case(
    case_id: str,
    stream: DeterministicStream,
    parameters: Mapping[str, Any],
) -> GraphBlueprint:
    if case_id == "c01":
        return _wheel(parameters)
    if case_id == "c02":
        return _complete_bipartite(parameters)
    if case_id == "c03":
        return _quiet_planted_3sat_lift(stream, parameters)
    if case_id == "c04":
        return _affine_parity_lift(stream, parameters)
    if case_id == "c05":
        return _biased_planted_3sat_lift(stream, parameters)
    if case_id == "c06":
        return _implication_ring_lift(stream, parameters)
    if case_id == "c07":
        return _cloaked_dense_xor_lift(stream, parameters)
    raise ValueError(f"unsupported new Hamiltonicity case: {case_id}")


__all__ = ["CASE_DEFAULTS", "build_case"]
