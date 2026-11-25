"""Independent 600-second Structured Set Cover task."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from aipbench.core.models import GeneratedCase
from aipbench.core.protocol import ParticipantClient, VirtualAgent
from aipbench.tasks.new_set_cover_cases import (
    CASE_DEFINITIONS,
    CASE_PARAMETERS,
    NewSetCoverStream,
    finalize_blueprint,
)
from aipbench.tasks.new_set_cover_cases.c02 import minimum_weight_cycle_vertex_cover
from aipbench.tasks.shared.structured_set_cover import (
    SELECTION_EVENT_KIND,
    SetCoverProtocolState,
    SetCoverReason,
    StructuredSetCoverProtocol,
    evaluate_selection,
)
from aipbench.tasks.shared.structured_set_cover import (
    VIRTUAL_AGENTS as SHARED_VIRTUAL_AGENTS,
)

TASK_ID: Final = "t1.new_structured_set_cover"
TASK_VERSION: Final = "0.1.0"
CASE_IDS: Final = tuple(CASE_PARAMETERS)

TASK_MANIFEST: Final[Mapping[str, Any]] = {
    "id": TASK_ID,
    "version": TASK_VERSION,
    "tier": 1,
    "title": "New Structured Set Cover",
    "plugin": {"entrypoint": "aipbench.tasks.new_structured_set_cover:create_task"},
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
            "tasks/tier1_np/new_structured_set_cover/schemas/public_instance.schema.json"
        ),
        "private_schema": (
            "tasks/tier1_np/new_structured_set_cover/schemas/private_instance.schema.json"
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
    "scoring": {"primary": "binary_accept", "partial_progress": "set_selection_submitted"},
    "soundness": {
        "class": "deterministic_certificate",
        "statement": (
            "the submitted distinct public set IDs have total weight at most the public "
            "budget and their union covers every public universe element"
        ),
    },
}


class NewStructuredSetCoverGenerator:
    def generate(
        self,
        *,
        instance_seed: bytes,
        case_id: str,
        case_parameters: Mapping[str, Any],
    ) -> GeneratedCase:
        if not isinstance(instance_seed, bytes):
            raise TypeError("instance_seed must be bytes")
        definition = CASE_DEFINITIONS.get(case_id)
        if definition is None:
            raise ValueError(f"unsupported new structured-set-cover case: {case_id}")
        parameters = dict(definition.parameters)
        parameters.update(case_parameters)
        stream = NewSetCoverStream(instance_seed)
        finalized = finalize_blueprint(
            blueprint=definition.builder(stream, parameters), stream=stream
        )
        return GeneratedCase(
            task_id=TASK_ID,
            task_version=TASK_VERSION,
            case_id=case_id,
            public_instance=finalized.public_instance,
            private_instance=finalized.private_instance,
            generation_metadata={
                **dict(finalized.generation_metadata),
                "generator": f"new-structured-set-cover/{case_id}/v1",
                "case_id": case_id,
            },
        )


class NewStructuredSetCoverProtocol(StructuredSetCoverProtocol):
    task_id = TASK_ID
    task_version = TASK_VERSION

    @staticmethod
    def _validate_task_identity(generated_case: GeneratedCase) -> None:
        if generated_case.task_id != TASK_ID or generated_case.task_version != TASK_VERSION:
            raise ValueError("generated case does not belong to the new Set Cover task")

    def public_protocol_description(self, *, generated_case: GeneratedCase) -> Mapping[str, Any]:
        description = dict(super().public_protocol_description(generated_case=generated_case))
        description["event_schemas"] = {
            SELECTION_EVENT_KIND: {
                "schema_ref": (
                    "tasks/tier1_np/new_structured_set_cover/schemas/selection.schema.json"
                )
            }
        }
        return description


def solve_public_c01(public_instance: Mapping[str, Any]) -> tuple[int, ...]:
    """Recover C01's exact cover using public incidences and verify it independently."""

    raw_sets = public_instance.get("sets")
    if not isinstance(raw_sets, list):
        raise ValueError("malformed public set family")
    candidates: list[tuple[int, frozenset[int]]] = []
    for raw_set in raw_sets:
        if not isinstance(raw_set, Mapping):
            raise ValueError("malformed public candidate")
        set_id = raw_set.get("set_id")
        elements = raw_set.get("elements")
        if (
            isinstance(set_id, bool)
            or not isinstance(set_id, int)
            or not isinstance(elements, list)
        ):
            raise ValueError("malformed public candidate fields")
        candidates.append((set_id, frozenset(elements)))
    selected = tuple(
        set_id
        for set_id, elements in candidates
        if not any(elements < other_elements for _, other_elements in candidates)
    )
    evaluation = evaluate_selection(public_instance, list(selected))
    budget = public_instance.get("budget")
    if not evaluation.covers_universe or evaluation.total_weight > budget:
        raise ValueError("public C01 recovery did not produce an accepted selection")
    return selected


