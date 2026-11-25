"""Independent weighted Set Cover construction primitives."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Final

from aipbench.tasks.shared.set_cover_cases.common import DeterministicStream

MAX_SAFE_INTEGER: Final = 9_007_199_254_740_991


class NewSetCoverStream(DeterministicStream):
    """Deterministic stream with a task-specific domain."""

    _DOMAIN: Final = b"aipbench/new-structured-set-cover/generator/v1\x00"


@dataclass(frozen=True)
class WeightedCandidate:
    elements: frozenset[int]
    weight: int


@dataclass(frozen=True)
class CaseBlueprint:
    universe_size: int
    candidates: tuple[WeightedCandidate, ...]
    budget: int
    reference_candidate_indices: tuple[int, ...]
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class FinalizedCase:
    public_instance: Mapping[str, Any]
    private_instance: Mapping[str, Any]
    generation_metadata: Mapping[str, Any]


def integer_parameter(parameters: Mapping[str, Any], name: str, *, minimum: int = 0) -> int:
    value = parameters.get(name)
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"case parameter {name!r} must be an integer >= {minimum}")
    return value


def _fresh_id(stream: NewSetCoverStream, used: set[int]) -> int:
    modulus = (1 << 31) - 1
    start = stream.randbelow(modulus)
    for offset in range(len(used) + 1):
        candidate = 1 + (start + offset) % modulus
        if candidate not in used:
            return candidate
    raise RuntimeError("failed to allocate an opaque set ID")


def finalize_blueprint(*, blueprint: CaseBlueprint, stream: NewSetCoverStream) -> FinalizedCase:
    if not 1 <= blueprint.universe_size <= 4_096:
        raise ValueError("invalid new Set Cover universe size")
    if not blueprint.candidates or len(blueprint.candidates) > 10_000:
        raise ValueError("invalid new Set Cover candidate count")
    if not 1 <= blueprint.budget <= MAX_SAFE_INTEGER:
        raise ValueError("invalid new Set Cover budget")

    seen: set[frozenset[int]] = set()
    union: set[int] = set()
    total_incidence = 0
    for candidate in blueprint.candidates:
        if (
            not isinstance(candidate.elements, frozenset)
            or not candidate.elements
            or candidate.elements in seen
            or any(
                isinstance(element, bool)
                or not isinstance(element, int)
                or not 0 <= element < blueprint.universe_size
                for element in candidate.elements
            )
            or isinstance(candidate.weight, bool)
            or not isinstance(candidate.weight, int)
            or not 1 <= candidate.weight <= MAX_SAFE_INTEGER
        ):
            raise ValueError("invalid weighted Set Cover candidate")
        seen.add(candidate.elements)
        union.update(candidate.elements)
        total_incidence += len(candidate.elements)
    if len(union) != blueprint.universe_size or total_incidence > 100_000:
        raise ValueError("candidate incidence does not cover the safe universe")

    reference = blueprint.reference_candidate_indices
    if len(reference) != len(set(reference)) or any(
        not 0 <= index < len(blueprint.candidates) for index in reference
    ):
        raise ValueError("invalid reference candidate indices")
    covered = set().union(*(blueprint.candidates[index].elements for index in reference))
    reference_weight = sum(blueprint.candidates[index].weight for index in reference)
    if len(covered) != blueprint.universe_size or reference_weight > blueprint.budget:
        raise ValueError("reference is not a budget-feasible cover")

    public_labels = list(range(1, blueprint.universe_size + 1))
    stream.shuffle(public_labels)
    public_of = dict(enumerate(public_labels))
    used_ids: set[int] = set()
    id_by_index: dict[int, int] = {}
    order = list(range(len(blueprint.candidates)))
    stream.shuffle(order)
    public_sets: list[dict[str, Any]] = []
    for index in order:
        set_id = _fresh_id(stream, used_ids)
        used_ids.add(set_id)
        id_by_index[index] = set_id
        elements = [public_of[element] for element in blueprint.candidates[index].elements]
        stream.shuffle(elements)
        public_sets.append(
            {
                "set_id": set_id,
                "elements": elements,
                "weight": blueprint.candidates[index].weight,
            }
        )
    reference_ids = sorted(id_by_index[index] for index in reference)
    return FinalizedCase(
        public_instance={
            "format_version": "aip-structured-set-cover-instance/1",
            "num_elements": blueprint.universe_size,
            "sets": public_sets,
            "budget": blueprint.budget,
        },
        private_instance={
            "reference_set_ids": reference_ids,
            "reference_weight": reference_weight,
        },
        generation_metadata={
            "num_elements": blueprint.universe_size,
            "num_sets": len(public_sets),
            "total_incidence": total_incidence,
            "reference_weight": reference_weight,
            **dict(blueprint.metadata),
        },
    )


__all__ = [
    "CaseBlueprint",
    "FinalizedCase",
    "NewSetCoverStream",
    "WeightedCandidate",
    "finalize_blueprint",
    "integer_parameter",
]
