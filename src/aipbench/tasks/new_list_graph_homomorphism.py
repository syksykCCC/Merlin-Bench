"""Independent 600-second List Graph Homomorphism task."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from aipbench.core.models import GeneratedCase
from aipbench.core.protocol import ParticipantClient, VirtualAgent
from aipbench.tasks.new_homomorphism_cases import (
    CASE_DEFINITIONS,
    CASE_PARAMETERS,
    NewHomomorphismStream,
)
from aipbench.tasks.shared.homomorphism_cases.common import finalize_blueprint
from aipbench.tasks.shared.list_graph_homomorphism import (
    MAPPING_EVENT_KIND,
    HomomorphismProtocolState,
    HomomorphismReason,
    ListGraphHomomorphismProtocol,
    evaluate_mapping,
)
from aipbench.tasks.shared.list_graph_homomorphism import (
    VIRTUAL_AGENTS as SHARED_VIRTUAL_AGENTS,
)

TASK_ID: Final = "t1.new_list_graph_homomorphism"
TASK_VERSION: Final = "0.1.0"
CASE_IDS: Final = tuple(CASE_PARAMETERS)

TASK_MANIFEST: Final[Mapping[str, Any]] = {
    "id": TASK_ID,
    "version": TASK_VERSION,
    "tier": 1,
    "title": "New List Graph Homomorphism",
    "plugin": {"entrypoint": "aipbench.tasks.new_list_graph_homomorphism:create_task"},
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
            "tasks/tier1_np/new_list_graph_homomorphism/schemas/public_instance.schema.json"
        ),
        "private_schema": (
            "tasks/tier1_np/new_list_graph_homomorphism/schemas/private_instance.schema.json"
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
    "scoring": {"primary": "binary_accept", "partial_progress": "mapping_submitted"},
    "soundness": {
        "class": "deterministic_certificate",
        "statement": (
            "every source vertex maps into its public list and every source edge "
            "maps to a public target edge"
        ),
    },
}


class NewListGraphHomomorphismGenerator:
    """Generate independently domain-separated cases."""

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
            raise ValueError(f"unsupported new list homomorphism case: {case_id}")
        parameters = dict(definition.parameters)
        parameters.update(case_parameters)
        stream = NewHomomorphismStream(instance_seed)
        blueprint = definition.builder(stream, parameters)
        finalized = finalize_blueprint(case_id=case_id, blueprint=blueprint, stream=stream)
        return GeneratedCase(
            task_id=TASK_ID,
            task_version=TASK_VERSION,
            case_id=case_id,
            public_instance=finalized.public_instance,
            private_instance=finalized.private_instance,
            generation_metadata=finalized.generation_metadata,
        )


class NewListGraphHomomorphismProtocol(ListGraphHomomorphismProtocol):
    """The established public relation under the independent task identity."""

    task_id = TASK_ID
    task_version = TASK_VERSION
    event_schema_ref = "tasks/tier1_np/new_list_graph_homomorphism/schemas/mapping.schema.json"


def solve_public_tree_constraints(public_instance: Mapping[str, Any]) -> tuple[int, ...]:
    """Recover a unique mapping by propagation through source-tree components."""

    source_count = public_instance.get("source_num_vertices")
    target_count = public_instance.get("target_num_vertices")
    raw_source_edges = public_instance.get("source_edges")
    raw_target_edges = public_instance.get("target_edges")
    raw_lists = public_instance.get("lists")
    if (
        isinstance(source_count, bool)
        or not isinstance(source_count, int)
        or isinstance(target_count, bool)
        or not isinstance(target_count, int)
        or not isinstance(raw_source_edges, list)
        or not isinstance(raw_target_edges, list)
        or not isinstance(raw_lists, list)
    ):
        raise ValueError("public homomorphism instance is malformed")
    source_adjacency = [set() for _ in range(source_count)]
    for edge in raw_source_edges:
        if not isinstance(edge, Mapping):
            raise ValueError("public source edge is malformed")
        first, second = edge.get("u"), edge.get("v")
        if not isinstance(first, int) or not isinstance(second, int):
            raise ValueError("public source edge endpoints are malformed")
        source_adjacency[first - 1].add(second - 1)
        source_adjacency[second - 1].add(first - 1)
    target_adjacency: set[tuple[int, int]] = set()
    for edge in raw_target_edges:
        if not isinstance(edge, Mapping):
            raise ValueError("public target edge is malformed")
        first, second = edge.get("u"), edge.get("v")
        if not isinstance(first, int) or not isinstance(second, int):
            raise ValueError("public target edge endpoints are malformed")
        target_adjacency.add(tuple(sorted((first, second))))
    allowed = [set() for _ in range(source_count)]
    for item in raw_lists:
        if not isinstance(item, Mapping):
            raise ValueError("public target list is malformed")
        source = item.get("source_vertex")
        targets = item.get("allowed_targets")
        if not isinstance(source, int) or not isinstance(targets, list):
            raise ValueError("public target list fields are malformed")
        allowed[source - 1] = set(targets)

    mapping = [0] * source_count
    unseen = set(range(source_count))
    while unseen:
        component_seed = next(iter(unseen))
        component: set[int] = set()
        frontier = [component_seed]
        while frontier:
            vertex = frontier.pop()
            if vertex in component:
                continue
            component.add(vertex)
            frontier.extend(source_adjacency[vertex] - component)
        unseen -= component
        if len(component) > 1 and sum(
            len(source_adjacency[vertex]) for vertex in component
        ) != 2 * (len(component) - 1):
            raise ValueError("public source component is not a tree")
        anchors = [vertex for vertex in component if len(allowed[vertex]) == 1]
        if len(anchors) != 1:
            raise ValueError("public component does not have one forced anchor")
        root = anchors[0]
        mapping[root] = next(iter(allowed[root]))
        queue = [(root, -1)]
        visited: set[int] = set()
        while queue:
            vertex, parent = queue.pop()
            if vertex in visited:
                continue
            visited.add(vertex)
            for neighbor in source_adjacency[vertex]:
                if neighbor == parent:
                    continue
                candidates = [
                    target
                    for target in allowed[neighbor]
                    if tuple(sorted((mapping[vertex], target))) in target_adjacency
                ]
                if len(candidates) != 1:
                    raise ValueError("public path propagation is not unique")
                mapping[neighbor] = candidates[0]
                queue.append((neighbor, vertex))
        if visited != component:
            raise ValueError("public source component traversal was incomplete")
    if evaluate_mapping(public_instance, mapping) != (True, True):
        raise ValueError("recovered mapping failed exact public verification")
    return tuple(mapping)


def solve_public_c01(public_instance: Mapping[str, Any]) -> tuple[int, ...]:
    """Recover C01's unique anchored path mapping."""

    return solve_public_tree_constraints(public_instance)


