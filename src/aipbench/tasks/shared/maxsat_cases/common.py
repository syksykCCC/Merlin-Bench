"""Shared primitives used by the current Merlin-Bench tasks."""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, Final

MAX_SAFE_INTEGER: Final = (1 << 53) - 1


class DeterministicStream:
    """Domain-separated SHA-256 stream used only for instance generation."""

    _DOMAIN: Final = b"aipbench/weighted-partial-maxsat/generator/v2\x00"

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

    def randint(self, lower_inclusive: int, upper_inclusive: int) -> int:
        if upper_inclusive < lower_inclusive:
            raise ValueError("invalid inclusive range")
        return lower_inclusive + self.randbelow(upper_inclusive - lower_inclusive + 1)

    def random_bool(self) -> bool:
        return bool(self.randbelow(2))

    def shuffle(self, values: list[Any]) -> None:
        for index in range(len(values) - 1, 0, -1):
            swap_index = self.randbelow(index + 1)
            values[index], values[swap_index] = values[swap_index], values[index]


def integer_parameter(parameters: Mapping[str, Any], name: str, *, minimum: int = 0) -> int:
    value = parameters.get(name)
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"case parameter {name!r} must be an integer >= {minimum}")
    return value


@dataclass(frozen=True)
class Clause:
    """A hard clause in signed, one-based logical DIMACS variables."""

    literals: tuple[int, ...]


@dataclass(frozen=True)
class SoftClause:
    """A positively weighted soft clause in logical DIMACS variables."""

    literals: tuple[int, ...]
    weight: int


@dataclass(frozen=True)
class CaseBlueprint:
    """A planted WCNF case before public variable and polarity hiding."""

    num_variables: int
    hard_clauses: tuple[Clause, ...]
    soft_clauses: tuple[SoftClause, ...]
    threshold: int
    reference_assignment: tuple[bool, ...]
    reference_cost: int
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


def _literal_is_true(literal: int, assignment: tuple[bool, ...]) -> bool:
    value = assignment[abs(literal) - 1]
    return value if literal > 0 else not value


def _validate_clause(literals: tuple[int, ...], num_variables: int) -> None:
    if not literals:
        raise ValueError("case blueprint contains an empty clause")
    seen_variables: set[int] = set()
    for literal in literals:
        if isinstance(literal, bool) or not isinstance(literal, int):
            raise ValueError("case blueprint contains a non-integer literal")
        variable = abs(literal)
        if not 1 <= variable <= num_variables:
            raise ValueError("case blueprint contains an out-of-range literal")
        if variable in seen_variables:
            raise ValueError("case blueprint contains a repeated or complementary literal")
        seen_variables.add(variable)


