"""Shared primitives used by the current Merlin-Bench tasks."""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, Final


class DeterministicStream:
    """Domain-separated SHA-256 stream used only for instance generation."""

    _DOMAIN: Final = b"aipbench/list-graph-homomorphism/generator/v1\x00"

    def __init__(self, seed: bytes) -> None:
        self._seed = bytes(seed)
        self._counter = 0
        self._buffer = bytearray()

    def _refill(self) -> None:
        digest = hashlib.sha256(
            self._DOMAIN
            + len(self._seed).to_bytes(8, "big")
            + self._seed
            + self._counter.to_bytes(16, "big")
        ).digest()
        self._counter += 1
        self._buffer.extend(digest)

    def take(self, length: int) -> bytes:
        if length < 0:
            raise ValueError("length must be non-negative")
        while len(self._buffer) < length:
            self._refill()
        result = bytes(self._buffer[:length])
        del self._buffer[:length]
        return result

    def randbelow(self, upper_exclusive: int) -> int:
        if upper_exclusive <= 0:
            raise ValueError("upper_exclusive must be positive")
        width = max(1, (upper_exclusive.bit_length() + 7) // 8)
        sample_space = 1 << (8 * width)
        rejection_limit = sample_space - sample_space % upper_exclusive
        while True:
            candidate = int.from_bytes(self.take(width), "big")
            if candidate < rejection_limit:
                return candidate % upper_exclusive

    def shuffle(self, values: list[Any]) -> None:
        for index in range(len(values) - 1, 0, -1):
            swap_index = self.randbelow(index + 1)
            values[index], values[swap_index] = values[swap_index], values[index]


def integer_parameter(parameters: Mapping[str, Any], name: str, *, minimum: int = 0) -> int:
    value = parameters.get(name)
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"case parameter {name!r} must be an integer >= {minimum}")
    return value


def complete_graph_edges(order: int) -> tuple[tuple[int, int], ...]:
    return tuple((first, second) for first in range(order) for second in range(first + 1, order))


def normalized_edges(pairs: set[tuple[int, int]]) -> tuple[tuple[int, int], ...]:
    return tuple(sorted({(min(first, second), max(first, second)) for first, second in pairs}))


@dataclass(frozen=True)
class CaseBlueprint:
    """A logical List-Hom instance before all public label randomization."""

    source_num_vertices: int
    source_edges: tuple[tuple[int, int], ...]
    target_num_vertices: int
    target_edges: tuple[tuple[int, int], ...]
    allowed_targets: tuple[frozenset[int], ...]
    reference_mapping: tuple[int, ...]
    metadata: Mapping[str, Any] = field(default_factory=dict)


CaseBuilder = Callable[[DeterministicStream, Mapping[str, Any]], CaseBlueprint]


@dataclass(frozen=True)
class CaseDefinition:
    case_id: str
    parameters: Mapping[str, Any]
    builder: CaseBuilder


@dataclass(frozen=True)
class FinalizedCase:
    public_instance: Mapping[str, Any]
    private_instance: Mapping[str, Any]
    generation_metadata: Mapping[str, Any]


def _validate_simple_graph(
    *,
    num_vertices: int,
    edges: tuple[tuple[int, int], ...],
    graph_name: str,
) -> set[tuple[int, int]]:
    if num_vertices < 1:
        raise ValueError(f"{graph_name} graph must contain at least one vertex")
    seen: set[tuple[int, int]] = set()
    for edge in edges:
        if (
            not isinstance(edge, tuple)
            or len(edge) != 2
            or isinstance(edge[0], bool)
            or isinstance(edge[1], bool)
            or not isinstance(edge[0], int)
            or not isinstance(edge[1], int)
        ):
            raise ValueError(f"{graph_name} graph contains a malformed edge")
        first, second = edge
        if not 0 <= first < second < num_vertices:
            raise ValueError(f"{graph_name} graph is not normalized simple undirected")
        if edge in seen:
            raise ValueError(f"{graph_name} graph contains a duplicate edge")
        seen.add(edge)
    return seen


