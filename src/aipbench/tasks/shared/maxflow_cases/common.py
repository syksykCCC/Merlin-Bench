"""Shared primitives used by the current Merlin-Bench tasks."""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, Final

MAX_SAFE_INTEGER: Final = (1 << 53) - 1


class DeterministicStream:
    """Domain-separated SHA-256 stream used only for instance generation."""

    _DOMAIN: Final = b"aipbench/maxflow/generator/v2\x00"

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
        rejection_limit = sample_space - (sample_space % upper_exclusive)
        while True:
            candidate = int.from_bytes(self.take(width), "big")
            if candidate < rejection_limit:
                return candidate % upper_exclusive

    def randint(self, lower_inclusive: int, upper_inclusive: int) -> int:
        if upper_inclusive < lower_inclusive:
            raise ValueError("invalid inclusive range")
        return lower_inclusive + self.randbelow(upper_inclusive - lower_inclusive + 1)

    def shuffle(self, values: list[Any]) -> None:
        for index in range(len(values) - 1, 0, -1):
            swap_index = self.randbelow(index + 1)
            values[index], values[swap_index] = values[swap_index], values[index]


def integer_parameter(parameters: Mapping[str, Any], name: str, *, minimum: int = 0) -> int:
    value = parameters.get(name)
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"case parameter {name!r} must be an integer >= {minimum}")
    return value


def positive_composition(total: int, parts: int, stream: DeterministicStream) -> list[int]:
    """Return a deterministic random positive composition of ``total``."""

    if parts <= 0 or total < parts:
        raise ValueError("positive composition requires total >= parts >= 1")
    if parts == 1:
        return [total]
    cuts: set[int] = set()
    while len(cuts) < parts - 1:
        cuts.add(1 + stream.randbelow(total - 1))
    ordered = [0, *sorted(cuts), total]
    return [right - left for left, right in zip(ordered, ordered[1:], strict=False)]


@dataclass(frozen=True)
class LogicalEdge:
    tail: int
    head: int
    capacity: int


@dataclass(frozen=True)
class CaseBlueprint:
    """A case in logical labels before public randomization."""

    num_vertices: int
    source: int
    sink: int
    edges: tuple[LogicalEdge, ...]
    reference_flow_value: int
    reference_source_side_cut: frozenset[int]
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


def finalize_blueprint(
    *,
    case_id: str,
    blueprint: CaseBlueprint,
    stream: DeterministicStream,
) -> FinalizedCase:
    """Validate and obscure a logical graph without changing its mathematics."""

    if blueprint.num_vertices < 2 or blueprint.source == blueprint.sink:
        raise ValueError("case blueprint has invalid terminals")
    if (
        isinstance(blueprint.reference_flow_value, bool)
        or not isinstance(blueprint.reference_flow_value, int)
        or not 0 <= blueprint.reference_flow_value <= MAX_SAFE_INTEGER
    ):
        raise ValueError("case blueprint has an invalid reference flow value")
    vertices = range(blueprint.num_vertices)
    if blueprint.source not in vertices or blueprint.sink not in vertices:
        raise ValueError("case blueprint terminal is outside the vertex range")
    if blueprint.source not in blueprint.reference_source_side_cut:
        raise ValueError("reference cut must contain the source")
    if blueprint.sink in blueprint.reference_source_side_cut:
        raise ValueError("reference cut must exclude the sink")

    total_capacity = 0
    for edge in blueprint.edges:
        if edge.tail not in vertices or edge.head not in vertices or edge.tail == edge.head:
            raise ValueError("case blueprint contains an invalid edge")
        if edge.capacity < 0:
            raise ValueError("case blueprint contains a negative capacity")
        total_capacity += edge.capacity
    if total_capacity > MAX_SAFE_INTEGER:
        raise ValueError("case blueprint exceeds the exact JSON integer capacity budget")
    reference_cut_capacity = sum(
        edge.capacity
        for edge in blueprint.edges
        if edge.tail in blueprint.reference_source_side_cut
        and edge.head not in blueprint.reference_source_side_cut
    )
    if reference_cut_capacity != blueprint.reference_flow_value:
        raise ValueError("case blueprint reference cut does not match its reference flow value")

    public_labels = list(vertices)
    stream.shuffle(public_labels)
    label_of = {logical: public_labels[logical] for logical in vertices}

    shuffled_edges = list(blueprint.edges)
    stream.shuffle(shuffled_edges)
    used_edge_ids: set[int] = set()
    public_edges: list[dict[str, int]] = []
    for edge in shuffled_edges:
        edge_id = 1 + stream.randbelow((1 << 31) - 1)
        while edge_id in used_edge_ids:
            edge_id = 1 + stream.randbelow((1 << 31) - 1)
        used_edge_ids.add(edge_id)
        public_edges.append(
            {
                "edge_id": edge_id,
                "tail": label_of[edge.tail],
                "head": label_of[edge.head],
                "capacity": edge.capacity,
            }
        )

    public_cut = sorted(label_of[vertex] for vertex in blueprint.reference_source_side_cut)
    public_instance: Mapping[str, Any] = {
        "format_version": "aip-maxflow-instance/1",
        "directed": True,
        "num_vertices": blueprint.num_vertices,
        "source": label_of[blueprint.source],
        "sink": label_of[blueprint.sink],
        "edges": public_edges,
    }
    private_instance: Mapping[str, Any] = {
        "reference_flow_value": blueprint.reference_flow_value,
        "reference_source_side_cut": public_cut,
    }
    metadata = {
        "generator": f"maxflow/{case_id}/v1",
        "case_id": case_id,
        "num_vertices": blueprint.num_vertices,
        "num_edges": len(public_edges),
        "total_capacity": total_capacity,
        **dict(blueprint.metadata),
    }
    return FinalizedCase(public_instance, private_instance, metadata)