def solve_public_c02(public_instance: Mapping[str, Any]) -> tuple[int, ...]:
    """Recover the public candidate cycle and solve its exact weighted cover."""

    raw_sets = public_instance.get("sets")
    if not isinstance(raw_sets, list) or len(raw_sets) < 3:
        raise ValueError("malformed public cycle family")
    weights: dict[int, int] = {}
    incident: dict[int, list[int]] = {}
    for raw_set in raw_sets:
        if not isinstance(raw_set, Mapping):
            raise ValueError("malformed public candidate")
        set_id = raw_set.get("set_id")
        weight = raw_set.get("weight")
        elements = raw_set.get("elements")
        if (
            isinstance(set_id, bool)
            or not isinstance(set_id, int)
            or isinstance(weight, bool)
            or not isinstance(weight, int)
            or not isinstance(elements, list)
            or len(elements) != 2
        ):
            raise ValueError("malformed public cycle candidate")
        weights[set_id] = weight
        for element in elements:
            incident.setdefault(element, []).append(set_id)
    if len(weights) != len(raw_sets) or any(len(ids) != 2 for ids in incident.values()):
        raise ValueError("public incidences do not form a candidate cycle")

    adjacency = {set_id: set() for set_id in weights}
    for left, right in incident.values():
        adjacency[left].add(right)
        adjacency[right].add(left)
    if any(len(neighbors) != 2 for neighbors in adjacency.values()):
        raise ValueError("public candidate graph is not a cycle")
    start = min(weights)
    order = [start]
    previous: int | None = None
    current = start
    while True:
        onward = sorted(neighbor for neighbor in adjacency[current] if neighbor != previous)
        following = onward[0]
        if following == start:
            break
        if following in order:
            raise ValueError("public candidate graph is not a single cycle")
        order.append(following)
        previous, current = current, following
    if len(order) != len(weights):
        raise ValueError("public candidate graph is disconnected")
    selected_indices = minimum_weight_cycle_vertex_cover([weights[set_id] for set_id in order])
    selected = tuple(order[index] for index in selected_indices)
    evaluation = evaluate_selection(public_instance, list(selected))
    budget = public_instance.get("budget")
    if not evaluation.covers_universe or evaluation.total_weight != budget:
        raise ValueError("public C02 recovery did not attain the exact budget")
    return selected


def _parse_public_candidates(
    public_instance: Mapping[str, Any],
) -> tuple[dict[int, int], dict[int, frozenset[int]], dict[int, tuple[int, ...]]]:
    raw_sets = public_instance.get("sets")
    if not isinstance(raw_sets, list):
        raise ValueError("malformed public set family")
    weights: dict[int, int] = {}
    incidence: dict[int, frozenset[int]] = {}
    by_element: dict[int, list[int]] = {}
    for raw_set in raw_sets:
        if not isinstance(raw_set, Mapping):
            raise ValueError("malformed public candidate")
        set_id = raw_set.get("set_id")
        weight = raw_set.get("weight")
        elements = raw_set.get("elements")
        if (
            isinstance(set_id, bool)
            or not isinstance(set_id, int)
            or isinstance(weight, bool)
            or not isinstance(weight, int)
            or not isinstance(elements, list)
        ):
            raise ValueError("malformed public candidate fields")
        weights[set_id] = weight
        incidence[set_id] = frozenset(elements)
        for element in elements:
            by_element.setdefault(element, []).append(set_id)
    return weights, incidence, {element: tuple(ids) for element, ids in by_element.items()}


