"""Independent 600-second Rooted Group Steiner Tree task."""

from __future__ import annotations

from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from aipbench.core.models import GeneratedCase
from aipbench.core.protocol import ParticipantClient, VirtualAgent
from aipbench.tasks.shared.group_steiner_cases.common import DeterministicStream
from aipbench.tasks.shared.rooted_group_steiner_tree import (
    EDGE_SET_EVENT_KIND,
    GroupSteinerProtocolState,
    GroupSteinerReason,
    RootedGroupSteinerProtocol,
    evaluate_edge_set,
)
from aipbench.tasks.shared.rooted_group_steiner_tree import (
    VIRTUAL_AGENTS as SHARED_VIRTUAL_AGENTS,
)

TASK_ID: Final = "t1.new_rooted_group_steiner_tree"
TASK_VERSION: Final = "0.1.0"
CASE_PARAMETERS: Final[Mapping[str, Mapping[str, int]]] = {
    "c01": {
        "branching_factor": 4,
        "depth": 5,
        "minimum_tree_weight": 7,
        "maximum_tree_weight": 29,
        "num_extra_edges": 1_600,
    },
    "c02": {
        "num_cells": 768,
        "minimum_edge_weight": 3,
        "maximum_edge_weight": 31,
        "constraints_per_boundary": 2,
    },
    "c03": {
        "num_variables": 1_536,
        "window_width": 12,
        "constraints_per_variable": 9,
        "minimum_edge_weight": 3,
        "maximum_edge_weight": 31,
    },
    "c04": {
        "num_variables": 1_280,
        "window_width": 15,
        "clauses_per_variable": 7,
        "minimum_clause_size": 3,
        "maximum_clause_size": 4,
        "minimum_edge_weight": 3,
        "maximum_edge_weight": 31,
    },
    "c05": {
        "num_bags": 121,
        "bag_width": 16,
        "separator_size": 6,
        "clauses_per_bag": 10,
        "minimum_clause_size": 3,
        "maximum_clause_size": 4,
        "minimum_edge_weight": 3,
        "maximum_edge_weight": 31,
    },
    "c06": {
        "branching_factor": 2,
        "depth": 11,
        "terminals_per_node": 2,
        "ancestor_window": 10,
        "groups_per_node": 4,
        "minimum_edge_weight": 3,
        "maximum_edge_weight": 31,
    },
}
CASE_IDS: Final = tuple(CASE_PARAMETERS)
_OPAQUE_ID_LIMIT: Final = (1 << 31) - 1


TASK_MANIFEST: Final[Mapping[str, Any]] = {
    "id": TASK_ID,
    "version": TASK_VERSION,
    "tier": 1,
    "title": "New Rooted Group Steiner Tree",
    "plugin": {"entrypoint": "aipbench.tasks.new_rooted_group_steiner_tree:create_task"},
    "protocol": {
        "api_version": "aip/1",
        "mode": "one_shot",
        "public_coin": False,
        "one_shot_eval": True,
        "max_events": 1,
        "participant_feedback": {"dev": "verbose", "eval": "minimal"},
    },
    "randomness": {
        "model": "committed_prg",
        "reveal_on_terminal": True,
        "domain_separation": "required",
    },
    "instance": {
        "public_schema": (
            "tasks/tier1_np/new_rooted_group_steiner_tree/schemas/public_instance.schema.json"
        ),
        "private_schema": (
            "tasks/tier1_np/new_rooted_group_steiner_tree/schemas/private_instance.schema.json"
        ),
    },
    "resources": {
        "wall_time_seconds": 600,
        "cpu_cores": 4,
        "memory_mb": 4096,
        "disk_mb": 4096,
        "max_artifact_bytes": 8_388_608,
        "max_events": 1,
    },
    "audit": {
        "replay_mode": "strict",
        "require_signature": True,
        "require_seed_commitment": True,
        "require_instance_digest": True,
        "require_event_chain": True,
        "require_seed_reveal": True,
    },
    "scoring": {"primary": "binary_accept", "partial_progress": "edge_set_submitted"},
    "soundness": {
        "class": "deterministic_certificate",
        "statement": (
            "selected public edges have total weight at most the public budget, "
            "are root-connected, and reach at least one vertex in every public group"
        ),
    },
}


class NewGroupSteinerStream(DeterministicStream):
    """Deterministic stream with a task-specific domain."""

    _DOMAIN: Final = b"aipbench/new-rooted-group-steiner-tree/generator/v1\x00"


def _integer_parameter(parameters: Mapping[str, Any], name: str, *, minimum: int) -> int:
    value = parameters.get(name)
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"case parameter {name!r} must be an integer >= {minimum}")
    return value


def _fresh_id(stream: NewGroupSteinerStream, used: set[int]) -> int:
    start = stream.randbelow(_OPAQUE_ID_LIMIT)
    for offset in range(len(used) + 1):
        candidate = 1 + (start + offset) % _OPAQUE_ID_LIMIT
        if candidate not in used:
            used.add(candidate)
            return candidate
    raise RuntimeError("opaque ID allocation failed")


def _build_c01(
    stream: NewGroupSteinerStream, parameters: Mapping[str, Any]
) -> tuple[Mapping[str, Any], Mapping[str, Any], Mapping[str, Any]]:
    branching = _integer_parameter(parameters, "branching_factor", minimum=2)
    depth = _integer_parameter(parameters, "depth", minimum=2)
    minimum_weight = _integer_parameter(parameters, "minimum_tree_weight", minimum=1)
    maximum_weight = _integer_parameter(parameters, "maximum_tree_weight", minimum=1)
    extra_count = _integer_parameter(parameters, "num_extra_edges", minimum=0)
    if minimum_weight > maximum_weight:
        raise ValueError("minimum tree weight exceeds maximum tree weight")

    num_vertices = (branching ** (depth + 1) - 1) // (branching - 1)
    first_terminal = (branching**depth - 1) // (branching - 1)
    tree_edges: list[tuple[int, int, int]] = []
    occupied: set[tuple[int, int]] = set()
    for child in range(1, num_vertices):
        parent = (child - 1) // branching
        weight = stream.randint(minimum_weight, maximum_weight)
        tree_edges.append((parent, child, weight))
        occupied.add((parent, child))
    budget = sum(weight for _first, _second, weight in tree_edges)

    maximum_extras = num_vertices * (num_vertices - 1) // 2 - len(occupied)
    if extra_count > maximum_extras:
        raise ValueError("requested too many extra edges")
    extra_edges: list[tuple[int, int, int]] = []
    while len(extra_edges) < extra_count:
        first = stream.randbelow(num_vertices)
        second = stream.randbelow(num_vertices - 1)
        if second >= first:
            second += 1
        pair = tuple(sorted((first, second)))
        if pair in occupied:
            continue
        occupied.add(pair)
        extra_edges.append((pair[0], pair[1], budget + 1 + stream.randbelow(10_000)))

    permutation = list(range(1, num_vertices + 1))
    stream.shuffle(permutation)
    used_edge_ids: set[int] = set()
    public_edges: list[dict[str, int]] = []
    reference_edge_ids: list[int] = []
    for edge_index, (first, second, weight) in enumerate((*tree_edges, *extra_edges)):
        edge_id = _fresh_id(stream, used_edge_ids)
        public_first, public_second = sorted((permutation[first], permutation[second]))
        public_edges.append(
            {
                "edge_id": edge_id,
                "u": public_first,
                "v": public_second,
                "weight": weight,
            }
        )
        if edge_index < len(tree_edges):
            reference_edge_ids.append(edge_id)
    stream.shuffle(public_edges)
    stream.shuffle(reference_edge_ids)

    used_group_ids: set[int] = set()
    public_groups = [
        {
            "group_id": _fresh_id(stream, used_group_ids),
            "vertices": [permutation[vertex]],
        }
        for vertex in range(first_terminal, num_vertices)
    ]
    stream.shuffle(public_groups)

    public_instance = {
        "format_version": "aip-rooted-group-steiner-tree-instance/1",
        "num_vertices": num_vertices,
        "edges": public_edges,
        "root": permutation[0],
        "groups": public_groups,
        "budget": budget,
    }
    private_instance = {
        "reference_edge_ids": reference_edge_ids,
        "reference_cost": budget,
    }
    metadata = {
        "generator": "new-rooted-group-steiner-tree/c01/v1",
        "case_id": "c01",
        "construction": "mandatory-cut calibration",
        "tree_edges": len(tree_edges),
        "extra_edges": len(extra_edges),
        "group_count": len(public_groups),
        "optimality_certificate": (
            "every non-reference edge individually exceeds the budget; every "
            "reference edge separates the root from a singleton public group"
        ),
    }
    return public_instance, private_instance, metadata


def _solve_c02_mode_path(
    *,
    mode_costs: tuple[tuple[int, int, int], ...],
    groups_by_boundary: tuple[tuple[tuple[int, int], ...], ...],
) -> tuple[int, tuple[int, ...]]:
    """Find the exact minimum of the three-state serial-cell model."""

    if not mode_costs or len(groups_by_boundary) != len(mode_costs) - 1:
        raise ValueError("malformed serial-cell model")

    def mode_cost(cell: int, mode: int) -> int:
        return mode_costs[cell][mode - 1]

    states = (1, 2, 3)
    prior_cost = {mode: mode_cost(0, mode) for mode in states}
    backtrack: list[dict[int, int]] = []
    for cell, group_pairs in enumerate(groups_by_boundary, start=1):
        current_cost: dict[int, int] = {}
        current_parent: dict[int, int] = {}
        for mode in states:
            best: tuple[int, int] | None = None
            for previous in states:
                if any(not (previous & left) and not (mode & right) for left, right in group_pairs):
                    continue
                candidate = (prior_cost[previous] + mode_cost(cell, mode), previous)
                if best is None or candidate < best:
                    best = candidate
            if best is not None:
                current_cost[mode], current_parent[mode] = best
        if not current_cost:
            raise ValueError("serial-cell model is infeasible")
        prior_cost = current_cost
        backtrack.append(current_parent)

    final_mode = min(prior_cost, key=lambda mode: (prior_cost[mode], mode))
    optimum = prior_cost[final_mode]
    modes = [final_mode]
    for parents in reversed(backtrack):
        modes.append(parents[modes[-1]])
    modes.reverse()
    return optimum, tuple(modes)