def finalize_blueprint(
    *,
    case_id: str,
    blueprint: CaseBlueprint,
    stream: DeterministicStream,
) -> FinalizedCase:
    """Validate a witness, then independently hide source and target labels."""

    source_adjacency = _validate_simple_graph(
        num_vertices=blueprint.source_num_vertices,
        edges=blueprint.source_edges,
        graph_name="source",
    )
    target_adjacency = _validate_simple_graph(
        num_vertices=blueprint.target_num_vertices,
        edges=blueprint.target_edges,
        graph_name="target",
    )
    if len(blueprint.allowed_targets) != blueprint.source_num_vertices:
        raise ValueError("blueprint must contain one target list per source vertex")
    if len(blueprint.reference_mapping) != blueprint.source_num_vertices:
        raise ValueError("reference mapping must contain one image per source vertex")
    for source_vertex, allowed in enumerate(blueprint.allowed_targets):
        if not isinstance(allowed, frozenset) or not allowed:
            raise ValueError("every logical target list must be a nonempty frozenset")
        if any(
            isinstance(target, bool)
            or not isinstance(target, int)
            or not 0 <= target < blueprint.target_num_vertices
            for target in allowed
        ):
            raise ValueError("logical target list contains an invalid target vertex")
        image = blueprint.reference_mapping[source_vertex]
        if (
            isinstance(image, bool)
            or not isinstance(image, int)
            or not 0 <= image < blueprint.target_num_vertices
        ):
            raise ValueError("reference mapping contains an invalid target vertex")
        if image not in allowed:
            raise ValueError("reference mapping violates a logical target list")
    if any(
        (blueprint.reference_mapping[first], blueprint.reference_mapping[second])
        not in target_adjacency
        and (blueprint.reference_mapping[second], blueprint.reference_mapping[first])
        not in target_adjacency
        for first, second in source_adjacency
    ):
        raise ValueError("reference mapping violates a logical source edge")

    source_labels = list(range(1, blueprint.source_num_vertices + 1))
    target_labels = list(range(1, blueprint.target_num_vertices + 1))
    stream.shuffle(source_labels)
    stream.shuffle(target_labels)
    source_public_of = dict(enumerate(source_labels))
    target_public_of = dict(enumerate(target_labels))

    def public_edges(
        edges: tuple[tuple[int, int], ...],
        labels: Mapping[int, int],
    ) -> list[dict[str, int]]:
        edge_order = list(edges)
        stream.shuffle(edge_order)
        used_ids: set[int] = set()
        result: list[dict[str, int]] = []
        for first, second in edge_order:
            edge_id = 1 + stream.randbelow((1 << 31) - 1)
            while edge_id in used_ids:
                edge_id = 1 + stream.randbelow((1 << 31) - 1)
            used_ids.add(edge_id)
            u, v = sorted((labels[first], labels[second]))
            result.append({"edge_id": edge_id, "u": u, "v": v})
        return result

    public_lists: list[dict[str, Any]] = []
    for source_vertex, allowed in enumerate(blueprint.allowed_targets):
        public_allowed = [target_public_of[target] for target in allowed]
        stream.shuffle(public_allowed)
        public_lists.append(
            {
                "source_vertex": source_public_of[source_vertex],
                "allowed_targets": public_allowed,
            }
        )
    stream.shuffle(public_lists)

    reference_mapping = [0] * blueprint.source_num_vertices
    for source_vertex, target_vertex in enumerate(blueprint.reference_mapping):
        reference_mapping[source_public_of[source_vertex] - 1] = target_public_of[target_vertex]

    public_instance: Mapping[str, Any] = {
        "format_version": "aip-list-graph-homomorphism-instance/1",
        "source_num_vertices": blueprint.source_num_vertices,
        "source_edges": public_edges(blueprint.source_edges, source_public_of),
        "target_num_vertices": blueprint.target_num_vertices,
        "target_edges": public_edges(blueprint.target_edges, target_public_of),
        "lists": public_lists,
    }
    private_instance: Mapping[str, Any] = {"reference_mapping": reference_mapping}
    metadata: Mapping[str, Any] = {
        "generator": f"list_graph_homomorphism/{case_id}/v1",
        "case_id": case_id,
        "source_num_vertices": blueprint.source_num_vertices,
        "source_num_edges": len(blueprint.source_edges),
        "target_num_vertices": blueprint.target_num_vertices,
        "target_num_edges": len(blueprint.target_edges),
        "total_list_entries": sum(len(allowed) for allowed in blueprint.allowed_targets),
        **dict(blueprint.metadata),
    }
    return FinalizedCase(public_instance, private_instance, metadata)