def solve_public_c03(public_instance: Mapping[str, Any]) -> tuple[int, ...]:
    """Recover C03's selector pairs and use public clauses for exact search."""

    weights, incidence, by_element = _parse_public_candidates(public_instance)
    marker_ids = {ids[0] for ids in by_element.values() if len(ids) == 1}
    selector_elements = {
        element: ids
        for element, ids in by_element.items()
        if len(ids) == 2
        and ids[0] != ids[1]
        and weights.get(ids[0]) == weights.get(ids[1])
        and ids[0] not in marker_ids
        and ids[1] not in marker_ids
    }
    pairs = tuple(selector_elements.values())
    if 2 * len(pairs) + len(marker_ids) != len(weights):
        raise ValueError("public C03 selectors are not uniquely recoverable")
    candidate_to_variable: dict[int, tuple[int, int]] = {}
    ordered_pairs: list[tuple[int, int]] = []
    for variable, pair in enumerate(sorted(tuple(sorted(pair)) for pair in pairs)):
        ordered_pairs.append(pair)
        candidate_to_variable[pair[0]] = (variable, 0)
        candidate_to_variable[pair[1]] = (variable, 1)

    clauses: list[tuple[tuple[int, int], ...]] = []
    marker_groups_by_id: dict[int, list[tuple[tuple[int, int], ...]]] = {
        marker_id: [] for marker_id in marker_ids
    }
    for element, ids in by_element.items():
        nonmarkers = tuple(set_id for set_id in ids if set_id not in marker_ids)
        if element in selector_elements or not nonmarkers:
            continue
        clause = tuple(candidate_to_variable[set_id] for set_id in nonmarkers)
        if len({variable for variable, _bit in clause}) != len(clause):
            raise ValueError("public C03 clause repeats a selector")
        clauses.append(clause)
        attached = [set_id for set_id in ids if set_id in marker_ids]
        if len(attached) != 1:
            raise ValueError("public C03 clause lacks a unique marker")
        marker_groups_by_id[attached[0]].append(clause)

    local_groups = [
        grouped
        for grouped in marker_groups_by_id.values()
        if grouped and all(len(clause) == 3 for clause in grouped)
    ]
    boundary_groups = [
        grouped
        for grouped in marker_groups_by_id.values()
        if grouped
        and {len(clause) for clause in grouped} <= {2, 4}
        and 4 in {len(clause) for clause in grouped}
    ]
    blocks = [
        {variable for clause in grouped for variable, _bit in clause} for grouped in local_groups
    ]
    if any(len(block) != 12 for block in blocks) or len(blocks) * 12 != len(pairs):
        raise ValueError("public C03 marker groups do not recover width-12 blocks")
    block_of: dict[int, int] = {}
    marker_groups: dict[tuple[int, ...], list[tuple[tuple[int, int], ...]]] = {}
    for block_index, (block, grouped) in enumerate(zip(blocks, local_groups, strict=True)):
        for variable in block:
            if variable in block_of:
                raise ValueError("public C03 recovered overlapping blocks")
            block_of[variable] = block_index
        marker_groups[(block_index,)] = grouped
    block_graph = {index: set() for index in range(len(blocks))}
    for grouped in boundary_groups:
        touched = tuple(
            sorted({block_of[variable] for clause in grouped for variable, _bit in clause})
        )
        if len(touched) != 2:
            raise ValueError("public C03 boundary marker does not join two blocks")
        marker_groups[touched] = grouped
        left, right = touched
        block_graph[left].add(right)
        block_graph[right].add(left)
    endpoints = sorted(block for block, neighbors in block_graph.items() if len(neighbors) == 1)
    if len(endpoints) != 2 or any(
        len(neighbors) not in {1, 2} for neighbors in block_graph.values()
    ):
        raise ValueError("public C03 recovered block graph is not a path")
    order = [endpoints[0]]
    while len(order) < len(blocks):
        onward = block_graph[order[-1]] - set(order)
        if len(onward) != 1:
            raise ValueError("public C03 path traversal failed")
        order.append(next(iter(onward)))

    first_variables = sorted(blocks[order[0]])
    first_states: list[dict[int, int]] = []
    first_local = marker_groups.get((order[0],), ())
    for mask in range(1 << len(first_variables)):
        trial = {
            variable: (mask >> position) & 1 for position, variable in enumerate(first_variables)
        }
        if all(any(trial[variable] == bit for variable, bit in clause) for clause in first_local):
            first_states.append(trial)
    active: list[dict[int, int]] = first_states
    for left, right in zip(order, order[1:], strict=False):
        right_variables = sorted(blocks[right])
        local = marker_groups.get((right,), ())
        boundary_key = tuple(sorted((left, right)))
        cross = marker_groups.get(boundary_key, ())
        next_active: list[dict[int, int]] = []
        seen_masks: set[int] = set()
        for state in active:
            for mask in range(1 << len(right_variables)):
                trial = {
                    variable: (mask >> position) & 1
                    for position, variable in enumerate(right_variables)
                }
                combined = {**state, **trial}
                if mask not in seen_masks and all(
                    any(combined[variable] == bit for variable, bit in clause)
                    for clause in (*local, *cross)
                ):
                    seen_masks.add(mask)
                    next_active.append(combined)
        active = next_active
        if not active:
            break
    solution = active[0] if active else None
    if solution is None:
        raise ValueError("public C03 chain propagation failed")
    selected = tuple(
        ordered_pairs[variable][bit] for variable, bit in sorted(solution.items())
    ) + tuple(sorted(marker_ids))
    evaluation = evaluate_selection(public_instance, list(selected))
    if not evaluation.covers_universe or evaluation.total_weight != public_instance.get("budget"):
        raise ValueError("public C03 recovery did not attain the exact budget")
    return selected