def solve_public_c02(public_instance: Mapping[str, Any]) -> tuple[int, ...]:
    """Recover C02's unique tree-permutation mapping."""

    return solve_public_tree_constraints(public_instance)


def solve_public(public_instance: Mapping[str, Any]) -> tuple[int, ...]:
    """Dispatch the implemented public-only references by source topology."""

    source_count = public_instance.get("source_num_vertices")
    if source_count == 1_800:
        return solve_public_c05(public_instance)
    if isinstance(source_count, int) and source_count > 3_000:
        return solve_public_c04(public_instance)
    if isinstance(source_count, int) and source_count > 2_000:
        return solve_public_c03(public_instance)
    return solve_public_tree_constraints(public_instance)


def solve_public_c03(public_instance: Mapping[str, Any]) -> tuple[int, ...]:
    """Invoke C03's maintainer public-only structural reference."""

    import importlib.util

    reference_path = (
        Path(__file__).resolve().parents[3] / "scripts" / "reference_new_list_homomorphism_c03.py"
    )
    specification = importlib.util.spec_from_file_location("aipbench_c03_reference", reference_path)
    if specification is None or specification.loader is None:
        raise RuntimeError("C03 maintainer reference could not be loaded")
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    solve = module.solve_public

    return solve(public_instance)