def _build_c02(
    stream: NewGroupSteinerStream, parameters: Mapping[str, Any]
) -> tuple[Mapping[str, Any], Mapping[str, Any], Mapping[str, Any]]:
    num_cells = _integer_parameter(parameters, "num_cells", minimum=2)
    minimum_weight = _integer_parameter(parameters, "minimum_edge_weight", minimum=1)
    maximum_weight = _integer_parameter(parameters, "maximum_edge_weight", minimum=1)
    constraints_per_boundary = _integer_parameter(parameters, "constraints_per_boundary", minimum=1)
    if minimum_weight > maximum_weight:
        raise ValueError("minimum edge weight exceeds maximum edge weight")
    if constraints_per_boundary > 3:
        raise ValueError("at most three distinct constraints fit one boundary")

    articulation_vertices = [0]
    branch_vertices: list[tuple[int, int]] = []
    logical_edges: list[tuple[int, int, int]] = []
    mode_costs: list[tuple[int, int, int]] = []
    mode_edge_indices: list[tuple[tuple[int, ...], tuple[int, ...], tuple[int, ...]]] = []
    next_vertex = 1
    for _cell in range(num_cells):
        left = articulation_vertices[-1]
        top, bottom, right = next_vertex, next_vertex + 1, next_vertex + 2
        next_vertex += 3
        articulation_vertices.append(right)
        branch_vertices.append((top, bottom))
        cell_indices: list[tuple[int, int]] = []
        cell_costs: list[int] = []
        for internal in (top, bottom):
            first_weight = stream.randint(minimum_weight, maximum_weight)
            second_weight = stream.randint(minimum_weight, maximum_weight)
            first_index = len(logical_edges)
            logical_edges.append((min(left, internal), max(left, internal), first_weight))
            second_index = len(logical_edges)
            logical_edges.append((min(internal, right), max(internal, right), second_weight))
            cell_indices.append((first_index, second_index))
            cell_costs.append(first_weight + second_weight)
        top_indices, bottom_indices = cell_indices
        top_weights = tuple(logical_edges[index][2] for index in top_indices)
        bottom_weights = tuple(logical_edges[index][2] for index in bottom_indices)
        first_option = (
            sum(top_weights) + min(bottom_weights),
            (*top_indices, bottom_indices[bottom_weights.index(min(bottom_weights))]),
        )
        second_option = (
            sum(bottom_weights) + min(top_weights),
            (*bottom_indices, top_indices[top_weights.index(min(top_weights))]),
        )
        both_indices = min(first_option, second_option)[1]
        mode_edge_indices.append((top_indices, bottom_indices, both_indices))
        mode_costs.append(
            (
                cell_costs[0],
                cell_costs[1],
                sum(logical_edges[index][2] for index in both_indices),
            )
        )

    planted_modes = tuple(1 + stream.randbelow(2) for _ in range(num_cells))
    groups_by_boundary: list[tuple[tuple[int, int], ...]] = []
    logical_groups: list[frozenset[int]] = []
    all_pairs = ((1, 1), (1, 2), (2, 1), (2, 2))
    for boundary in range(num_cells - 1):
        missed_by_planted = (
            3 ^ planted_modes[boundary],
            3 ^ planted_modes[boundary + 1],
        )
        candidates = [pair for pair in all_pairs if pair != missed_by_planted]
        stream.shuffle(candidates)
        groups = tuple(candidates[:constraints_per_boundary])
        groups_by_boundary.append(groups)
        for left, right in groups:
            logical_groups.append(
                frozenset(
                    (
                        branch_vertices[boundary][left - 1],
                        branch_vertices[boundary + 1][right - 1],
                    )
                )
            )
    logical_groups.append(frozenset((articulation_vertices[-1],)))

    budget, optimal_modes = _solve_c02_mode_path(
        mode_costs=tuple(mode_costs),
        groups_by_boundary=tuple(groups_by_boundary),
    )
    reference_edge_indices: set[int] = set()
    for cell, mode in enumerate(optimal_modes):
        reference_edge_indices.update(mode_edge_indices[cell][mode - 1])

    num_vertices = next_vertex
    permutation = list(range(1, num_vertices + 1))
    stream.shuffle(permutation)
    used_edge_ids: set[int] = set()
    public_edges: list[dict[str, int]] = []
    reference_edge_ids: list[int] = []
    for edge_index, (first, second, weight) in enumerate(logical_edges):
        edge_id = _fresh_id(stream, used_edge_ids)
        public_first, public_second = sorted((permutation[first], permutation[second]))
        public_edges.append(
            {
                "edge_id": edge_id,
                "u": public_first,
                "v": public_second,
                "weight": weight,
            }
        )
        if edge_index in reference_edge_indices:
            reference_edge_ids.append(edge_id)
    stream.shuffle(public_edges)
    stream.shuffle(reference_edge_ids)

    used_group_ids: set[int] = set()
    public_groups = []
    for group in logical_groups:
        vertices = [permutation[vertex] for vertex in group]
        stream.shuffle(vertices)
        public_groups.append({"group_id": _fresh_id(stream, used_group_ids), "vertices": vertices})
    stream.shuffle(public_groups)

    public_instance = {
        "format_version": "aip-rooted-group-steiner-tree-instance/1",
        "num_vertices": num_vertices,
        "edges": public_edges,
        "root": permutation[0],
        "groups": public_groups,
        "budget": budget,
    }
    private_instance = {
        "reference_edge_ids": reference_edge_ids,
        "reference_cost": budget,
    }
    metadata = {
        "generator": "new-rooted-group-steiner-tree/c02/v1",
        "case_id": "c02",
        "construction": "serial cactus with adjacent group constraints",
        "num_cells": num_cells,
        "group_count": len(public_groups),
        "selected_modes": list(optimal_modes),
        "optimality_certificate": "exact three-state path dynamic program",
    }
    evaluation = evaluate_edge_set(public_instance, reference_edge_ids)
    if not evaluation.connected or not evaluation.groups_hit or evaluation.cost != budget:
        raise ValueError("generated C02 reference failed public verification")
    return public_instance, private_instance, metadata


def _solve_c03_frontier(
    *,
    costs: tuple[tuple[int, int], ...],
    constraints_by_right: tuple[tuple[tuple[int, int, int], ...], ...],
    window_width: int,
) -> tuple[int, tuple[int, ...]]:
    """Solve the exact binary bounded-frontier model and recover one assignment."""

    if not costs or len(constraints_by_right) != len(costs):
        raise ValueError("malformed bounded-frontier model")
    if window_width < 1:
        raise ValueError("window width must be positive")
    prior: dict[int, int] = {0: 0}
    parents: list[dict[int, tuple[int, int]]] = []
    mask_limit = (1 << window_width) - 1
    for right, local_constraints in enumerate(constraints_by_right):
        current: dict[int, int] = {}
        parent_row: dict[int, tuple[int, int]] = {}
        for prior_mask, prior_cost in prior.items():
            for value in (0, 1):
                feasible = True
                for left, forbidden_left, forbidden_right in local_constraints:
                    if value != forbidden_right:
                        continue
                    distance = right - left
                    left_value = (prior_mask >> (distance - 1)) & 1
                    if left_value == forbidden_left:
                        feasible = False
                        break
                if not feasible:
                    continue
                current_mask = ((prior_mask << 1) | value) & mask_limit
                candidate = prior_cost + costs[right][value]
                key = (candidate, prior_mask, value)
                existing = current.get(current_mask)
                if existing is None or key < (
                    existing,
                    parent_row[current_mask][0],
                    parent_row[current_mask][1],
                ):
                    current[current_mask] = candidate
                    parent_row[current_mask] = (prior_mask, value)
        if not current:
            raise ValueError("bounded-frontier model is infeasible")
        prior = current
        parents.append(parent_row)

    final_mask = min(prior, key=lambda mask: (prior[mask], mask))
    optimum = prior[final_mask]
    assignment = [0] * len(costs)
    mask = final_mask
    for index in range(len(costs) - 1, -1, -1):
        previous, value = parents[index][mask]
        assignment[index] = value
        mask = previous
    return optimum, tuple(assignment)


def _build_c03(
    stream: NewGroupSteinerStream, parameters: Mapping[str, Any]
) -> tuple[Mapping[str, Any], Mapping[str, Any], Mapping[str, Any]]:
    num_variables = _integer_parameter(parameters, "num_variables", minimum=2)
    window_width = _integer_parameter(parameters, "window_width", minimum=1)
    constraints_per_variable = _integer_parameter(parameters, "constraints_per_variable", minimum=1)
    minimum_weight = _integer_parameter(parameters, "minimum_edge_weight", minimum=1)
    maximum_weight = _integer_parameter(parameters, "maximum_edge_weight", minimum=1)
    if minimum_weight > maximum_weight:
        raise ValueError("minimum edge weight exceeds maximum edge weight")
    if window_width >= num_variables:
        raise ValueError("window width must be smaller than the variable count")
    if constraints_per_variable > window_width:
        raise ValueError("too many distinct predecessor constraints requested")
    choice_base = num_variables * (maximum_weight - minimum_weight) + 1

    root = 0
    centers: list[int] = []
    choice_vertices: list[tuple[int, int]] = []
    logical_edges: list[tuple[int, int, int]] = []
    choice_edge_indices: list[tuple[tuple[int, int], tuple[int, int]]] = []
    costs: list[tuple[int, int]] = []
    next_vertex = 1
    for _variable in range(num_variables):
        center, zero, one = next_vertex, next_vertex + 1, next_vertex + 2
        next_vertex += 3
        centers.append(center)
        choice_vertices.append((zero, one))
        spoke_weight = stream.randint(minimum_weight, maximum_weight)
        spoke_index = len(logical_edges)
        logical_edges.append((root, center, spoke_weight))
        local_indices = []
        local_costs = []
        for choice in (zero, one):
            choice_weight = choice_base + stream.randint(minimum_weight, maximum_weight)
            choice_index = len(logical_edges)
            logical_edges.append((center, choice, choice_weight))
            local_indices.append((spoke_index, choice_index))
            local_costs.append(spoke_weight + choice_weight)
        choice_edge_indices.append((local_indices[0], local_indices[1]))
        costs.append((local_costs[0], local_costs[1]))

    planted = tuple(stream.randbelow(2) for _ in range(num_variables))
    constraints_by_right: list[list[tuple[int, int, int]]] = [[] for _ in range(num_variables)]
    logical_groups: list[frozenset[int]] = [frozenset((center,)) for center in centers]
    logical_groups.extend(frozenset((zero, one)) for zero, one in choice_vertices)
    for index in range(len(centers) - 1):
        left, right = centers[index], centers[index + 1]
        logical_groups.append(frozenset((left, right)))
    for right in range(1, num_variables):
        predecessor_count = min(window_width, right)
        predecessors = list(range(right - predecessor_count, right))
        stream.shuffle(predecessors)
        for left in predecessors[: min(constraints_per_variable, predecessor_count)]:
            forbidden_left = stream.randbelow(2)
            forbidden_right = stream.randbelow(2)
            if (planted[left], planted[right]) == (forbidden_left, forbidden_right):
                forbidden_left ^= 1
            constraints_by_right[right].append((left, forbidden_left, forbidden_right))
            logical_groups.append(
                frozenset(
                    (
                        choice_vertices[left][forbidden_left ^ 1],
                        choice_vertices[right][forbidden_right ^ 1],
                    )
                )
            )

    budget, assignment = _solve_c03_frontier(
        costs=tuple(costs),
        constraints_by_right=tuple(tuple(row) for row in constraints_by_right),
        window_width=window_width,
    )
    reference_edge_indices = {
        edge_index
        for variable, value in enumerate(assignment)
        for edge_index in choice_edge_indices[variable][value]
    }

    permutation = list(range(1, next_vertex + 1))
    stream.shuffle(permutation)
    used_edge_ids: set[int] = set()
    public_edges: list[dict[str, int]] = []
    reference_edge_ids: list[int] = []
    for edge_index, (first, second, weight) in enumerate(logical_edges):
        edge_id = _fresh_id(stream, used_edge_ids)
        public_first, public_second = sorted((permutation[first], permutation[second]))
        public_edges.append(
            {
                "edge_id": edge_id,
                "u": public_first,
                "v": public_second,
                "weight": weight,
            }
        )
        if edge_index in reference_edge_indices:
            reference_edge_ids.append(edge_id)
    stream.shuffle(public_edges)
    stream.shuffle(reference_edge_ids)

    used_group_ids: set[int] = set()
    public_groups = []
    for group in logical_groups:
        vertices = [permutation[vertex] for vertex in group]
        stream.shuffle(vertices)
        public_groups.append({"group_id": _fresh_id(stream, used_group_ids), "vertices": vertices})
    stream.shuffle(public_groups)
    public_instance = {
        "format_version": "aip-rooted-group-steiner-tree-instance/1",
        "num_vertices": next_vertex,
        "edges": public_edges,
        "root": permutation[root],
        "groups": public_groups,
        "budget": budget,
    }
    private_instance = {
        "reference_edge_ids": reference_edge_ids,
        "reference_cost": budget,
    }
    metadata = {
        "generator": "new-rooted-group-steiner-tree/c03/v1",
        "case_id": "c03",
        "construction": "relabelled bounded-frontier choice graph",
        "num_variables": num_variables,
        "window_width": window_width,
        "choice_base": choice_base,
        "group_count": len(public_groups),
        "optimality_certificate": "exact binary frontier dynamic program",
    }
    evaluation = evaluate_edge_set(public_instance, reference_edge_ids)
    if not evaluation.connected or not evaluation.groups_hit or evaluation.cost != budget:
        raise ValueError("generated C03 reference failed public verification")
    return public_instance, private_instance, metadata