def _solve_public_marked_hitting_path(
    public_instance: Mapping[str, Any], *, expected_width: int, expected_overlap: int
) -> tuple[int, ...]:
    """Recover a marked bag path and solve it by separator DP."""

    from aipbench.tasks.new_set_cover_cases.c04 import solve_weighted_bag_path

    weights, _incidence, by_element = _parse_public_candidates(public_instance)
    budget = public_instance.get("budget")
    if not isinstance(budget, int):
        raise ValueError("public C04 budget is malformed")
    marker_ids = {set_id for set_id, weight in weights.items() if weight > budget}
    if not marker_ids:
        raise ValueError("public C04 has no recoverable group labels")
    variables = sorted(set(weights) - marker_ids)
    variable_of = {set_id: index for index, set_id in enumerate(variables)}
    groups: list[tuple[set[int], tuple[tuple[int, ...], ...]]] = []
    for marker_id in marker_ids:
        clauses = []
        for ids in by_element.values():
            if marker_id not in ids:
                continue
            clause = tuple(variable_of[set_id] for set_id in ids if set_id != marker_id)
            if not clause:
                raise ValueError("public C04 group marker has an empty clause")
            clauses.append(clause)
        bag = {variable for clause in clauses for variable in clause}
        if len(bag) != expected_width:
            raise ValueError("public group does not expose the expected bag width")
        groups.append((bag, tuple(clauses)))
    adjacency = {index: set() for index in range(len(groups))}
    for left in range(len(groups)):
        for right in range(left + 1, len(groups)):
            if len(groups[left][0] & groups[right][0]) == expected_overlap:
                adjacency[left].add(right)
                adjacency[right].add(left)
    endpoints = sorted(index for index, neighbors in adjacency.items() if len(neighbors) == 1)
    if len(endpoints) != 2 or any(len(neighbors) not in {1, 2} for neighbors in adjacency.values()):
        raise ValueError("public recovered group graph is not a path")
    order = [endpoints[0]]
    while len(order) < len(groups):
        onward = adjacency[order[-1]] - set(order)
        if len(onward) != 1:
            raise ValueError("public group traversal failed")
        order.append(next(iter(onward)))
    selected_variables = solve_weighted_bag_path(
        bags=[tuple(sorted(groups[index][0])) for index in order],
        clauses_by_bag=[groups[index][1] for index in order],
        weights=[weights[set_id] for set_id in variables],
    )
    selected = tuple(variables[index] for index in selected_variables)
    evaluation = evaluate_selection(public_instance, list(selected))
    if not evaluation.covers_universe or evaluation.total_weight != public_instance.get("budget"):
        raise ValueError("public marked-path recovery did not attain the exact budget")
    return selected


