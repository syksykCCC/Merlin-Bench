from __future__ import annotations

from pathlib import Path

import yaml

from aipbench.core.models import ParticipantEvent, SessionMode, TerminalStatus
from aipbench.tasks.new_maxflow import (
    CASE_IDS,
    CASE_PARAMETERS,
    CERTIFICATE_EVENT_KIND,
    TASK_ID,
    TASK_MANIFEST,
    create_task,
    solve_maxflow,
)
from aipbench.tasks.shared.maxflow import MaxFlowReason

ROOT = Path(__file__).resolve().parents[2]
SEED = b"new-maxflow-reference-test"


class _Context:
    @property
    def mode(self) -> SessionMode:
        return SessionMode.DEV

    def random_bytes(self, *, tag: str, length: int) -> bytes:
        raise AssertionError((tag, length))

    def random_int(self, *, tag: str, lower_inclusive: int, upper_exclusive: int) -> int:
        raise AssertionError((tag, lower_inclusive, upper_exclusive))

    def random_field_element(self, *, tag: str, modulus: int) -> int:
        raise AssertionError((tag, modulus))


def _generated(case_id: str = "c01", seed: bytes = SEED):
    task = create_task()
    return task.generator.generate(
        instance_seed=seed,
        case_id=case_id,
        case_parameters=CASE_PARAMETERS[case_id],
    )


def _submit(case, payload):
    protocol = create_task().protocol
    context = _Context()
    state = protocol.initialize(generated_case=case, context=context)
    return protocol.handle_event(
        state=state,
        event=ParticipantEvent(
            sequence=0,
            kind=CERTIFICATE_EVENT_KIND,
            payload=payload,
        ),
        generated_case=case,
        context=context,
    )


def _mutable(payload):
    return {
        "flow_value": payload["flow_value"],
        "edge_flows": [dict(item) for item in payload["edge_flows"]],
        "source_side_cut": list(payload["source_side_cut"]),
    }


def test_c01_manifest_yaml_and_registry_profile() -> None:
    assert CASE_IDS == ("c01", "c02", "c03", "c04", "c05", "c06")
    assert TASK_MANIFEST["id"] == TASK_ID
    assert TASK_MANIFEST["resources"]["wall_time_seconds"] == 600
    case_yaml = yaml.safe_load(
        (ROOT / "tasks" / "tier1_np" / "new_maxflow_min_cut" / "cases" / "c01.yaml").read_text(
            encoding="utf-8"
        )
    )
    assert case_yaml["id"] == "c01"
    assert case_yaml["title"] == "Independent-channel calibration"
    assert case_yaml["parameters"] == dict(CASE_PARAMETERS["c01"])


def test_c01_is_deterministic_seeded_and_matches_channel_profile() -> None:
    first = _generated()
    repeated = _generated()
    different = _generated(seed=SEED + b"/different")
    assert first == repeated
    assert first.public_instance != different.public_instance
    public = first.public_instance
    channel_count = first.generation_metadata["channel_count"]
    assert 8 <= channel_count <= 16
    assert public["num_vertices"] == channel_count + 2
    assert len(public["edges"]) == 2 * channel_count
    assert len({edge["edge_id"] for edge in public["edges"]}) == 2 * channel_count
    assert first.generation_metadata["generator"] == "new-maxflow/c01/v1"
    assert "reference_flow_value" not in public


def test_c02_manifest_yaml_registry_and_scaled_profile() -> None:
    case_yaml = yaml.safe_load(
        (ROOT / "tasks" / "tier1_np" / "new_maxflow_min_cut" / "cases" / "c02.yaml").read_text(
            encoding="utf-8"
        )
    )
    assert case_yaml["id"] == "c02"
    assert case_yaml["title"] == "Regular bipartite matching network"
    assert case_yaml["parameters"] == dict(CASE_PARAMETERS["c02"])

    case = _generated("c02")
    repeated = _generated("c02")
    different = _generated("c02", SEED + b"/different")
    assert case == repeated
    assert case.public_instance != different.public_instance
    assert case.public_instance["num_vertices"] == 402
    assert len(case.public_instance["edges"]) == 5_000
    assert len({edge["edge_id"] for edge in case.public_instance["edges"]}) == 5_000
    assert case.generation_metadata["generator"] == "new-maxflow/c02/v1"
    assert case.generation_metadata["side_size"] == 200
    assert case.generation_metadata["identity_matching_present"] is True
    assert "reference_flow_value" not in case.public_instance