def _solve_c04_frontier(
    *,
    costs: tuple[tuple[int, int], ...],
    clauses_by_right: tuple[tuple[tuple[tuple[int, int], ...], ...], ...],
    window_width: int,
) -> tuple[int, tuple[int, ...]]:
    """Solve weighted bounded-span clauses by exhaustive frontier transfer."""

    if not costs or len(clauses_by_right) != len(costs):
        raise ValueError("malformed higher-order frontier model")
    mask_limit = (1 << window_width) - 1
    prior: dict[int, int] = {0: 0}
    parents: list[dict[int, tuple[int, int]]] = []
    for right, local_clauses in enumerate(clauses_by_right):
        current: dict[int, int] = {}
        parent_row: dict[int, tuple[int, int]] = {}
        for prior_mask, prior_cost in prior.items():
            for value in (0, 1):
                feasible = True
                for clause in local_clauses:
                    clause_hit = False
                    for variable, literal_value in clause:
                        if variable == right:
                            actual = value
                        else:
                            distance = right - variable
                            actual = (prior_mask >> (distance - 1)) & 1
                        if actual == literal_value:
                            clause_hit = True
                            break
                    if not clause_hit:
                        feasible = False
                        break
                if not feasible:
                    continue
                current_mask = ((prior_mask << 1) | value) & mask_limit
                candidate = prior_cost + costs[right][value]
                existing = current.get(current_mask)
                key = (candidate, prior_mask, value)
                if existing is None or key < (
                    existing,
                    parent_row[current_mask][0],
                    parent_row[current_mask][1],
                ):
                    current[current_mask] = candidate
                    parent_row[current_mask] = (prior_mask, value)
        if not current:
            raise ValueError("higher-order frontier model is infeasible")
        prior = current
        parents.append(parent_row)

    final_mask = min(prior, key=lambda mask: (prior[mask], mask))
    optimum = prior[final_mask]
    assignment = [0] * len(costs)
    mask = final_mask
    for index in range(len(costs) - 1, -1, -1):
        previous, value = parents[index][mask]
        assignment[index] = value
        mask = previous
    return optimum, tuple(assignment)


def _build_c04(
    stream: NewGroupSteinerStream, parameters: Mapping[str, Any]
) -> tuple[Mapping[str, Any], Mapping[str, Any], Mapping[str, Any]]:
    num_variables = _integer_parameter(parameters, "num_variables", minimum=4)
    window_width = _integer_parameter(parameters, "window_width", minimum=3)
    clauses_per_variable = _integer_parameter(parameters, "clauses_per_variable", minimum=1)
    minimum_clause_size = _integer_parameter(parameters, "minimum_clause_size", minimum=3)
    maximum_clause_size = _integer_parameter(
        parameters, "maximum_clause_size", minimum=minimum_clause_size
    )
    minimum_weight = _integer_parameter(parameters, "minimum_edge_weight", minimum=1)
    maximum_weight = _integer_parameter(parameters, "maximum_edge_weight", minimum=1)
    if minimum_weight > maximum_weight:
        raise ValueError("minimum edge weight exceeds maximum edge weight")
    if window_width >= num_variables:
        raise ValueError("window width must be smaller than the variable count")
    if maximum_clause_size > window_width + 1:
        raise ValueError("clause size exceeds one frontier window")
    choice_base = num_variables * (maximum_weight - minimum_weight) + 1

    root = 0
    centers: list[int] = []
    choice_vertices: list[tuple[int, int]] = []
    logical_edges: list[tuple[int, int, int]] = []
    choice_edge_indices: list[tuple[tuple[int, int], tuple[int, int]]] = []
    costs: list[tuple[int, int]] = []
    next_vertex = 1
    for _variable in range(num_variables):
        center, zero, one = next_vertex, next_vertex + 1, next_vertex + 2
        next_vertex += 3
        centers.append(center)
        choice_vertices.append((zero, one))
        spoke_weight = stream.randint(minimum_weight, maximum_weight)
        spoke_index = len(logical_edges)
        logical_edges.append((root, center, spoke_weight))
        indices: list[tuple[int, int]] = []
        local_costs: list[int] = []
        for choice in (zero, one):
            choice_weight = choice_base + stream.randint(minimum_weight, maximum_weight)
            choice_index = len(logical_edges)
            logical_edges.append((center, choice, choice_weight))
            indices.append((spoke_index, choice_index))
            local_costs.append(spoke_weight + choice_weight)
        choice_edge_indices.append((indices[0], indices[1]))
        costs.append((local_costs[0], local_costs[1]))

    planted = tuple(stream.randbelow(2) for _ in range(num_variables))
    clauses_by_right: list[list[tuple[tuple[int, int], ...]]] = [[] for _ in range(num_variables)]
    logical_groups: list[frozenset[int]] = [frozenset((center,)) for center in centers]
    logical_groups.extend(frozenset((zero, one)) for zero, one in choice_vertices)
    for index in range(len(centers) - 2):
        logical_groups.append(frozenset((centers[index], centers[index + 1], centers[index + 2])))

    for right in range(2, num_variables):
        available = list(range(max(0, right - window_width), right))
        signatures: set[tuple[tuple[int, int], ...]] = set()
        target_count = min(clauses_per_variable, 2 ** len(available))
        while len(signatures) < target_count:
            clause_size = min(
                stream.randint(minimum_clause_size, maximum_clause_size),
                len(available) + 1,
            )
            predecessors = list(available)
            stream.shuffle(predecessors)
            variables = sorted((*predecessors[: clause_size - 1], right))
            literals = [(variable, stream.randbelow(2)) for variable in variables]
            if not any(planted[variable] == literal for variable, literal in literals):
                variable, literal = literals[stream.randbelow(len(literals))]
                literals[literals.index((variable, literal))] = (
                    variable,
                    planted[variable],
                )
            signature = tuple(literals)
            if signature in signatures:
                continue
            signatures.add(signature)
            clauses_by_right[right].append(signature)
            logical_groups.append(
                frozenset(choice_vertices[variable][literal] for variable, literal in signature)
            )

    budget, assignment = _solve_c04_frontier(
        costs=tuple(costs),
        clauses_by_right=tuple(tuple(row) for row in clauses_by_right),
        window_width=window_width,
    )
    reference_edge_indices = {
        edge_index
        for variable, value in enumerate(assignment)
        for edge_index in choice_edge_indices[variable][value]
    }

    permutation = list(range(1, next_vertex + 1))
    stream.shuffle(permutation)
    used_edge_ids: set[int] = set()
    public_edges: list[dict[str, int]] = []
    reference_edge_ids: list[int] = []
    for edge_index, (first, second, weight) in enumerate(logical_edges):
        edge_id = _fresh_id(stream, used_edge_ids)
        public_first, public_second = sorted((permutation[first], permutation[second]))
        public_edges.append(
            {
                "edge_id": edge_id,
                "u": public_first,
                "v": public_second,
                "weight": weight,
            }
        )
        if edge_index in reference_edge_indices:
            reference_edge_ids.append(edge_id)
    stream.shuffle(public_edges)
    stream.shuffle(reference_edge_ids)

    used_group_ids: set[int] = set()
    public_groups = []
    for group in logical_groups:
        vertices = [permutation[vertex] for vertex in group]
        stream.shuffle(vertices)
        public_groups.append({"group_id": _fresh_id(stream, used_group_ids), "vertices": vertices})
    stream.shuffle(public_groups)
    public_instance = {
        "format_version": "aip-rooted-group-steiner-tree-instance/1",
        "num_vertices": next_vertex,
        "edges": public_edges,
        "root": permutation[root],
        "groups": public_groups,
        "budget": budget,
    }
    private_instance = {
        "reference_edge_ids": reference_edge_ids,
        "reference_cost": budget,
    }
    metadata = {
        "generator": "new-rooted-group-steiner-tree/c04/v1",
        "case_id": "c04",
        "construction": "relabelled higher-order bounded-frontier coverage",
        "num_variables": num_variables,
        "window_width": window_width,
        "choice_base": choice_base,
        "group_count": len(public_groups),
        "optimality_certificate": "exact higher-order frontier dynamic program",
    }
    evaluation = evaluate_edge_set(public_instance, reference_edge_ids)
    if not evaluation.connected or not evaluation.groups_hit or evaluation.cost != budget:
        raise ValueError("generated C04 reference failed public verification")
    return public_instance, private_instance, metadata


def _solve_c05_tree_decomposition(
    *,
    num_variables: int,
    bags: tuple[tuple[int, ...], ...],
    parents: tuple[int, ...],
    costs: tuple[tuple[int, int], ...],
    clauses_by_home: tuple[tuple[tuple[tuple[int, int], ...], ...], ...],
) -> tuple[int, tuple[int, ...]]:
    """Exact bottom-up DP on a supplied running-intersection bag tree."""

    if (
        not bags
        or len(parents) != len(bags)
        or len(clauses_by_home) != len(bags)
        or len(costs) != num_variables
        or parents[0] != -1
    ):
        raise ValueError("malformed tree-decomposition model")
    children: list[list[int]] = [[] for _ in bags]
    for bag in range(1, len(bags)):
        parent = parents[bag]
        if parent < 0 or parent >= bag:
            raise ValueError("bag parent order is invalid")
        children[parent].append(bag)

    introduced: list[tuple[int, ...]] = []
    separators: list[tuple[int, ...]] = []
    for bag, variables in enumerate(bags):
        parent_variables = set() if bag == 0 else set(bags[parents[bag]])
        separator = tuple(variable for variable in variables if variable in parent_variables)
        separators.append(separator)
        introduced.append(
            tuple(variable for variable in variables if variable not in parent_variables)
        )

    tables: list[dict[int, int]] = [{} for _ in bags]
    choices: list[dict[int, int]] = [{} for _ in bags]
    for bag in range(len(bags) - 1, -1, -1):
        variables = bags[bag]
        index = {variable: offset for offset, variable in enumerate(variables)}
        separator = separators[bag]
        for mask in range(1 << len(variables)):
            feasible = True
            for clause in clauses_by_home[bag]:
                if not any(
                    ((mask >> index[variable]) & 1) == literal for variable, literal in clause
                ):
                    feasible = False
                    break
            if not feasible:
                continue
            total = sum(
                costs[variable][(mask >> index[variable]) & 1] for variable in introduced[bag]
            )
            for child in children[bag]:
                child_separator = separators[child]
                child_key = sum(
                    ((mask >> index[variable]) & 1) << offset
                    for offset, variable in enumerate(child_separator)
                )
                if child_key not in tables[child]:
                    feasible = False
                    break
                total += tables[child][child_key]
            if not feasible:
                continue
            key = sum(
                ((mask >> index[variable]) & 1) << offset
                for offset, variable in enumerate(separator)
            )
            current = tables[bag].get(key)
            if current is None or (total, mask) < (current, choices[bag][key]):
                tables[bag][key] = total
                choices[bag][key] = mask
        if not tables[bag]:
            raise ValueError("tree-decomposition model is infeasible")

    assignment = [-1] * num_variables

    def recover(bag: int, separator_key: int) -> None:
        mask = choices[bag][separator_key]
        variables = bags[bag]
        index = {variable: offset for offset, variable in enumerate(variables)}
        for variable in variables:
            value = (mask >> index[variable]) & 1
            if assignment[variable] not in (-1, value):
                raise ValueError("tree DP recovery violated running intersection")
            assignment[variable] = value
        for child in children[bag]:
            child_key = sum(
                ((mask >> index[variable]) & 1) << offset
                for offset, variable in enumerate(separators[child])
            )
            recover(child, child_key)

    recover(0, 0)
    if any(value < 0 for value in assignment):
        raise ValueError("tree DP did not assign every variable")
    return tables[0][0], tuple(assignment)