def solve_public_c04(public_instance: Mapping[str, Any]) -> tuple[int, ...]:
    """Recover C04's width-16 marked bag path and solve it exactly."""

    return _solve_public_marked_hitting_path(public_instance, expected_width=16, expected_overlap=8)


def solve_public_c05(public_instance: Mapping[str, Any]) -> tuple[int, ...]:
    """Recover C05's width-18 marked bag path and solve it exactly."""

    return _solve_public_marked_hitting_path(public_instance, expected_width=18, expected_overlap=9)


def solve_public_c06(public_instance: Mapping[str, Any]) -> tuple[int, ...]:
    """Recover C06's width-16 bag tree and solve it exactly."""

    from aipbench.tasks.new_set_cover_cases.c06 import solve_weighted_bag_tree

    weights, _incidence, by_element = _parse_public_candidates(public_instance)
    budget = public_instance.get("budget")
    if not isinstance(budget, int):
        raise ValueError("public C06 budget is malformed")
    marker_ids = {set_id for set_id, weight in weights.items() if weight > budget}
    variables = sorted(set(weights) - marker_ids)
    variable_of = {set_id: index for index, set_id in enumerate(variables)}
    groups: list[tuple[set[int], tuple[tuple[int, ...], ...]]] = []
    for marker_id in marker_ids:
        clauses = []
        for ids in by_element.values():
            if marker_id in ids:
                clause = tuple(variable_of[set_id] for set_id in ids if set_id != marker_id)
                if clause:
                    clauses.append(clause)
        bag = {variable for clause in clauses for variable in clause}
        if len(bag) != 16:
            raise ValueError("public C06 group does not expose a width-16 bag")
        groups.append((bag, tuple(clauses)))
    adjacency = {index: set() for index in range(len(groups))}
    for left in range(len(groups)):
        for right in range(left + 1, len(groups)):
            if len(groups[left][0] & groups[right][0]) == 6:
                adjacency[left].add(right)
                adjacency[right].add(left)
    if sum(len(neighbors) for neighbors in adjacency.values()) // 2 != len(groups) - 1:
        raise ValueError("public C06 group graph is not a tree")
    roots = sorted(index for index, neighbors in adjacency.items() if len(neighbors) == 3)
    root = roots[0] if roots else min(adjacency)
    order = [root]
    parent_by_old = {root: -1}
    for node in order:
        for neighbor in sorted(adjacency[node]):
            if neighbor != parent_by_old[node]:
                if neighbor in parent_by_old:
                    raise ValueError("public C06 group graph contains a cycle")
                parent_by_old[neighbor] = node
                order.append(neighbor)
    if len(order) != len(groups):
        raise ValueError("public C06 group graph is disconnected")
    new_index = {old: index for index, old in enumerate(order)}
    parents = tuple(
        -1 if parent_by_old[old] < 0 else new_index[parent_by_old[old]] for old in order
    )
    selected_variables = solve_weighted_bag_tree(
        bags=[tuple(sorted(groups[index][0])) for index in order],
        clauses_by_bag=[groups[index][1] for index in order],
        parents=parents,
        weights=[weights[set_id] for set_id in variables],
    )
    selected = tuple(variables[index] for index in selected_variables)
    evaluation = evaluate_selection(public_instance, list(selected))
    if not evaluation.covers_universe or evaluation.total_weight != budget:
        raise ValueError("public C06 recovery did not attain the exact budget")
    return selected