def finalize_blueprint(
    *,
    blueprint: CaseBlueprint,
    stream: DeterministicStream,
) -> FinalizedCase:
    """Strictly validate a planted WCNF and hide all logical labels.

    The hiding transformation first chooses an arbitrary permutation of the
    variables, then independently complements every public variable.  It is an
    exact WCNF isomorphism: clause satisfaction and weighted cost are preserved.
    """

    if blueprint.num_variables < 1:
        raise ValueError("case blueprint must contain at least one variable")
    if len(blueprint.reference_assignment) != blueprint.num_variables or any(
        not isinstance(value, bool) for value in blueprint.reference_assignment
    ):
        raise ValueError("reference assignment must contain one boolean per variable")
    if (
        isinstance(blueprint.threshold, bool)
        or not isinstance(blueprint.threshold, int)
        or not 0 <= blueprint.threshold <= MAX_SAFE_INTEGER
    ):
        raise ValueError("case blueprint has an invalid threshold")
    if (
        isinstance(blueprint.reference_cost, bool)
        or not isinstance(blueprint.reference_cost, int)
        or not 0 <= blueprint.reference_cost <= MAX_SAFE_INTEGER
    ):
        raise ValueError("case blueprint has an invalid reference cost")

    for hard_clause in blueprint.hard_clauses:
        _validate_clause(hard_clause.literals, blueprint.num_variables)
        if not any(
            _literal_is_true(literal, blueprint.reference_assignment)
            for literal in hard_clause.literals
        ):
            raise ValueError("reference assignment violates a hard clause")

    computed_cost = 0
    total_soft_weight = 0
    for soft_clause in blueprint.soft_clauses:
        _validate_clause(soft_clause.literals, blueprint.num_variables)
        if (
            isinstance(soft_clause.weight, bool)
            or not isinstance(soft_clause.weight, int)
            or soft_clause.weight <= 0
        ):
            raise ValueError("soft-clause weights must be positive integers")
        total_soft_weight += soft_clause.weight
        if total_soft_weight > MAX_SAFE_INTEGER:
            raise ValueError("case blueprint exceeds the exact JSON integer weight budget")
        if not any(
            _literal_is_true(literal, blueprint.reference_assignment)
            for literal in soft_clause.literals
        ):
            computed_cost += soft_clause.weight
    if computed_cost != blueprint.reference_cost:
        raise ValueError("reference assignment cost does not match reference_cost")
    if computed_cost > blueprint.threshold:
        raise ValueError("reference assignment exceeds the public threshold")

    logical_variables = list(range(1, blueprint.num_variables + 1))
    public_variables = logical_variables.copy()
    stream.shuffle(public_variables)
    public_of = dict(zip(logical_variables, public_variables, strict=True))
    gauge_flip = {variable: stream.random_bool() for variable in logical_variables}

    public_assignment = [False] * blueprint.num_variables
    for logical_variable, logical_value in enumerate(blueprint.reference_assignment, start=1):
        public_variable = public_of[logical_variable]
        public_assignment[public_variable - 1] = logical_value ^ gauge_flip[logical_variable]

    def obscure_literals(literals: tuple[int, ...]) -> list[int]:
        result: list[int] = []
        for literal in literals:
            logical_variable = abs(literal)
            positive = literal > 0
            if gauge_flip[logical_variable]:
                positive = not positive
            public_variable = public_of[logical_variable]
            result.append(public_variable if positive else -public_variable)
        stream.shuffle(result)
        return result

    used_clause_ids: set[int] = set()

    def new_clause_id() -> int:
        clause_id = stream.randbelow(MAX_SAFE_INTEGER + 1)
        while clause_id in used_clause_ids:
            clause_id = stream.randbelow(MAX_SAFE_INTEGER + 1)
        used_clause_ids.add(clause_id)
        return clause_id

    hard_order = list(blueprint.hard_clauses)
    soft_order = list(blueprint.soft_clauses)
    stream.shuffle(hard_order)
    stream.shuffle(soft_order)
    public_hard = [
        {"clause_id": new_clause_id(), "literals": obscure_literals(clause.literals)}
        for clause in hard_order
    ]
    public_soft = [
        {
            "clause_id": new_clause_id(),
            "literals": obscure_literals(clause.literals),
            "weight": clause.weight,
        }
        for clause in soft_order
    ]

    public_instance: Mapping[str, Any] = {
        "format_version": "aip-weighted-partial-maxsat-instance/1",
        "num_variables": blueprint.num_variables,
        "hard_clauses": public_hard,
        "soft_clauses": public_soft,
        "threshold": blueprint.threshold,
    }
    private_instance: Mapping[str, Any] = {
        "reference_assignment": [int(value) for value in public_assignment],
        "reference_cost": blueprint.reference_cost,
    }
    metadata: Mapping[str, Any] = {
        "num_variables": blueprint.num_variables,
        "num_hard_clauses": len(public_hard),
        "num_soft_clauses": len(public_soft),
        "total_soft_weight": total_soft_weight,
        **dict(blueprint.metadata),
    }
    return FinalizedCase(public_instance, private_instance, metadata)