def _build_c05(
    stream: NewGroupSteinerStream, parameters: Mapping[str, Any]
) -> tuple[Mapping[str, Any], Mapping[str, Any], Mapping[str, Any]]:
    num_bags = _integer_parameter(parameters, "num_bags", minimum=1)
    bag_width = _integer_parameter(parameters, "bag_width", minimum=4)
    separator_size = _integer_parameter(parameters, "separator_size", minimum=1)
    clauses_per_bag = _integer_parameter(parameters, "clauses_per_bag", minimum=1)
    minimum_clause_size = _integer_parameter(parameters, "minimum_clause_size", minimum=3)
    maximum_clause_size = _integer_parameter(
        parameters, "maximum_clause_size", minimum=minimum_clause_size
    )
    minimum_weight = _integer_parameter(parameters, "minimum_edge_weight", minimum=1)
    maximum_weight = _integer_parameter(parameters, "maximum_edge_weight", minimum=1)
    if separator_size >= bag_width:
        raise ValueError("separator must be smaller than a bag")
    if maximum_clause_size > bag_width:
        raise ValueError("clause size exceeds bag width")
    if minimum_weight > maximum_weight:
        raise ValueError("minimum edge weight exceeds maximum edge weight")

    parents = tuple(-1 if bag == 0 else (bag - 1) // 3 for bag in range(num_bags))
    bags: list[tuple[int, ...]] = []
    next_variable = 0
    for bag in range(num_bags):
        if bag == 0:
            variables = tuple(range(next_variable, next_variable + bag_width))
            next_variable += bag_width
        else:
            parent_variables = list(bags[parents[bag]])
            child_slot = (bag - 1) % 3
            if parents[bag] == 0:
                offset = child_slot * separator_size
                separator = tuple(
                    parent_variables[(offset + index) % len(parent_variables)]
                    for index in range(separator_size)
                )
            else:
                inherited_count = separator_size // 2
                inherited = parent_variables[:separator_size]
                fresh = parent_variables[separator_size:]
                separator = tuple(
                    inherited[(child_slot * inherited_count + index) % len(inherited)]
                    for index in range(inherited_count)
                ) + tuple(
                    fresh[(child_slot * inherited_count + index) % len(fresh)]
                    for index in range(separator_size - inherited_count)
                )
            introduced = tuple(range(next_variable, next_variable + bag_width - separator_size))
            next_variable += len(introduced)
            variables = (*separator, *introduced)
        bags.append(variables)
    num_variables = next_variable
    choice_base = num_variables * (maximum_weight - minimum_weight) + 1

    root = 0
    centers: list[int] = []
    choice_vertices: list[tuple[int, int]] = []
    logical_edges: list[tuple[int, int, int]] = []
    choice_edge_indices: list[tuple[tuple[int, int], tuple[int, int]]] = []
    costs: list[tuple[int, int]] = []
    next_vertex = 1
    for _variable in range(num_variables):
        center, zero, one = next_vertex, next_vertex + 1, next_vertex + 2
        next_vertex += 3
        centers.append(center)
        choice_vertices.append((zero, one))
        spoke_weight = stream.randint(minimum_weight, maximum_weight)
        spoke_index = len(logical_edges)
        logical_edges.append((root, center, spoke_weight))
        indices: list[tuple[int, int]] = []
        local_costs: list[int] = []
        for choice in (zero, one):
            choice_weight = choice_base + stream.randint(minimum_weight, maximum_weight)
            choice_index = len(logical_edges)
            logical_edges.append((center, choice, choice_weight))
            indices.append((spoke_index, choice_index))
            local_costs.append(spoke_weight + choice_weight)
        choice_edge_indices.append((indices[0], indices[1]))
        costs.append((local_costs[0], local_costs[1]))

    planted = tuple(stream.randbelow(2) for _ in range(num_variables))
    clauses_by_home: list[list[tuple[tuple[int, int], ...]]] = [[] for _ in bags]
    logical_groups: list[frozenset[int]] = [frozenset((center,)) for center in centers]
    logical_groups.extend(frozenset((zero, one)) for zero, one in choice_vertices)
    for variables in bags:
        logical_groups.append(frozenset(centers[variable] for variable in variables))
    for bag in range(1, num_bags):
        separator = set(bags[bag]) & set(bags[parents[bag]])
        logical_groups.append(frozenset(centers[variable] for variable in separator))

    for bag, variables in enumerate(bags):
        signatures: set[tuple[tuple[int, int], ...]] = set()
        while len(signatures) < clauses_per_bag:
            clause_size = stream.randint(minimum_clause_size, maximum_clause_size)
            candidates = list(variables)
            stream.shuffle(candidates)
            clause_variables = sorted(candidates[:clause_size])
            literals = [(variable, stream.randbelow(2)) for variable in clause_variables]
            if not any(planted[variable] == literal for variable, literal in literals):
                index = stream.randbelow(len(literals))
                variable, _literal = literals[index]
                literals[index] = (variable, planted[variable])
            signature = tuple(literals)
            if signature in signatures:
                continue
            signatures.add(signature)
            clauses_by_home[bag].append(signature)
            logical_groups.append(
                frozenset(choice_vertices[variable][literal] for variable, literal in signature)
            )

    budget, assignment = _solve_c05_tree_decomposition(
        num_variables=num_variables,
        bags=tuple(bags),
        parents=parents,
        costs=tuple(costs),
        clauses_by_home=tuple(tuple(row) for row in clauses_by_home),
    )
    reference_edge_indices = {
        edge_index
        for variable, value in enumerate(assignment)
        for edge_index in choice_edge_indices[variable][value]
    }

    permutation = list(range(1, next_vertex + 1))
    stream.shuffle(permutation)
    used_edge_ids: set[int] = set()
    public_edges: list[dict[str, int]] = []
    reference_edge_ids: list[int] = []
    for edge_index, (first, second, weight) in enumerate(logical_edges):
        edge_id = _fresh_id(stream, used_edge_ids)
        public_first, public_second = sorted((permutation[first], permutation[second]))
        public_edges.append(
            {
                "edge_id": edge_id,
                "u": public_first,
                "v": public_second,
                "weight": weight,
            }
        )
        if edge_index in reference_edge_indices:
            reference_edge_ids.append(edge_id)
    stream.shuffle(public_edges)
    stream.shuffle(reference_edge_ids)
    used_group_ids: set[int] = set()
    public_groups = []
    for group in logical_groups:
        vertices = [permutation[vertex] for vertex in group]
        stream.shuffle(vertices)
        public_groups.append({"group_id": _fresh_id(stream, used_group_ids), "vertices": vertices})
    stream.shuffle(public_groups)
    public_instance = {
        "format_version": "aip-rooted-group-steiner-tree-instance/1",
        "num_vertices": next_vertex,
        "edges": public_edges,
        "root": permutation[root],
        "groups": public_groups,
        "budget": budget,
    }
    private_instance = {
        "reference_edge_ids": reference_edge_ids,
        "reference_cost": budget,
    }
    metadata = {
        "generator": "new-rooted-group-steiner-tree/c05/v1",
        "case_id": "c05",
        "construction": "running-intersection ternary bag tree coverage",
        "num_bags": num_bags,
        "num_variables": num_variables,
        "bag_width": bag_width,
        "separator_size": separator_size,
        "choice_base": choice_base,
        "group_count": len(public_groups),
        "optimality_certificate": "exact bottom-up separator dynamic program",
    }
    evaluation = evaluate_edge_set(public_instance, reference_edge_ids)
    if not evaluation.connected or not evaluation.groups_hit or evaluation.cost != budget:
        raise ValueError("generated C05 reference failed public verification")
    return public_instance, private_instance, metadata


def _build_c06(
    stream: NewGroupSteinerStream, parameters: Mapping[str, Any]
) -> tuple[Mapping[str, Any], Mapping[str, Any], Mapping[str, Any]]:
    branching = _integer_parameter(parameters, "branching_factor", minimum=2)
    depth = _integer_parameter(parameters, "depth", minimum=2)
    terminals_per_node = _integer_parameter(parameters, "terminals_per_node", minimum=2)
    ancestor_window = _integer_parameter(parameters, "ancestor_window", minimum=1)
    groups_per_node = _integer_parameter(parameters, "groups_per_node", minimum=1)
    minimum_weight = _integer_parameter(parameters, "minimum_edge_weight", minimum=1)
    maximum_weight = _integer_parameter(parameters, "maximum_edge_weight", minimum=1)
    if minimum_weight > maximum_weight:
        raise ValueError("minimum edge weight exceeds maximum edge weight")

    num_tree_vertices = (branching ** (depth + 1) - 1) // (branching - 1)
    parent = [-1] + [(vertex - 1) // branching for vertex in range(1, num_tree_vertices)]
    logical_edges: list[tuple[int, int, int]] = []
    tree_edge_index = [-1] * num_tree_vertices
    for vertex in range(1, num_tree_vertices):
        tree_edge_index[vertex] = len(logical_edges)
        logical_edges.append(
            (parent[vertex], vertex, stream.randint(minimum_weight, maximum_weight))
        )

    terminal_vertices: list[tuple[int, ...]] = []
    terminal_edge_indices: list[tuple[int, ...]] = []
    next_vertex = num_tree_vertices
    terminal_base = num_tree_vertices * (maximum_weight - minimum_weight) + 1
    for tree_vertex in range(num_tree_vertices):
        terminals = []
        indices = []
        for _terminal in range(terminals_per_node):
            terminal = next_vertex
            next_vertex += 1
            terminals.append(terminal)
            indices.append(len(logical_edges))
            logical_edges.append(
                (
                    tree_vertex,
                    terminal,
                    terminal_base + stream.randint(minimum_weight, maximum_weight),
                )
            )
        terminal_vertices.append(tuple(terminals))
        terminal_edge_indices.append(tuple(indices))

    planted = tuple(stream.randint(0, terminals_per_node - 1) for _ in range(num_tree_vertices))
    logical_groups: list[frozenset[int]] = [frozenset(terminals) for terminals in terminal_vertices]
    clauses_by_node: list[list[tuple[tuple[int, int], ...]]] = [
        [] for _ in range(num_tree_vertices)
    ]
    for tree_vertex in range(num_tree_vertices):
        ancestors = []
        current = tree_vertex
        while current >= 0 and len(ancestors) < ancestor_window:
            ancestors.append(current)
            current = parent[current]
        for _group in range(groups_per_node):
            group_nodes = list(ancestors)
            stream.shuffle(group_nodes)
            group_nodes = group_nodes[: min(3, len(group_nodes))]
            if tree_vertex not in group_nodes:
                group_nodes[0] = tree_vertex
            literals = [(node, stream.randint(0, terminals_per_node - 1)) for node in group_nodes]
            if not any(planted[node] == value for node, value in literals):
                forced = stream.randint(0, len(literals) - 1)
                forced_node = literals[forced][0]
                literals[forced] = (forced_node, planted[forced_node])
            members = [terminal_vertices[node][value] for node, value in literals]
            logical_groups.append(frozenset(members))
            clauses_by_node[tree_vertex].append(tuple(literals))

    # Exact tree-structured message passing over bounded ancestor assignments.
    children: list[list[int]] = [[] for _ in range(num_tree_vertices)]
    for vertex in range(1, num_tree_vertices):
        children[parent[vertex]].append(vertex)
    assignment = [-1] * num_tree_vertices
    choices: dict[tuple[int, tuple[int, ...]], int] = {}
    memo_cost: dict[tuple[int, tuple[int, ...]], int] = {}
    infinity = 10**30

    def subtree_cost(node: int, ancestor_values: tuple[int, ...]) -> int:
        key = (node, ancestor_values)
        if key in memo_cost:
            return memo_cost[key]
        ancestor_nodes = []
        current = parent[node]
        while current >= 0 and len(ancestor_nodes) < len(ancestor_values):
            ancestor_nodes.append(current)
            current = parent[current]
        known = dict(zip(ancestor_nodes, ancestor_values, strict=True))
        best: tuple[int, int] | None = None
        for value in range(terminals_per_node):
            known[node] = value
            if any(
                not any(known.get(variable) == literal for variable, literal in clause)
                for clause in clauses_by_node[node]
            ):
                continue
            next_values = (value, *ancestor_values)[: ancestor_window - 1]
            candidate = logical_edges[terminal_edge_indices[node][value]][2] + sum(
                subtree_cost(child, next_values) for child in children[node]
            )
            if best is None or (candidate, value) < best:
                best = (candidate, value)
        if best is None:
            memo_cost[key] = infinity
            return infinity
        choices[key] = best[1]
        memo_cost[key] = best[0]
        return best[0]

    routing_cost = sum(logical_edges[index][2] for index in tree_edge_index[1:])
    terminal_cost = subtree_cost(0, ())
    if terminal_cost >= infinity:
        raise ValueError("C06 ancestor-window model is infeasible")
    best_cost = routing_cost + terminal_cost

    def recover(node: int, ancestor_values: tuple[int, ...]) -> None:
        value = choices[(node, ancestor_values)]
        assignment[node] = value
        next_values = (value, *ancestor_values)[: ancestor_window - 1]
        for child in children[node]:
            recover(child, next_values)

    recover(0, ())
    best_assignment = tuple(assignment)
    reference_edge_indices = set(tree_edge_index[1:])
    reference_edge_indices.update(
        terminal_edge_indices[node][best_assignment[node]] for node in range(num_tree_vertices)
    )

    permutation = list(range(1, next_vertex + 1))
    stream.shuffle(permutation)
    used_edge_ids: set[int] = set()
    public_edges: list[dict[str, int]] = []
    reference_edge_ids: list[int] = []
    for edge_index, (first, second, weight) in enumerate(logical_edges):
        edge_id = _fresh_id(stream, used_edge_ids)
        public_first, public_second = sorted((permutation[first], permutation[second]))
        public_edges.append(
            {"edge_id": edge_id, "u": public_first, "v": public_second, "weight": weight}
        )
        if edge_index in reference_edge_indices:
            reference_edge_ids.append(edge_id)
    stream.shuffle(public_edges)
    stream.shuffle(reference_edge_ids)
    used_group_ids: set[int] = set()
    public_groups = []
    for group in logical_groups:
        members = [permutation[vertex] for vertex in group]
        stream.shuffle(members)
        public_groups.append({"group_id": _fresh_id(stream, used_group_ids), "vertices": members})
    stream.shuffle(public_groups)
    public_instance = {
        "format_version": "aip-rooted-group-steiner-tree-instance/1",
        "num_vertices": next_vertex,
        "edges": public_edges,
        "root": permutation[0],
        "groups": public_groups,
        "budget": best_cost,
    }
    private_instance = {"reference_edge_ids": reference_edge_ids, "reference_cost": best_cost}
    metadata = {
        "generator": "new-rooted-group-steiner-tree/c06/v1",
        "case_id": "c06",
        "construction": "deep shared-routing tree with ancestor groups",
        "tree_vertices": num_tree_vertices,
        "group_count": len(public_groups),
        "optimality_certificate": "mandatory routing cuts and bounded ancestor assignment DP",
    }
    evaluation = evaluate_edge_set(public_instance, reference_edge_ids)
    if not evaluation.connected or not evaluation.groups_hit or evaluation.cost != best_cost:
        raise ValueError("generated C06 reference failed public verification")
    return public_instance, private_instance, metadata


class NewRootedGroupSteinerGenerator:
    def generate(
        self,
        *,
        instance_seed: bytes,
        case_id: str,
        case_parameters: Mapping[str, Any],
    ) -> GeneratedCase:
        if not isinstance(instance_seed, bytes):
            raise TypeError("instance_seed must be bytes")
        if case_id not in CASE_PARAMETERS:
            raise ValueError(f"unsupported new rooted-group-steiner case: {case_id}")
        parameters = dict(CASE_PARAMETERS[case_id])
        parameters.update(case_parameters)
        builders = {
            "c01": _build_c01,
            "c02": _build_c02,
            "c03": _build_c03,
            "c04": _build_c04,
            "c05": _build_c05,
            "c06": _build_c06,
        }
        builder = builders[case_id]
        public, private, metadata = builder(NewGroupSteinerStream(instance_seed), parameters)
        return GeneratedCase(
            task_id=TASK_ID,
            task_version=TASK_VERSION,
            case_id=case_id,
            public_instance=public,
            private_instance=private,
            generation_metadata=metadata,
        )


class NewRootedGroupSteinerProtocol(RootedGroupSteinerProtocol):
    task_id = TASK_ID
    task_version = TASK_VERSION

    @staticmethod
    def _validate_task_identity(generated_case: GeneratedCase) -> None:
        if generated_case.task_id != TASK_ID or generated_case.task_version != TASK_VERSION:
            raise ValueError("generated case does not belong to the new Group Steiner task")

    def public_protocol_description(self, *, generated_case: GeneratedCase) -> Mapping[str, Any]:
        description = dict(super().public_protocol_description(generated_case=generated_case))
        description["event_schemas"] = {
            EDGE_SET_EVENT_KIND: {
                "schema_ref": (
                    "tasks/tier1_np/new_rooted_group_steiner_tree/schemas/edge_set.schema.json"
                )
            }
        }
        return description


def solve_public_c01(public_instance: Mapping[str, Any]) -> tuple[int, ...]:
    """Recover C01 from public edge weights and prove the submitted relation."""

    num_vertices = public_instance.get("num_vertices")
    root = public_instance.get("root")
    budget = public_instance.get("budget")
    raw_edges = public_instance.get("edges")
    raw_groups = public_instance.get("groups")
    if (
        isinstance(num_vertices, bool)
        or not isinstance(num_vertices, int)
        or isinstance(root, bool)
        or not isinstance(root, int)
        or isinstance(budget, bool)
        or not isinstance(budget, int)
        or not isinstance(raw_edges, list)
        or not isinstance(raw_groups, list)
    ):
        raise ValueError("malformed public Group Steiner instance")
    adjacency: list[list[tuple[int, int]]] = [[] for _ in range(num_vertices + 1)]
    edge_by_pair: dict[tuple[int, int], int] = {}
    for raw_edge in raw_edges:
        if not isinstance(raw_edge, Mapping):
            raise ValueError("malformed public edge")
        edge_id = raw_edge.get("edge_id")
        first = raw_edge.get("u")
        second = raw_edge.get("v")
        weight = raw_edge.get("weight")
        if not all(
            isinstance(value, int) and not isinstance(value, bool)
            for value in (edge_id, first, second, weight)
        ):
            raise ValueError("malformed public edge fields")
        assert isinstance(edge_id, int) and isinstance(first, int)
        assert isinstance(second, int) and isinstance(weight, int)
        if weight <= budget:
            adjacency[first].append((second, edge_id))
            adjacency[second].append((first, edge_id))
            edge_by_pair[tuple(sorted((first, second)))] = edge_id
    if len(edge_by_pair) != num_vertices - 1:
        raise ValueError("public affordable subgraph is not a tree")

    parent = [0] * (num_vertices + 1)
    parent_edge = [0] * (num_vertices + 1)
    reached = {root}
    queue = deque([root])
    while queue:
        vertex = queue.popleft()
        for neighbor, edge_id in adjacency[vertex]:
            if neighbor in reached:
                continue
            reached.add(neighbor)
            parent[neighbor] = vertex
            parent_edge[neighbor] = edge_id
            queue.append(neighbor)
    if len(reached) != num_vertices:
        raise ValueError("public affordable tree is disconnected")

    selected: set[int] = set()
    for raw_group in raw_groups:
        if not isinstance(raw_group, Mapping):
            raise ValueError("malformed public group")
        vertices = raw_group.get("vertices")
        if not isinstance(vertices, list) or len(vertices) != 1 or not isinstance(vertices[0], int):
            raise ValueError("C01 public group is not a singleton")
        vertex = vertices[0]
        while vertex != root:
            selected.add(parent_edge[vertex])
            vertex = parent[vertex]
    evaluation = evaluate_edge_set(public_instance, list(selected))
    if not evaluation.connected or not evaluation.groups_hit or evaluation.cost != budget:
        raise ValueError("public recovery failed exact validation")
    return tuple(sorted(selected))


def solve_public_c02(public_instance: Mapping[str, Any]) -> tuple[int, ...]:
    """Recover the public cactus chain and solve its exact three-state path DP."""

    num_vertices = public_instance.get("num_vertices")
    root = public_instance.get("root")
    raw_edges = public_instance.get("edges")
    raw_groups = public_instance.get("groups")
    budget = public_instance.get("budget")
    if (
        isinstance(num_vertices, bool)
        or not isinstance(num_vertices, int)
        or isinstance(root, bool)
        or not isinstance(root, int)
        or not isinstance(raw_edges, list)
        or not isinstance(raw_groups, list)
        or isinstance(budget, bool)
        or not isinstance(budget, int)
    ):
        raise ValueError("malformed public C02 instance")

    adjacency: list[list[tuple[int, int, int]]] = [[] for _ in range(num_vertices + 1)]
    for raw_edge in raw_edges:
        if not isinstance(raw_edge, Mapping):
            raise ValueError("malformed public C02 edge")
        edge_id = raw_edge.get("edge_id")
        first = raw_edge.get("u")
        second = raw_edge.get("v")
        weight = raw_edge.get("weight")
        if not all(
            isinstance(value, int) and not isinstance(value, bool)
            for value in (edge_id, first, second, weight)
        ):
            raise ValueError("malformed public C02 edge fields")
        assert isinstance(edge_id, int) and isinstance(first, int)
        assert isinstance(second, int) and isinstance(weight, int)
        adjacency[first].append((second, edge_id, weight))
        adjacency[second].append((first, edge_id, weight))

    singleton_groups = []
    pair_groups: list[tuple[int, int]] = []
    for raw_group in raw_groups:
        if not isinstance(raw_group, Mapping) or not isinstance(raw_group.get("vertices"), list):
            raise ValueError("malformed public C02 group")
        vertices = raw_group["vertices"]
        if len(vertices) == 1 and isinstance(vertices[0], int):
            singleton_groups.append(vertices[0])
        elif len(vertices) == 2 and all(isinstance(vertex, int) for vertex in vertices):
            pair_groups.append((vertices[0], vertices[1]))
        else:
            raise ValueError("public C02 groups must have size one or two")
    if len(singleton_groups) != 1:
        raise ValueError("public C02 does not have one terminal group")
    terminal = singleton_groups[0]

    articulations = [root]
    cell_branches: list[tuple[int, int]] = []
    cell_edge_data: list[
        tuple[tuple[tuple[int, int], tuple[int, int]], tuple[tuple[int, int], tuple[int, int]]]
    ] = []
    previous_articulation: int | None = None
    current = root
    while current != terminal:
        candidates: dict[int, list[tuple[int, tuple[int, int], tuple[int, int]]]] = {}
        for branch, first_edge_id, first_weight in adjacency[current]:
            if len(adjacency[branch]) != 2:
                continue
            onward = [edge for edge in adjacency[branch] if edge[0] != current]
            if len(onward) != 1:
                continue
            right, second_edge_id, second_weight = onward[0]
            if right == previous_articulation:
                continue
            candidates.setdefault(right, []).append(
                (
                    branch,
                    (first_edge_id, first_weight),
                    (second_edge_id, second_weight),
                )
            )
        forward = [(right, entries) for right, entries in candidates.items() if len(entries) == 2]
        if len(forward) != 1:
            raise ValueError("public C02 cactus chain is not uniquely traversable")
        right, entries = forward[0]
        entries.sort(key=lambda item: item[0])
        cell_branches.append((entries[0][0], entries[1][0]))
        cell_edge_data.append(
            (
                (entries[0][1], entries[0][2]),
                (entries[1][1], entries[1][2]),
            )
        )
        articulations.append(right)
        previous_articulation, current = current, right
        if len(articulations) > num_vertices:
            raise ValueError("public C02 cactus traversal cycled")
    if 1 + 3 * len(cell_branches) != num_vertices:
        raise ValueError("public C02 traversal did not cover the graph")

    branch_location = {
        vertex: (cell, bit)
        for cell, branches in enumerate(cell_branches)
        for vertex, bit in zip(branches, (1, 2), strict=True)
    }
    group_pairs: list[list[tuple[int, int]]] = [[] for _ in range(len(cell_branches) - 1)]
    for first, second in pair_groups:
        if first not in branch_location or second not in branch_location:
            raise ValueError("public C02 group contains a non-branch vertex")
        first_location = branch_location[first]
        second_location = branch_location[second]
        if first_location[0] > second_location[0]:
            first_location, second_location = second_location, first_location
        if second_location[0] != first_location[0] + 1:
            raise ValueError("public C02 group does not cross one cell boundary")
        group_pairs[first_location[0]].append((first_location[1], second_location[1]))
    if any(not constraints for constraints in group_pairs):
        raise ValueError("public C02 boundary lacks a group constraint")

    mode_costs: list[tuple[int, int, int]] = []
    mode_edges: list[tuple[tuple[int, ...], tuple[int, ...], tuple[int, ...]]] = []
    for first_branch, second_branch in cell_edge_data:
        first_ids = (first_branch[0][0], first_branch[1][0])
        second_ids = (second_branch[0][0], second_branch[1][0])
        first_weights = (first_branch[0][1], first_branch[1][1])
        second_weights = (second_branch[0][1], second_branch[1][1])
        first_option = (*first_ids, second_ids[second_weights.index(min(second_weights))])
        second_option = (*second_ids, first_ids[first_weights.index(min(first_weights))])
        first_option_cost = sum(first_weights) + min(second_weights)
        second_option_cost = sum(second_weights) + min(first_weights)
        both = min(
            (first_option_cost, tuple(sorted(first_option)), first_option),
            (second_option_cost, tuple(sorted(second_option)), second_option),
        )[2]
        mode_edges.append((first_ids, second_ids, both))
        mode_costs.append(
            (
                sum(first_weights),
                sum(second_weights),
                sum(
                    weight for edge_id, weight in (*first_branch, *second_branch) if edge_id in both
                ),
            )
        )

    optimum, modes = _solve_c02_mode_path(
        mode_costs=tuple(mode_costs),
        groups_by_boundary=tuple(tuple(pairs) for pairs in group_pairs),
    )
    selected = {
        edge_id for cell, mode in enumerate(modes) for edge_id in mode_edges[cell][mode - 1]
    }
    evaluation = evaluate_edge_set(public_instance, list(selected))
    if (
        optimum != budget
        or evaluation.cost != budget
        or not evaluation.connected
        or not evaluation.groups_hit
    ):
        raise ValueError("public C02 recovery failed exact validation")
    return tuple(sorted(selected))


def solve_public_c03(public_instance: Mapping[str, Any]) -> tuple[int, ...]:
    """Recover and solve the bounded-frontier choice model from public data."""

    num_vertices = public_instance.get("num_vertices")
    root = public_instance.get("root")
    raw_edges = public_instance.get("edges")
    raw_groups = public_instance.get("groups")
    budget = public_instance.get("budget")
    if (
        isinstance(num_vertices, bool)
        or not isinstance(num_vertices, int)
        or isinstance(root, bool)
        or not isinstance(root, int)
        or not isinstance(raw_edges, list)
        or not isinstance(raw_groups, list)
        or isinstance(budget, bool)
        or not isinstance(budget, int)
    ):
        raise ValueError("malformed public C03 instance")

    adjacency: dict[int, list[tuple[int, int, int]]] = {
        vertex: [] for vertex in range(1, num_vertices + 1)
    }
    for raw_edge in raw_edges:
        if not isinstance(raw_edge, Mapping):
            raise ValueError("malformed public C03 edge")
        edge_id = raw_edge.get("edge_id")
        first = raw_edge.get("u")
        second = raw_edge.get("v")
        weight = raw_edge.get("weight")
        if not all(
            isinstance(value, int) and not isinstance(value, bool)
            for value in (edge_id, first, second, weight)
        ):
            raise ValueError("malformed public C03 edge fields")
        assert isinstance(edge_id, int) and isinstance(first, int)
        assert isinstance(second, int) and isinstance(weight, int)
        adjacency[first].append((second, edge_id, weight))
        adjacency[second].append((first, edge_id, weight))

    singleton_vertices: set[int] = set()
    center_link_groups: list[tuple[int, int]] = []
    choice_requirement_centers: set[int] = set()
    pair_groups: list[tuple[int, int]] = []
    for raw_group in raw_groups:
        if not isinstance(raw_group, Mapping) or not isinstance(raw_group.get("vertices"), list):
            raise ValueError("malformed public C03 group")
        vertices = raw_group["vertices"]
        if len(vertices) == 1 and isinstance(vertices[0], int):
            singleton_vertices.add(vertices[0])
        elif len(vertices) == 2 and all(isinstance(vertex, int) for vertex in vertices):
            pair_groups.append((vertices[0], vertices[1]))
        else:
            raise ValueError("public C03 groups must have size one or two")

    center_data: dict[int, tuple[int, tuple[tuple[int, int, int], tuple[int, int, int]]]] = {}
    choice_location: dict[int, tuple[int, int]] = {}
    for center in singleton_vertices:
        root_edges = [entry for entry in adjacency[center] if entry[0] == root]
        leaves = [entry for entry in adjacency[center] if len(adjacency[entry[0]]) == 1]
        if len(root_edges) != 1 or len(leaves) != 2 or len(adjacency[center]) != 3:
            raise ValueError("public C03 singleton does not identify a choice center")
        leaves.sort(key=lambda entry: entry[0])
        center_data[center] = (root_edges[0][1], (leaves[0], leaves[1]))
        choice_location[leaves[0][0]] = (center, 0)
        choice_location[leaves[1][0]] = (center, 1)
    if 1 + 3 * len(center_data) != num_vertices:
        raise ValueError("public C03 center decomposition does not cover the graph")

    center_adjacency: dict[int, set[int]] = {center: set() for center in center_data}
    recovered_groups: list[tuple[int, int, int, int]] = []
    for first, second in pair_groups:
        if first in center_data and second in center_data:
            center_link_groups.append((first, second))
            continue
        if first not in choice_location or second not in choice_location:
            raise ValueError("public C03 pair group contains a non-choice vertex")
        first_center, first_bit = choice_location[first]
        second_center, second_bit = choice_location[second]
        if first_center == second_center:
            if first_bit == second_bit:
                raise ValueError("public C03 choice requirement repeats one leaf")
            choice_requirement_centers.add(first_center)
            continue
        center_adjacency[first_center].add(second_center)
        center_adjacency[second_center].add(first_center)
        recovered_groups.append((first_center, first_bit, second_center, second_bit))
    if choice_requirement_centers != set(center_data):
        raise ValueError("public C03 does not require one choice at every center")

    ordering_adjacency: dict[int, list[int]] = {center: [] for center in center_data}
    for first, second in center_link_groups:
        ordering_adjacency[first].append(second)
        ordering_adjacency[second].append(first)
    endpoints = [center for center, neighbors in ordering_adjacency.items() if len(neighbors) == 1]
    if len(endpoints) != 2 or any(
        len(neighbors) not in (1, 2) for neighbors in ordering_adjacency.values()
    ):
        raise ValueError("public C03 ordering markers are not a spanning path")
    start = min(endpoints)
    order = []
    previous: int | None = None
    current = start
    while True:
        order.append(current)
        onward = [neighbor for neighbor in ordering_adjacency[current] if neighbor != previous]
        if not onward:
            break
        if len(onward) != 1:
            raise ValueError("public C03 ordering path branches")
        previous, current = current, onward[0]
    if len(order) != len(center_data):
        raise ValueError("public C03 ordering path does not cover every center")
    position = {center: index for index, center in enumerate(order)}

    constraints_by_right: list[list[tuple[int, int, int]]] = [[] for _ in order]
    for first_center, first_bit, second_center, second_bit in recovered_groups:
        first_position = position[first_center]
        second_position = position[second_center]
        if first_position > second_position:
            first_position, second_position = second_position, first_position
            first_bit, second_bit = second_bit, first_bit
        if second_position - first_position > 12:
            raise ValueError("public C03 recovered order has excessive constraint span")
        constraints_by_right[second_position].append(
            (first_position, first_bit ^ 1, second_bit ^ 1)
        )

    costs: list[tuple[int, int]] = []
    choice_edges: list[tuple[tuple[int, int], tuple[int, int]]] = []
    for center in order:
        root_edge_id, leaves = center_data[center]
        root_edge = next(entry for entry in adjacency[center] if entry[1] == root_edge_id)
        leaf_edges = ((root_edge_id, leaves[0][1]), (root_edge_id, leaves[1][1]))
        choice_edges.append(leaf_edges)
        costs.append(
            (
                root_edge[2] + leaves[0][2],
                root_edge[2] + leaves[1][2],
            )
        )
    optimum, assignment = _solve_c03_frontier(
        costs=tuple(costs),
        constraints_by_right=tuple(tuple(row) for row in constraints_by_right),
        window_width=12,
    )
    selected = {
        edge_id for index, value in enumerate(assignment) for edge_id in choice_edges[index][value]
    }
    evaluation = evaluate_edge_set(public_instance, list(selected))
    if (
        optimum != budget
        or evaluation.cost != budget
        or not evaluation.connected
        or not evaluation.groups_hit
    ):
        raise ValueError("public C03 recovery failed exact validation")
    return tuple(sorted(selected))


def solve_public_c04(public_instance: Mapping[str, Any]) -> tuple[int, ...]:
    """Recover higher-order public coverage clauses and solve their frontier."""

    num_vertices = public_instance.get("num_vertices")
    root = public_instance.get("root")
    raw_edges = public_instance.get("edges")
    raw_groups = public_instance.get("groups")
    budget = public_instance.get("budget")
    if (
        isinstance(num_vertices, bool)
        or not isinstance(num_vertices, int)
        or isinstance(root, bool)
        or not isinstance(root, int)
        or not isinstance(raw_edges, list)
        or not isinstance(raw_groups, list)
        or isinstance(budget, bool)
        or not isinstance(budget, int)
    ):
        raise ValueError("malformed public C04 instance")

    adjacency: dict[int, list[tuple[int, int, int]]] = {
        vertex: [] for vertex in range(1, num_vertices + 1)
    }
    for raw_edge in raw_edges:
        if not isinstance(raw_edge, Mapping):
            raise ValueError("malformed public C04 edge")
        edge_id = raw_edge.get("edge_id")
        first = raw_edge.get("u")
        second = raw_edge.get("v")
        weight = raw_edge.get("weight")
        if not all(
            isinstance(value, int) and not isinstance(value, bool)
            for value in (edge_id, first, second, weight)
        ):
            raise ValueError("malformed public C04 edge fields")
        assert isinstance(edge_id, int) and isinstance(first, int)
        assert isinstance(second, int) and isinstance(weight, int)
        adjacency[first].append((second, edge_id, weight))
        adjacency[second].append((first, edge_id, weight))

    singleton_vertices: set[int] = set()
    nonsingleton_groups: list[tuple[int, ...]] = []
    for raw_group in raw_groups:
        if not isinstance(raw_group, Mapping) or not isinstance(raw_group.get("vertices"), list):
            raise ValueError("malformed public C04 group")
        vertices = raw_group["vertices"]
        if not vertices or not all(isinstance(vertex, int) for vertex in vertices):
            raise ValueError("malformed public C04 group vertices")
        if len(vertices) == 1:
            singleton_vertices.add(vertices[0])
        else:
            nonsingleton_groups.append(tuple(vertices))

    center_data: dict[
        int,
        tuple[
            tuple[int, int],
            tuple[tuple[int, int, int], tuple[int, int, int]],
        ],
    ] = {}
    choice_location: dict[int, tuple[int, int]] = {}
    for center in singleton_vertices:
        root_edges = [entry for entry in adjacency[center] if entry[0] == root]
        leaves = [entry for entry in adjacency[center] if len(adjacency[entry[0]]) == 1]
        if len(root_edges) != 1 or len(leaves) != 2 or len(adjacency[center]) != 3:
            raise ValueError("public C04 singleton does not identify a choice center")
        leaves.sort(key=lambda entry: entry[0])
        center_data[center] = (
            (root_edges[0][1], root_edges[0][2]),
            (leaves[0], leaves[1]),
        )
        choice_location[leaves[0][0]] = (center, 0)
        choice_location[leaves[1][0]] = (center, 1)
    if 1 + 3 * len(center_data) != num_vertices:
        raise ValueError("public C04 center decomposition does not cover the graph")

    center_markers: list[tuple[int, ...]] = []
    requirement_centers: set[int] = set()
    clause_groups: list[tuple[int, ...]] = []
    for vertices in nonsingleton_groups:
        if all(vertex in center_data for vertex in vertices):
            center_markers.append(vertices)
            continue
        if not all(vertex in choice_location for vertex in vertices):
            raise ValueError("public C04 group mixes center and choice vertices")
        locations = [choice_location[vertex] for vertex in vertices]
        centers = {center for center, _bit in locations}
        if len(vertices) == 2 and len(centers) == 1:
            requirement_centers.update(centers)
            continue
        if len(centers) != len(vertices) or len(vertices) not in (3, 4):
            raise ValueError("public C04 coverage clause has invalid arity")
        clause_groups.append(vertices)
    if requirement_centers != set(center_data):
        raise ValueError("public C04 does not require one choice at every center")

    marker_adjacency: dict[int, set[int]] = {center: set() for center in center_data}
    for marker in center_markers:
        for first in marker:
            marker_adjacency[first].update(second for second in marker if second != first)
    endpoints = [center for center, neighbors in marker_adjacency.items() if len(neighbors) == 2]
    if len(endpoints) != 2 or any(
        len(neighbors) not in (2, 3, 4) for neighbors in marker_adjacency.values()
    ):
        raise ValueError("public C04 order markers are malformed")
    start = min(endpoints)
    first_candidates = [
        center for center in marker_adjacency[start] if len(marker_adjacency[center]) == 3
    ]
    if len(first_candidates) != 1:
        raise ValueError("public C04 order markers do not identify the second center")
    order = [start, first_candidates[0]]
    while len(order) < len(center_data):
        candidates = [
            center
            for center in marker_adjacency[order[-1]] & marker_adjacency[order[-2]]
            if center not in order
        ]
        if len(candidates) != 1:
            raise ValueError("public C04 order markers do not determine one path")
        order.append(candidates[0])
    position = {center: index for index, center in enumerate(order)}

    clauses_by_right: list[list[tuple[tuple[int, int], ...]]] = [[] for _ in order]
    for vertices in clause_groups:
        clause = sorted(
            (position[choice_location[vertex][0]], choice_location[vertex][1])
            for vertex in vertices
        )
        right = clause[-1][0]
        if right - clause[0][0] > 15:
            raise ValueError("public C04 clause exceeds the supported frontier")
        clauses_by_right[right].append(tuple(clause))

    costs: list[tuple[int, int]] = []
    choice_edges: list[tuple[tuple[int, int], tuple[int, int]]] = []
    for center in order:
        root_edge, leaves = center_data[center]
        choice_edges.append(((root_edge[0], leaves[0][1]), (root_edge[0], leaves[1][1])))
        costs.append(
            (
                root_edge[1] + leaves[0][2],
                root_edge[1] + leaves[1][2],
            )
        )
    optimum, assignment = _solve_c04_frontier(
        costs=tuple(costs),
        clauses_by_right=tuple(tuple(row) for row in clauses_by_right),
        window_width=15,
    )
    selected = {
        edge_id for index, value in enumerate(assignment) for edge_id in choice_edges[index][value]
    }
    evaluation = evaluate_edge_set(public_instance, list(selected))
    if (
        optimum != budget
        or evaluation.cost != budget
        or not evaluation.connected
        or not evaluation.groups_hit
    ):
        raise ValueError("public C04 recovery failed exact validation")
    return tuple(sorted(selected))


def solve_public_c05(public_instance: Mapping[str, Any]) -> tuple[int, ...]:
    """Recover a public running-intersection bag tree and solve separator DP."""

    num_vertices = public_instance.get("num_vertices")
    root = public_instance.get("root")
    raw_edges = public_instance.get("edges")
    raw_groups = public_instance.get("groups")
    budget = public_instance.get("budget")
    if (
        isinstance(num_vertices, bool)
        or not isinstance(num_vertices, int)
        or isinstance(root, bool)
        or not isinstance(root, int)
        or not isinstance(raw_edges, list)
        or not isinstance(raw_groups, list)
        or isinstance(budget, bool)
        or not isinstance(budget, int)
    ):
        raise ValueError("malformed public C05 instance")
    adjacency: dict[int, list[tuple[int, int, int]]] = {
        vertex: [] for vertex in range(1, num_vertices + 1)
    }
    for raw_edge in raw_edges:
        if not isinstance(raw_edge, Mapping):
            raise ValueError("malformed public C05 edge")
        edge_id = raw_edge.get("edge_id")
        first = raw_edge.get("u")
        second = raw_edge.get("v")
        weight = raw_edge.get("weight")
        if not all(
            isinstance(value, int) and not isinstance(value, bool)
            for value in (edge_id, first, second, weight)
        ):
            raise ValueError("malformed public C05 edge fields")
        assert isinstance(edge_id, int) and isinstance(first, int)
        assert isinstance(second, int) and isinstance(weight, int)
        adjacency[first].append((second, edge_id, weight))
        adjacency[second].append((first, edge_id, weight))

    singleton_vertices: set[int] = set()
    groups_by_size: dict[int, list[tuple[int, ...]]] = {}
    for raw_group in raw_groups:
        if not isinstance(raw_group, Mapping) or not isinstance(raw_group.get("vertices"), list):
            raise ValueError("malformed public C05 group")
        vertices = raw_group["vertices"]
        if not vertices or not all(isinstance(vertex, int) for vertex in vertices):
            raise ValueError("malformed public C05 group vertices")
        groups_by_size.setdefault(len(vertices), []).append(tuple(vertices))
        if len(vertices) == 1:
            singleton_vertices.add(vertices[0])

    center_data: dict[
        int,
        tuple[
            tuple[int, int],
            tuple[tuple[int, int, int], tuple[int, int, int]],
        ],
    ] = {}
    choice_location: dict[int, tuple[int, int]] = {}
    for center in singleton_vertices:
        root_edges = [entry for entry in adjacency[center] if entry[0] == root]
        leaves = [entry for entry in adjacency[center] if len(adjacency[entry[0]]) == 1]
        if len(root_edges) != 1 or len(leaves) != 2 or len(adjacency[center]) != 3:
            raise ValueError("public C05 singleton does not identify a choice center")
        leaves.sort(key=lambda entry: entry[0])
        center_data[center] = (
            (root_edges[0][1], root_edges[0][2]),
            (leaves[0], leaves[1]),
        )
        choice_location[leaves[0][0]] = (center, 0)
        choice_location[leaves[1][0]] = (center, 1)
    if 1 + 3 * len(center_data) != num_vertices:
        raise ValueError("public C05 center decomposition does not cover the graph")

    requirement_centers: set[int] = set()
    for vertices in groups_by_size.get(2, []):
        if not all(vertex in choice_location for vertex in vertices):
            if all(vertex in center_data for vertex in vertices):
                continue
            raise ValueError("public C05 binary group is malformed")
        locations = [choice_location[vertex] for vertex in vertices]
        if locations[0][0] != locations[1][0] or locations[0][1] == locations[1][1]:
            raise ValueError("public C05 binary group is malformed")
        requirement_centers.add(locations[0][0])
    if requirement_centers != set(center_data):
        raise ValueError("public C05 does not require one choice at every center")

    center_only_groups = {
        size: [vertices for vertices in groups if all(vertex in center_data for vertex in vertices)]
        for size, groups in groups_by_size.items()
    }
    marker_sizes = sorted(
        size for size, groups in center_only_groups.items() if size > 1 and groups
    )
    if len(marker_sizes) < 2:
        raise ValueError("public C05 lacks distinct separator and bag markers")
    separator_size, bag_width = marker_sizes[-2], marker_sizes[-1]
    separator_markers = center_only_groups[separator_size]
    bag_markers = center_only_groups[bag_width]
    if not bag_markers:
        raise ValueError("public C05 has no bag markers")
    bags_as_centers: list[frozenset[int]] = []
    for marker in bag_markers:
        bags_as_centers.append(frozenset(marker))
    separators = []
    for marker in separator_markers:
        separators.append(frozenset(marker))

    bag_adjacency: list[set[int]] = [set() for _ in bags_as_centers]
    for separator in separators:
        containing = [index for index, bag in enumerate(bags_as_centers) if separator <= bag]
        if len(containing) != 2:
            raise ValueError("public C05 separator does not identify one bag edge")
        first, second = containing
        bag_adjacency[first].add(second)
        bag_adjacency[second].add(first)
    edge_count = sum(len(neighbors) for neighbors in bag_adjacency) // 2
    if edge_count != len(bags_as_centers) - 1:
        raise ValueError("public C05 bag graph is not a tree")
    root_bag = min(
        range(len(bags_as_centers)),
        key=lambda index: (len(bag_adjacency[index]), tuple(sorted(bags_as_centers[index]))),
    )
    order = [root_bag]
    parent_public = {root_bag: -1}
    for bag in order:
        for neighbor in sorted(bag_adjacency[bag]):
            if neighbor in parent_public:
                continue
            parent_public[neighbor] = bag
            order.append(neighbor)
    if len(order) != len(bags_as_centers):
        raise ValueError("public C05 bag tree is disconnected")
    new_index = {old: index for index, old in enumerate(order)}
    center_order = sorted(center_data)
    variable_of_center = {center: index for index, center in enumerate(center_order)}
    bags = tuple(
        tuple(sorted(variable_of_center[center] for center in bags_as_centers[old]))
        for old in order
    )
    parents = tuple(
        -1 if parent_public[old] == -1 else new_index[parent_public[old]] for old in order
    )
    home_candidates: dict[frozenset[int], list[int]] = {}
    for bag, variables in enumerate(bags):
        for size in (3, 4):
            for vertices in groups_by_size.get(size, []):
                if not all(vertex in choice_location for vertex in vertices):
                    continue
                clause_variables = frozenset(
                    variable_of_center[choice_location[vertex][0]] for vertex in vertices
                )
                if clause_variables <= set(variables):
                    home_candidates.setdefault(frozenset(vertices), []).append(bag)
    clauses_by_home: list[list[tuple[tuple[int, int], ...]]] = [[] for _ in bags]
    for size in (3, 4):
        for vertices in groups_by_size.get(size, []):
            if not all(vertex in choice_location for vertex in vertices):
                continue
            candidates = home_candidates.get(frozenset(vertices), [])
            if not candidates:
                raise ValueError("public C05 clause is not contained in a bag")
            home = max(
                candidates, key=lambda bag: sum(1 for parent in parents[: bag + 1] if parent >= 0)
            )
            clauses_by_home[home].append(
                tuple(
                    sorted(
                        (
                            variable_of_center[choice_location[vertex][0]],
                            choice_location[vertex][1],
                        )
                        for vertex in vertices
                    )
                )
            )

    costs: list[tuple[int, int]] = []
    choice_edges: list[tuple[tuple[int, int], tuple[int, int]]] = []
    for center in center_order:
        root_edge, leaves = center_data[center]
        choice_edges.append(((root_edge[0], leaves[0][1]), (root_edge[0], leaves[1][1])))
        costs.append(
            (
                root_edge[1] + leaves[0][2],
                root_edge[1] + leaves[1][2],
            )
        )
    optimum, assignment = _solve_c05_tree_decomposition(
        num_variables=len(center_order),
        bags=bags,
        parents=parents,
        costs=tuple(costs),
        clauses_by_home=tuple(tuple(row) for row in clauses_by_home),
    )
    selected = {
        edge_id
        for variable, value in enumerate(assignment)
        for edge_id in choice_edges[variable][value]
    }
    evaluation = evaluate_edge_set(public_instance, list(selected))
    if (
        optimum != budget
        or evaluation.cost != budget
        or not evaluation.connected
        or not evaluation.groups_hit
    ):
        raise ValueError("public C05 recovery failed exact validation")
    return tuple(sorted(selected))


def solve_public_c06(public_instance: Mapping[str, Any]) -> tuple[int, ...]:
    """Recover the deep routing tree and solve ancestor-window terminal DP."""

    num_vertices = public_instance.get("num_vertices")
    root = public_instance.get("root")
    raw_edges = public_instance.get("edges")
    raw_groups = public_instance.get("groups")
    budget = public_instance.get("budget")
    if (
        not all(
            isinstance(value, int) and not isinstance(value, bool)
            for value in (num_vertices, root, budget)
        )
        or not isinstance(raw_edges, list)
        or not isinstance(raw_groups, list)
    ):
        raise ValueError("malformed public C06 instance")
    assert isinstance(num_vertices, int) and isinstance(root, int) and isinstance(budget, int)
    adjacency: dict[int, list[tuple[int, int, int]]] = {
        vertex: [] for vertex in range(1, num_vertices + 1)
    }
    for edge in raw_edges:
        if not isinstance(edge, Mapping):
            raise ValueError("malformed public C06 edge")
        edge_id, first, second, weight = (edge.get(key) for key in ("edge_id", "u", "v", "weight"))
        if not all(
            isinstance(value, int) and not isinstance(value, bool)
            for value in (edge_id, first, second, weight)
        ):
            raise ValueError("malformed public C06 edge fields")
        assert (
            isinstance(edge_id, int)
            and isinstance(first, int)
            and isinstance(second, int)
            and isinstance(weight, int)
        )
        adjacency[first].append((second, edge_id, weight))
        adjacency[second].append((first, edge_id, weight))

    terminal_groups = []
    other_groups = []
    for group in raw_groups:
        if not isinstance(group, Mapping) or not isinstance(group.get("vertices"), list):
            raise ValueError("malformed public C06 group")
        vertices = tuple(group["vertices"])
        if (
            len(vertices) == 2
            and all(len(adjacency[vertex]) == 1 for vertex in vertices)
            and adjacency[vertices[0]][0][0] == adjacency[vertices[1]][0][0]
        ):
            terminal_groups.append(vertices)
        else:
            other_groups.append(vertices)
    terminal_vertices = {vertex for pair in terminal_groups for vertex in pair}
    tree_vertices = sorted(set(range(1, num_vertices + 1)) - terminal_vertices)
    tree_adjacency: dict[int, list[tuple[int, int, int]]] = {vertex: [] for vertex in tree_vertices}
    terminal_edge: dict[int, tuple[int, int, int]] = {}
    for vertex in tree_vertices:
        for neighbor, edge_id, weight in adjacency[vertex]:
            if neighbor in terminal_vertices:
                terminal_edge[neighbor] = (vertex, edge_id, weight)
            elif neighbor in tree_adjacency:
                tree_adjacency[vertex].append((neighbor, edge_id, weight))
    parent: dict[int, int] = {root: -1}
    parent_edge: dict[int, int] = {}
    order = [root]
    for vertex in order:
        for neighbor, edge_id, _weight in tree_adjacency[vertex]:
            if neighbor in parent:
                continue
            parent[neighbor] = vertex
            parent_edge[neighbor] = edge_id
            order.append(neighbor)
    if len(order) != len(tree_vertices):
        raise ValueError("public C06 routing tree is disconnected")
    terminals_by_tree: dict[int, tuple[int, int]] = {}
    for pair in terminal_groups:
        owners = {terminal_edge[terminal][0] for terminal in pair}
        if len(owners) != 1:
            raise ValueError("public C06 terminal pair has different owners")
        owner = next(iter(owners))
        terminals_by_tree[owner] = tuple(sorted(pair))
    if set(terminals_by_tree) != set(tree_vertices):
        raise ValueError("public C06 does not give one terminal pair per routing vertex")
    tree_index = {vertex: index for index, vertex in enumerate(order)}
    clauses_by_node: list[list[tuple[tuple[int, int], ...]]] = [[] for _ in order]
    terminal_location = {
        terminal: (tree_index[owner], value)
        for owner, pair in terminals_by_tree.items()
        for value, terminal in enumerate(pair)
    }
    for vertices in other_groups:
        if not vertices or not all(vertex in terminal_location for vertex in vertices):
            raise ValueError("public C06 higher group contains a nonterminal")
        clause = tuple(terminal_location[vertex] for vertex in vertices)
        home = max(variable for variable, _value in clause)
        clauses_by_node[home].append(clause)
    children: list[list[int]] = [[] for _ in order]
    for vertex in order[1:]:
        children[tree_index[parent[vertex]]].append(tree_index[vertex])
    terminals = tuple(terminals_by_tree[vertex] for vertex in order)
    memo: dict[tuple[int, tuple[int, ...]], int] = {}
    choice: dict[tuple[int, tuple[int, ...]], int] = {}
    infinity = 10**30

    def cost(node: int, ancestors: tuple[int, ...]) -> int:
        key = (node, ancestors)
        if key in memo:
            return memo[key]
        ancestor_nodes = []
        current_vertex = parent[order[node]]
        while current_vertex >= 0 and len(ancestor_nodes) < len(ancestors):
            ancestor_nodes.append(tree_index[current_vertex])
            current_vertex = parent[current_vertex]
        known = dict(zip(ancestor_nodes, ancestors, strict=True))
        best: tuple[int, int] | None = None
        for value, terminal in enumerate(terminals[node]):
            known[node] = value
            if any(
                not any(known.get(variable) == literal for variable, literal in clause)
                for clause in clauses_by_node[node]
            ):
                continue
            next_ancestors = (value, *ancestors)[:9]
            candidate = terminal_edge[terminal][2] + sum(
                cost(child, next_ancestors) for child in children[node]
            )
            if best is None or (candidate, value) < best:
                best = (candidate, value)
        if best is None:
            memo[key] = infinity
            return infinity
        memo[key], choice[key] = best
        return best[0]

    routing_cost = sum(
        next(edge[2] for edge in tree_adjacency[vertex] if edge[0] == parent[vertex])
        for vertex in order[1:]
    )
    terminal_cost = cost(0, ())
    if terminal_cost >= infinity:
        raise ValueError("public C06 terminal model is infeasible")
    optimum = routing_cost + terminal_cost
    selected = set(parent_edge.values())

    def recover(node: int, ancestors: tuple[int, ...]) -> None:
        value = choice[(node, ancestors)]
        selected.add(terminal_edge[terminals[node][value]][1])
        next_ancestors = (value, *ancestors)[:9]
        for child in children[node]:
            recover(child, next_ancestors)

    recover(0, ())
    evaluation = evaluate_edge_set(public_instance, list(selected))
    if (
        optimum != budget
        or evaluation.cost != budget
        or not evaluation.connected
        or not evaluation.groups_hit
    ):
        raise ValueError("public C06 recovery failed exact validation")
    return tuple(sorted(selected))


def solve_public(public_instance: Mapping[str, Any]) -> tuple[int, ...]:
    """Dispatch by participant-visible graph and group invariants."""

    raw_groups = public_instance.get("groups")
    if not isinstance(raw_groups, list):
        raise ValueError("malformed public group table")
    has_pair = any(
        isinstance(group, Mapping)
        and isinstance(group.get("vertices"), list)
        and len(group["vertices"]) == 2
        for group in raw_groups
    )
    if not has_pair:
        return solve_public_c01(public_instance)
    num_vertices = public_instance.get("num_vertices")
    root = public_instance.get("root")
    raw_edges = public_instance.get("edges")
    root_degree = (
        sum(
            1
            for edge in raw_edges
            if isinstance(edge, Mapping) and root in (edge.get("u"), edge.get("v"))
        )
        if isinstance(root, int) and isinstance(raw_edges, list)
        else -1
    )
    if any(
        isinstance(group, Mapping)
        and isinstance(group.get("vertices"), list)
        and len(group["vertices"]) >= 3
        for group in raw_groups
    ):
        if root_degree == 4:
            return solve_public_c06(public_instance)
        if any(
            isinstance(group, Mapping)
            and isinstance(group.get("vertices"), list)
            and len(group["vertices"]) >= 6
            for group in raw_groups
        ):
            return solve_public_c05(public_instance)
        return solve_public_c04(public_instance)
    if (
        isinstance(num_vertices, int)
        and isinstance(root, int)
        and isinstance(raw_edges, list)
        and root_degree * 3 + 1 == num_vertices
    ):
        return solve_public_c03(public_instance)
    return solve_public_c02(public_instance)


def _participant_instance(client: ParticipantClient) -> Mapping[str, Any]:
    response = client.get_instance()
    nested = response.get("public_instance")
    return nested if isinstance(nested, Mapping) else response


class HonestNewGroupSteinerAgent:
    agent_id = "virtual-honest"

    def run(self, *, client: ParticipantClient, workspace: Path) -> None:
        del workspace
        client.submit_event(
            sequence=0,
            kind=EDGE_SET_EVENT_KIND,
            payload={"edge_ids": list(solve_public(_participant_instance(client)))},
        )


_VIRTUAL_AGENT_LIST: Final[tuple[VirtualAgent, ...]] = (
    HonestNewGroupSteinerAgent(),
    *SHARED_VIRTUAL_AGENTS.values(),
)
VIRTUAL_AGENTS: Final[Mapping[str, VirtualAgent]] = {
    agent.agent_id: agent for agent in _VIRTUAL_AGENT_LIST
}


@dataclass(frozen=True)
class NewRootedGroupSteinerTaskPlugin:
    manifest: Mapping[str, Any]
    case_parameters: Mapping[str, Mapping[str, Any]]
    generator: NewRootedGroupSteinerGenerator
    protocol: NewRootedGroupSteinerProtocol


def create_task() -> NewRootedGroupSteinerTaskPlugin:
    return NewRootedGroupSteinerTaskPlugin(
        manifest=TASK_MANIFEST,
        case_parameters=CASE_PARAMETERS,
        generator=NewRootedGroupSteinerGenerator(),
        protocol=NewRootedGroupSteinerProtocol(),
    )


__all__ = [
    "CASE_IDS",
    "CASE_PARAMETERS",
    "EDGE_SET_EVENT_KIND",
    "GroupSteinerProtocolState",
    "GroupSteinerReason",
    "NewRootedGroupSteinerGenerator",
    "NewRootedGroupSteinerProtocol",
    "TASK_ID",
    "TASK_MANIFEST",
    "TASK_VERSION",
    "VIRTUAL_AGENTS",
    "create_task",
    "evaluate_edge_set",
    "solve_public",
    "solve_public_c01",
    "solve_public_c02",
    "solve_public_c03",
    "solve_public_c04",
    "solve_public_c05",
    "solve_public_c06",
]