def solve_public_c04(public_instance: Mapping[str, Any]) -> tuple[int, ...]:
    """Invoke C04's maintainer public-only line-inversion reference."""

    import importlib.util

    reference_path = (
        Path(__file__).resolve().parents[3] / "scripts" / "reference_new_list_homomorphism_c04.py"
    )
    specification = importlib.util.spec_from_file_location("aipbench_c04_reference", reference_path)
    if specification is None or specification.loader is None:
        raise RuntimeError("C04 maintainer reference could not be loaded")
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module.solve_public(public_instance)


def solve_public_c05(public_instance: Mapping[str, Any]) -> tuple[int, ...]:
    """Invoke C05's public-only cyclic-cover CFI reference."""

    import importlib.util

    reference_path = (
        Path(__file__).resolve().parents[3] / "scripts" / "reference_new_list_homomorphism_c05.py"
    )
    specification = importlib.util.spec_from_file_location("aipbench_c05_reference", reference_path)
    if specification is None or specification.loader is None:
        raise RuntimeError("C05 maintainer reference could not be loaded")
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module.solve_public(public_instance)


def solve_public_c06(public_instance: Mapping[str, Any]) -> tuple[int, ...]:
    """Run the C04 structural reference on its C06 difficulty replicate."""

    return solve_public_c04(public_instance)


def _participant_instance(client: ParticipantClient) -> Mapping[str, Any]:
    response = client.get_instance()
    nested = response.get("public_instance")
    return nested if isinstance(nested, Mapping) else response


class HonestNewHomomorphismAgent:
    agent_id = "virtual-honest"

    def run(self, *, client: ParticipantClient, workspace: Path) -> None:
        del workspace
        client.submit_event(
            sequence=0,
            kind=MAPPING_EVENT_KIND,
            payload={"mapping": list(solve_public(_participant_instance(client)))},
        )


_VIRTUAL_AGENT_LIST: Final[tuple[VirtualAgent, ...]] = (
    HonestNewHomomorphismAgent(),
    *SHARED_VIRTUAL_AGENTS.values(),
)
VIRTUAL_AGENTS: Final[Mapping[str, VirtualAgent]] = {
    agent.agent_id: agent for agent in _VIRTUAL_AGENT_LIST
}


@dataclass(frozen=True)
class NewListGraphHomomorphismTaskPlugin:
    manifest: Mapping[str, Any]
    case_parameters: Mapping[str, Mapping[str, Any]]
    generator: NewListGraphHomomorphismGenerator
    protocol: NewListGraphHomomorphismProtocol


def create_task() -> NewListGraphHomomorphismTaskPlugin:
    return NewListGraphHomomorphismTaskPlugin(
        manifest=TASK_MANIFEST,
        case_parameters=CASE_PARAMETERS,
        generator=NewListGraphHomomorphismGenerator(),
        protocol=NewListGraphHomomorphismProtocol(),
    )


__all__ = [
    "CASE_IDS",
    "CASE_PARAMETERS",
    "MAPPING_EVENT_KIND",
    "HomomorphismProtocolState",
    "HomomorphismReason",
    "NewListGraphHomomorphismGenerator",
    "NewListGraphHomomorphismProtocol",
    "TASK_ID",
    "TASK_MANIFEST",
    "TASK_VERSION",
    "VIRTUAL_AGENTS",
    "create_task",
    "evaluate_mapping",
    "solve_public",
    "solve_public_c01",
    "solve_public_c02",
    "solve_public_c03",
    "solve_public_c04",
    "solve_public_c05",
    "solve_public_c06",
    "solve_public_tree_constraints",
]