def test_c02_public_graph_has_unit_terminal_bottlenecks_and_three_layers() -> None:
    case = _generated("c02")
    public = case.public_instance
    source = public["source"]
    sink = public["sink"]
    edges = public["edges"]
    source_edges = [edge for edge in edges if edge["tail"] == source]
    sink_edges = [edge for edge in edges if edge["head"] == sink]
    assert len(source_edges) == len(sink_edges) == 200
    assert all(edge["capacity"] == 1 for edge in edges)
    left = {edge["head"] for edge in source_edges}
    right = {edge["tail"] for edge in sink_edges}
    assert len(left) == len(right) == 200
    assert left.isdisjoint(right | {source, sink})
    assert right.isdisjoint({source, sink})
    middle = [edge for edge in edges if edge["tail"] in left and edge["head"] in right]
    assert len(middle) == 4_600
    assert len({(edge["tail"], edge["head"]) for edge in middle}) == 4_600
    assert len(edges) == len(source_edges) + len(middle) + len(sink_edges)


def test_c03_manifest_yaml_registry_and_large_certificate_profile() -> None:
    case_yaml = yaml.safe_load(
        (ROOT / "tasks" / "tier1_np" / "new_maxflow_min_cut" / "cases" / "c03.yaml").read_text(
            encoding="utf-8"
        )
    )
    assert case_yaml["id"] == "c03"
    assert case_yaml["title"] == "Large-integer sharded serial network"
    assert case_yaml["parameters"] == dict(CASE_PARAMETERS["c03"])

    case = _generated("c03")
    repeated = _generated("c03")
    different = _generated("c03", SEED + b"/different")
    assert case == repeated
    assert case.public_instance != different.public_instance
    assert case.public_instance["num_vertices"] == 257
    assert len(case.public_instance["edges"]) == 18_944
    assert len({edge["edge_id"] for edge in case.public_instance["edges"]}) == 18_944
    assert case.generation_metadata["generator"] == "new-maxflow/c03/v1"
    assert case.generation_metadata["bandwidth"] == 3_000_000_007
    assert case.private_instance["reference_flow_value"] > (1 << 31) - 1
    assert "reference_flow_value" not in case.public_instance


def test_c03_parallel_bundles_form_a_complete_serial_chain() -> None:
    case = _generated("c03")
    public = case.public_instance
    grouped: dict[tuple[int, int], list[int]] = {}
    for edge in public["edges"]:
        grouped.setdefault((edge["tail"], edge["head"]), []).append(edge["capacity"])

    bundles = {pair: capacities for pair, capacities in grouped.items() if len(capacities) == 72}
    returns = {pair: capacities for pair, capacities in grouped.items() if len(capacities) == 1}
    assert len(bundles) == 256
    assert len(returns) == 512
    assert all(sum(capacities) == 3_000_000_007 for capacities in bundles.values())
    assert all(all(capacity > 0 for capacity in capacities) for capacities in bundles.values())

    position = {public["source"]: 0}
    vertex = public["source"]
    for index in range(1, 257):
        successors = [head for tail, head in bundles if tail == vertex]
        assert len(successors) == 1
        vertex = successors[0]
        assert vertex not in position
        position[vertex] = index
    assert vertex == public["sink"]
    assert len(position) == 257
    assert all(position[tail] >= position[head] + 2 for tail, head in returns)


def test_c04_manifest_yaml_registry_and_wide_layered_profile() -> None:
    case_yaml = yaml.safe_load(
        (ROOT / "tasks" / "tier1_np" / "new_maxflow_min_cut" / "cases" / "c04.yaml").read_text(
            encoding="utf-8"
        )
    )
    assert case_yaml["id"] == "c04"
    assert case_yaml["title"] == "Wide layered permutation network"
    assert case_yaml["parameters"] == dict(CASE_PARAMETERS["c04"])

    case = _generated("c04")
    repeated = _generated("c04")
    different = _generated("c04", SEED + b"/different")
    assert case == repeated
    assert case.public_instance != different.public_instance
    assert case.public_instance["num_vertices"] == 4_098
    assert len(case.public_instance["edges"]) == 12_224
    assert len({edge["edge_id"] for edge in case.public_instance["edges"]}) == 12_224
    assert case.generation_metadata["generator"] == "new-maxflow/c04/v1"
    assert case.generation_metadata["maximum_flow_is_non_unique"] is True
    assert case.private_instance["reference_flow_value"] == 64
    assert "reference_flow_value" not in case.public_instance


