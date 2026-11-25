from __future__ import annotations

from collections import Counter, deque
from collections.abc import Sequence
from functools import cache
from pathlib import Path

import pytest
import yaml

from aipbench.core.errors import ErrorCode
from aipbench.core.models import ParticipantEvent, SessionMode, TerminalStatus
from aipbench.tasks.new_graph_non_isomorphism import (
    CASE_IDS,
    CASE_PARAMETERS,
    TASK_ID,
    TASK_MANIFEST,
    create_task,
)
from aipbench.tasks.shared.graph_non_isomorphism import (
    BEGIN_EVENT_KIND,
    CHALLENGE_LANES,
    RESPONSE_EVENT_KIND,
)
from aipbench.tasks.shared.graph_non_isomorphism_cases.common import (
    LogicalGraph,
    parse_public_graph,
    public_graph_fingerprint,
)

ROOT = Path(__file__).resolve().parents[2]
EXPECTED_CASE_IDS = ("c01", "c02", "c03", "c04", "c05", "c06", "c07")
EXPECTED_CASE_TITLES = {
    "c01": "Connected prism--Moebius baseline",
    "c02": "Connected Shrikhande--rook amplification",
    "c03": "Locally matched group-table geometries",
    "c04": "Uncolored enlarged CFI parity",
    "c05": "Fisher-transformed uncolored CFI parity",
    "c06": "Line graph of uncolored CFI parity",
    "c07": "Double line graph of uncolored CFI parity",
}
DEFAULT_SEED = b"new-graph-non-isomorphism-tests"


@cache
def _generated(case_id: str):
    return create_task().generator.generate(
        instance_seed=DEFAULT_SEED,
        case_id=case_id,
        case_parameters=CASE_PARAMETERS[case_id],
    )


def _adjacency(graph: LogicalGraph) -> list[set[int]]:
    result = [set() for _ in range(graph.num_vertices)]
    for first, second in graph.edges:
        result[first].add(second)
        result[second].add(first)
    return result


def _is_bipartite(adjacency: Sequence[set[int]]) -> bool:
    side: list[int | None] = [None] * len(adjacency)
    for start in range(len(adjacency)):
        if side[start] is not None:
            continue
        side[start] = 0
        queue = deque([start])
        while queue:
            vertex = queue.popleft()
            for neighbor in adjacency[vertex]:
                if side[neighbor] is None:
                    side[neighbor] = 1 - side[vertex]  # type: ignore[operator]
                    queue.append(neighbor)
                elif side[neighbor] == side[vertex]:
                    return False
    return True


def test_manifest_registry_and_case_yaml_cover_seven_cases() -> None:
    assert CASE_IDS == EXPECTED_CASE_IDS
    assert tuple(CASE_PARAMETERS) == EXPECTED_CASE_IDS
    assert TASK_MANIFEST["id"] == TASK_ID
    assert TASK_MANIFEST["resources"]["wall_time_seconds"] == 600
    assert TASK_MANIFEST["protocol"]["max_events"] == 2
    case_root = ROOT / "tasks" / "tier2_interactive" / "new_graph_non_isomorphism" / "cases"
    for case_id in EXPECTED_CASE_IDS:
        decoded = yaml.safe_load((case_root / f"{case_id}.yaml").read_text(encoding="utf-8"))
        assert decoded["id"] == case_id
        assert decoded["title"] == EXPECTED_CASE_TITLES[case_id]
        assert decoded["parameters"] == dict(CASE_PARAMETERS[case_id])


@pytest.mark.parametrize("case_id", EXPECTED_CASE_IDS)
def test_generation_is_deterministic_public_only_and_pair_balanced(case_id: str) -> None:
    generated = _generated(case_id)
    repeated = create_task().generator.generate(
        instance_seed=DEFAULT_SEED,
        case_id=case_id,
        case_parameters=CASE_PARAMETERS[case_id],
    )
    different = create_task().generator.generate(
        instance_seed=DEFAULT_SEED + b"/different",
        case_id=case_id,
        case_parameters=CASE_PARAMETERS[case_id],
    )
    assert generated == repeated
    assert generated.public_instance != different.public_instance
    assert generated.private_instance == {}
    assert generated.public_instance["challenge_lanes"] == CHALLENGE_LANES
    graphs = [parse_public_graph(raw) for raw in generated.public_instance["graphs"]]
    assert graphs[0].num_vertices == graphs[1].num_vertices
    assert len(graphs[0].edges) == len(graphs[1].edges)
    assert Counter(graphs[0].colors) == Counter(graphs[1].colors)


def test_c01_is_connected_cubic_and_has_exactly_one_bipartite_source() -> None:
    graphs = [parse_public_graph(raw) for raw in _generated("c01").public_instance["graphs"]]
    adjacencies = [_adjacency(graph) for graph in graphs]
    assert all(set(map(len, adjacency)) == {3} for adjacency in adjacencies)
    assert {_is_bipartite(adjacency) for adjacency in adjacencies} == {False, True}


@pytest.mark.parametrize("case_id", ("c03", "c04", "c05", "c06", "c07"))
def test_hard_cases_match_all_cheap_fingerprint_fields(case_id: str) -> None:
    graphs = [parse_public_graph(raw) for raw in _generated(case_id).public_instance["graphs"]]
    assert public_graph_fingerprint(graphs[0]) == public_graph_fingerprint(graphs[1])


class _Context:
    def __init__(self) -> None:
        self.tags: list[str] = []

    @property
    def mode(self) -> SessionMode:
        return SessionMode.DEV

    def random_int(self, *, tag: str, lower_inclusive: int, upper_exclusive: int) -> int:
        self.tags.append(tag)
        if tag.endswith("/source-bit"):
            lane = int(tag.split("/lane-", 1)[1].split("/", 1)[0])
            return lane % 2
        return upper_exclusive - 1

    def random_bytes(self, *, tag: str, length: int) -> bytes:
        raise AssertionError((tag, length))

    def random_field_element(self, *, tag: str, modulus: int) -> int:
        raise AssertionError((tag, modulus))

    def get_artifact_path(self, artifact_id: str) -> Path:
        raise AssertionError(artifact_id)


def test_protocol_uses_new_task_randomness_domain_and_accepts_exact_bits() -> None:
    task = create_task()
    generated = _generated("c01")
    context = _Context()
    state = task.protocol.initialize(generated_case=generated, context=context)
    begun = task.protocol.handle_event(
        state=state,
        event=ParticipantEvent(sequence=0, kind=BEGIN_EVENT_KIND, payload={}),
        generated_case=generated,
        context=context,
    )
    assert begun.terminal_status is None
    assert context.tags
    assert all(tag.startswith(f"{TASK_ID}/") for tag in context.tags)
    accepted = task.protocol.handle_event(
        state=begun.new_state,
        event=ParticipantEvent(
            sequence=1,
            kind=RESPONSE_EVENT_KIND,
            payload={"source_bits": [lane % 2 for lane in range(CHALLENGE_LANES)]},
        ),
        generated_case=generated,
        context=context,
    )
    assert accepted.terminal_status is TerminalStatus.ACCEPT
    assert accepted.reason_code == ErrorCode.PROTOCOL_ACCEPT