def solve_public(public_instance: Mapping[str, Any]) -> tuple[int, ...]:
    """Dispatch the public-only reference for the implemented profiles."""

    raw_sets = public_instance.get("sets")
    if isinstance(raw_sets, list) and any(
        isinstance(raw_set, Mapping)
        and isinstance(raw_set.get("weight"), int)
        and isinstance(public_instance.get("budget"), int)
        and raw_set["weight"] > public_instance["budget"]
        for raw_set in raw_sets
    ):
        marker_sets = [
            raw_set
            for raw_set in raw_sets
            if isinstance(raw_set, Mapping)
            and isinstance(raw_set.get("weight"), int)
            and isinstance(public_instance.get("budget"), int)
            and raw_set["weight"] > public_instance["budget"]
        ]
        marker_elements = set(marker_sets[0].get("elements", ()))
        variables_in_group = {
            raw_set.get("set_id")
            for raw_set in raw_sets
            if raw_set not in marker_sets and marker_elements & set(raw_set.get("elements", ()))
        }
        if len(variables_in_group) == 18:
            return solve_public_c05(public_instance)
        return (
            solve_public_c06(public_instance)
            if len(marker_sets) == 109
            else solve_public_c04(public_instance)
        )
    if (
        isinstance(raw_sets, list)
        and len(raw_sets) >= 2_000
        and any(
            isinstance(raw_set, Mapping)
            and isinstance(raw_set.get("elements"), list)
            and len(raw_set["elements"]) > 2
            for raw_set in raw_sets
        )
    ):
        return solve_public_c03(public_instance)
    if (
        isinstance(raw_sets, list)
        and len(raw_sets) >= 1_000
        and any(
            isinstance(raw_set, Mapping)
            and isinstance(raw_set.get("elements"), list)
            and len(raw_set["elements"]) > 2
            for raw_set in raw_sets
        )
    ):
        return solve_public_c03(public_instance)
    if (
        isinstance(raw_sets, list)
        and raw_sets
        and all(
            isinstance(raw_set, Mapping)
            and isinstance(raw_set.get("elements"), list)
            and len(raw_set["elements"]) == 2
            for raw_set in raw_sets
        )
    ):
        return solve_public_c02(public_instance)
    return solve_public_c01(public_instance)


def _participant_instance(client: ParticipantClient) -> Mapping[str, Any]:
    response = client.get_instance()
    nested = response.get("public_instance")
    return nested if isinstance(nested, Mapping) else response


class HonestNewSetCoverAgent:
    agent_id = "virtual-honest"

    def run(self, *, client: ParticipantClient, workspace: Path) -> None:
        del workspace
        selection = solve_public(_participant_instance(client))
        client.submit_event(
            sequence=0,
            kind=SELECTION_EVENT_KIND,
            payload={"set_ids": list(selection)},
        )


_VIRTUAL_AGENT_LIST: Final[tuple[VirtualAgent, ...]] = (
    HonestNewSetCoverAgent(),
    *(agent for agent_id, agent in SHARED_VIRTUAL_AGENTS.items() if agent_id != "virtual-honest"),
)
VIRTUAL_AGENTS: Final[Mapping[str, VirtualAgent]] = {
    agent.agent_id: agent for agent in _VIRTUAL_AGENT_LIST
}


@dataclass(frozen=True)
class NewStructuredSetCoverTaskPlugin:
    manifest: Mapping[str, Any]
    case_parameters: Mapping[str, Mapping[str, Any]]
    generator: NewStructuredSetCoverGenerator
    protocol: NewStructuredSetCoverProtocol


def create_task() -> NewStructuredSetCoverTaskPlugin:
    return NewStructuredSetCoverTaskPlugin(
        manifest=TASK_MANIFEST,
        case_parameters=CASE_PARAMETERS,
        generator=NewStructuredSetCoverGenerator(),
        protocol=NewStructuredSetCoverProtocol(),
    )


__all__ = [
    "CASE_IDS",
    "CASE_PARAMETERS",
    "NewStructuredSetCoverGenerator",
    "NewStructuredSetCoverProtocol",
    "NewStructuredSetCoverTaskPlugin",
    "SELECTION_EVENT_KIND",
    "SetCoverProtocolState",
    "SetCoverReason",
    "TASK_ID",
    "TASK_MANIFEST",
    "TASK_VERSION",
    "VIRTUAL_AGENTS",
    "create_task",
    "evaluate_selection",
    "solve_public",
    "solve_public_c01",
    "solve_public_c02",
    "solve_public_c03",
    "solve_public_c04",
    "solve_public_c05",
    "solve_public_c06",
]