def test_c04_public_graph_has_64_wide_strict_layers_and_three_matchings() -> None:
    case = _generated("c04")
    public = case.public_instance
    source = public["source"]
    sink = public["sink"]
    adjacency: list[list[int]] = [[] for _ in range(public["num_vertices"])]
    edge_pairs: set[tuple[int, int]] = set()
    for edge in public["edges"]:
        assert edge["capacity"] == 1
        pair = (edge["tail"], edge["head"])
        assert pair not in edge_pairs
        edge_pairs.add(pair)
        adjacency[edge["tail"]].append(edge["head"])

    distances = [-1] * public["num_vertices"]
    distances[source] = 0
    frontier = [source]
    while frontier:
        next_frontier: list[int] = []
        for vertex in frontier:
            for neighbor in adjacency[vertex]:
                if distances[neighbor] == -1:
                    distances[neighbor] = distances[vertex] + 1
                    next_frontier.append(neighbor)
        frontier = next_frontier

    assert distances[sink] == 65
    assert distances.count(0) == distances.count(65) == 1
    assert all(distances.count(layer) == 64 for layer in range(1, 65))
    assert all(distances[head] == distances[tail] + 1 for tail, head in edge_pairs)
    counts_by_tail_layer = {
        layer: sum(1 for tail, _ in edge_pairs if distances[tail] == layer) for layer in range(65)
    }
    assert counts_by_tail_layer[0] == 64
    assert counts_by_tail_layer[64] == 64
    assert all(counts_by_tail_layer[layer] == 192 for layer in range(1, 64))


def test_c05_manifest_yaml_registry_and_sparse_cluster_profile() -> None:
    case_yaml = yaml.safe_load(
        (ROOT / "tasks" / "tier1_np" / "new_maxflow_min_cut" / "cases" / "c05.yaml").read_text(
            encoding="utf-8"
        )
    )
    assert case_yaml["id"] == "c05"
    assert case_yaml["title"] == "Sparse cluster-interface network"
    assert case_yaml["parameters"] == dict(CASE_PARAMETERS["c05"])

    case = _generated("c05")
    repeated = _generated("c05")
    different = _generated("c05", SEED + b"/different")
    assert case == repeated
    assert case.public_instance != different.public_instance
    assert case.public_instance["num_vertices"] == 12_290
    assert len(case.public_instance["edges"]) == 24_704
    assert len({edge["edge_id"] for edge in case.public_instance["edges"]}) == 24_704
    assert case.generation_metadata["generator"] == "new-maxflow/c05/v1"
    assert case.generation_metadata["maximum_flow_is_non_unique"] is True
    assert case.private_instance["reference_flow_value"] == 128
    assert "reference_flow_value" not in case.public_instance


def test_c05_public_graph_alternates_dense_clusters_and_sparse_interfaces() -> None:
    case = _generated("c05")
    public = case.public_instance
    source = public["source"]
    sink = public["sink"]
    adjacency: list[list[int]] = [[] for _ in range(public["num_vertices"])]
    edge_pairs: set[tuple[int, int]] = set()
    for edge in public["edges"]:
        assert edge["capacity"] == 1
        pair = (edge["tail"], edge["head"])
        assert pair not in edge_pairs
        edge_pairs.add(pair)
        adjacency[edge["tail"]].append(edge["head"])

    distances = [-1] * public["num_vertices"]
    distances[source] = 0
    frontier = [source]
    while frontier:
        next_frontier: list[int] = []
        for vertex in frontier:
            for neighbor in adjacency[vertex]:
                if distances[neighbor] == -1:
                    distances[neighbor] = distances[vertex] + 1
                    next_frontier.append(neighbor)
        frontier = next_frontier

    assert distances[sink] == 97
    assert distances.count(0) == distances.count(97) == 1
    assert all(distances.count(layer) == 128 for layer in range(1, 97))
    assert all(distances[head] == distances[tail] + 1 for tail, head in edge_pairs)
    counts_by_tail_layer = {
        layer: sum(1 for tail, _ in edge_pairs if distances[tail] == layer) for layer in range(97)
    }
    assert counts_by_tail_layer[0] == counts_by_tail_layer[96] == 128
    assert all(counts_by_tail_layer[layer] == 384 for layer in range(1, 96, 2))
    assert all(counts_by_tail_layer[layer] == 128 for layer in range(2, 96, 2))


def test_c06_manifest_yaml_registry_and_deep_diagnostic_profile() -> None:
    case_yaml = yaml.safe_load(
        (ROOT / "tasks" / "tier1_np" / "new_maxflow_min_cut" / "cases" / "c06.yaml").read_text(
            encoding="utf-8"
        )
    )
    assert case_yaml["id"] == "c06"
    assert case_yaml["title"] == "Deep width-two diagnostic network"
    assert case_yaml["parameters"] == dict(CASE_PARAMETERS["c06"])

    case = _generated("c06")
    repeated = _generated("c06")
    different = _generated("c06", SEED + b"/different")
    assert case == repeated
    assert case.public_instance != different.public_instance
    assert case.public_instance["num_vertices"] == 6_002
    assert len(case.public_instance["edges"]) == 12_000
    assert len({edge["edge_id"] for edge in case.public_instance["edges"]}) == 12_000
    assert case.generation_metadata["generator"] == "new-maxflow/c06/v1"
    assert case.generation_metadata["source_sink_distance"] == 3_001
    assert case.generation_metadata["general_hardness_claimed"] is False
    assert case.private_instance["reference_flow_value"] == 2
    assert "reference_flow_value" not in case.public_instance


def test_c06_public_graph_has_3000_width_two_layers_and_k22_transitions() -> None:
    case = _generated("c06")
    public = case.public_instance
    source = public["source"]
    sink = public["sink"]
    adjacency: list[list[int]] = [[] for _ in range(public["num_vertices"])]
    edge_pairs: set[tuple[int, int]] = set()
    for edge in public["edges"]:
        assert edge["capacity"] == 1
        pair = (edge["tail"], edge["head"])
        assert pair not in edge_pairs
        edge_pairs.add(pair)
        adjacency[edge["tail"]].append(edge["head"])

    distances = [-1] * public["num_vertices"]
    distances[source] = 0
    frontier = [source]
    while frontier:
        next_frontier: list[int] = []
        for vertex in frontier:
            for neighbor in adjacency[vertex]:
                if distances[neighbor] == -1:
                    distances[neighbor] = distances[vertex] + 1
                    next_frontier.append(neighbor)
        frontier = next_frontier

    assert distances[sink] == 3_001
    assert distances.count(0) == distances.count(3_001) == 1
    assert all(distances.count(layer) == 2 for layer in range(1, 3_001))
    assert all(distances[head] == distances[tail] + 1 for tail, head in edge_pairs)
    counts_by_tail_layer = {
        layer: sum(1 for tail, _ in edge_pairs if distances[tail] == layer)
        for layer in range(3_001)
    }
    assert counts_by_tail_layer[0] == counts_by_tail_layer[3_000] == 2
    assert all(counts_by_tail_layer[layer] == 4 for layer in range(1, 3_000))


def test_private_references_match_independent_solver_and_formal_relation() -> None:
    for case_id in CASE_IDS:
        case = _generated(case_id)
        certificate = solve_maxflow(case.public_instance)
        transition = _submit(case, certificate)
        assert transition.terminal_status == TerminalStatus.ACCEPT
        assert certificate["flow_value"] == case.private_instance["reference_flow_value"]
        assert certificate["source_side_cut"] == case.private_instance["reference_source_side_cut"]


def test_formal_capacity_and_edge_set_mutations_are_rejected() -> None:
    for case_id in CASE_IDS:
        case = _generated(case_id)
        certificate = _mutable(solve_maxflow(case.public_instance))
        capacities = {edge["edge_id"]: edge["capacity"] for edge in case.public_instance["edges"]}
        saturated = next(
            item
            for item in certificate["edge_flows"]
            if item["flow"] == capacities[item["edge_id"]]
        )
        saturated["flow"] += 1
        assert _submit(case, certificate).reason_code == MaxFlowReason.CAPACITY_VIOLATION

        missing = _mutable(solve_maxflow(case.public_instance))
        missing["edge_flows"].pop()
        assert _submit(case, missing).reason_code == MaxFlowReason.EDGE_SET_MISMATCH


def test_participant_specification_does_not_disclose_profile_or_solution_route() -> None:
    text = (
        ROOT / "tasks" / "tier1_np" / "new_maxflow_min_cut" / "TASK_SPECIFICATION.md"
    ).read_text(encoding="utf-8")
    lowered = text.lower()
    for forbidden in (
        "c01",
        "c02",
        "c03",
        "c04",
        "c05",
        "c06",
        "channel",
        "bipartite",
        "matching",
        "serial",
        "shard",
        "layered",
        "permutation",
        "cluster",
        "interface",
        "diagnostic",
        "phase",
        "generator",
        "dinic",
        "edmonds",
        "push--relabel",
        "10--18",
        "16--32",
        "402",
        "5000",
        "18944",
        "3000000007",
        "4098",
        "12224",
        "12290",
        "24704",
        "6002",
        "12000",
        "worked solution",
    ):
        assert forbidden not in lowered
