"""Shared primitives used by the current Merlin-Bench tasks."""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final

from aipbench.tasks.field61 import CODEC_NAME, MODULUS, encode_field


class DeterministicStream:
    """Small domain-separated SHA-256 stream for deterministic generation."""

    _DOMAIN: Final = b"aipbench/boolean-hypercube-sumcheck/generator/v1\x00"

    def __init__(self, seed: bytes) -> None:
        self._seed = bytes(seed)
        self._counter = 0
        self._buffer = bytearray()

    def _refill(self) -> None:
        self._buffer.extend(
            hashlib.sha256(self._DOMAIN + self._seed + self._counter.to_bytes(8, "big")).digest()
        )
        self._counter += 1

    def random_bytes(self, length: int) -> bytes:
        while len(self._buffer) < length:
            self._refill()
        result = bytes(self._buffer[:length])
        del self._buffer[:length]
        return result

    def randbelow(self, upper: int) -> int:
        if isinstance(upper, bool) or not isinstance(upper, int) or upper <= 0:
            raise ValueError("upper must be a positive integer")
        width = max(1, (upper.bit_length() + 7) // 8)
        limit = 1 << (8 * width)
        cutoff = limit - limit % upper
        for _ in range(128):
            candidate = int.from_bytes(self.random_bytes(width), "big")
            if candidate < cutoff:
                return candidate % upper
        # This path is cryptographically negligible but makes the generator a
        # total deterministic function even under adversarial test streams.
        return int.from_bytes(self.random_bytes(width), "big") % upper

    def shuffle(self, values: list[Any]) -> None:
        for index in range(len(values) - 1, 0, -1):
            other = self.randbelow(index + 1)
            values[index], values[other] = values[other], values[index]

    def field(self, *, nonzero: bool = False, exclude_one: bool = False) -> int:
        if nonzero and exclude_one:
            return 2 + self.randbelow(MODULUS - 2)
        if nonzero:
            return 1 + self.randbelow(MODULUS - 1)
        if exclude_one:
            value = self.randbelow(MODULUS - 1)
            return 0 if value == 0 else value + 1
        return self.randbelow(MODULUS)


@dataclass(frozen=True)
class Factor:
    """One local Boolean truth table in scope-position little-endian order."""

    scope: tuple[int, ...]
    values: tuple[int, ...]


@dataclass(frozen=True)
class FactorBlueprint:
    num_variables: int
    factors: tuple[Factor, ...]
    metadata: Mapping[str, Any]


@dataclass(frozen=True)
class FactorModel:
    num_variables: int
    factors: tuple[Factor, ...]


@dataclass(frozen=True)
class FinalizedCase:
    public_instance: Mapping[str, Any]
    private_instance: Mapping[str, Any]
    generation_metadata: Mapping[str, Any]


CaseBuilder = Callable[[DeterministicStream, Mapping[str, Any]], FactorBlueprint]


@dataclass(frozen=True)
class CaseDefinition:
    case_id: str
    parameters: Mapping[str, Any]
    builder: CaseBuilder


def integer_parameter(
    parameters: Mapping[str, Any], name: str, *, minimum: int, maximum: int
) -> int:
    value = parameters.get(name)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an integer")
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be in [{minimum}, {maximum}]")
    return value


def _validate_model(model: FactorModel) -> None:
    if not 1 <= model.num_variables <= 400:
        raise ValueError("num_variables must be in [1, 400]")
    if not model.factors:
        raise ValueError("at least one factor is required")
    occurrence = [0] * model.num_variables
    for factor in model.factors:
        if not 1 <= len(factor.scope) <= 5:
            raise ValueError("factor arity must be in [1, 5]")
        if len(set(factor.scope)) != len(factor.scope):
            raise ValueError("factor scope contains a repeated variable")
        if any(
            isinstance(variable, bool)
            or not isinstance(variable, int)
            or not 0 <= variable < model.num_variables
            for variable in factor.scope
        ):
            raise ValueError("factor scope contains an invalid variable ID")
        if len(factor.values) != 1 << len(factor.scope):
            raise ValueError("factor table length does not match its scope")
        if any(
            isinstance(value, bool) or not isinstance(value, int) or not 0 <= value < MODULUS
            for value in factor.values
        ):
            raise ValueError("factor table contains an invalid field element")
        for variable in factor.scope:
            occurrence[variable] += 1
    if max(occurrence, default=0) > 5:
        raise ValueError("a variable occurs in more than five factors")
    if any(count == 0 for count in occurrence):
        raise ValueError("every variable must occur in at least one factor")


def parse_public_instance(public_instance: Mapping[str, Any]) -> FactorModel:
    """Strictly decode the public JSON relation and its canonical field values."""

    if set(public_instance) != {"format_version", "field", "num_variables", "factors"}:
        raise ValueError("malformed Sum-Check public instance")
    if public_instance.get("format_version") != "aip-sumcheck-instance/1":
        raise ValueError("unsupported Sum-Check instance format")
    field = public_instance.get("field")
    if not isinstance(field, Mapping) or set(field) != {"modulus", "codec"}:
        raise ValueError("malformed Sum-Check field declaration")
    if field.get("modulus") != "1fffffffffffffff" or field.get("codec") != CODEC_NAME:
        raise ValueError("unsupported Sum-Check field declaration")
    raw_num_variables = public_instance.get("num_variables")
    if (
        isinstance(raw_num_variables, bool)
        or not isinstance(raw_num_variables, int)
        or not 1 <= raw_num_variables <= 400
    ):
        raise ValueError("invalid Sum-Check variable count")
    raw_factors = public_instance.get("factors")
    if not isinstance(raw_factors, list) or not raw_factors:
        raise ValueError("Sum-Check factors must be a nonempty array")
    factors: list[Factor] = []
    for raw_factor in raw_factors:
        if not isinstance(raw_factor, Mapping) or set(raw_factor) != {"scope", "values"}:
            raise ValueError("malformed Sum-Check factor")
        raw_scope = raw_factor.get("scope")
        raw_values = raw_factor.get("values")
        if not isinstance(raw_scope, list) or not isinstance(raw_values, list):
            raise ValueError("malformed Sum-Check factor arrays")
        if any(
            isinstance(variable, bool) or not isinstance(variable, int) for variable in raw_scope
        ):
            raise ValueError("Sum-Check scope IDs must be strict integers")
        values: list[int] = []
        for value in raw_values:
            from aipbench.tasks.field61 import decode_field

            values.append(decode_field(value))
        factors.append(Factor(tuple(raw_scope), tuple(values)))
    model = FactorModel(raw_num_variables, tuple(factors))
    _validate_model(model)
    return model


def serialize_model(model: FactorModel) -> Mapping[str, Any]:
    _validate_model(model)
    return {
        "format_version": "aip-sumcheck-instance/1",
        "field": {"modulus": "1fffffffffffffff", "codec": CODEC_NAME},
        "num_variables": model.num_variables,
        "factors": [
            {
                "scope": list(factor.scope),
                "values": [encode_field(value) for value in factor.values],
            }
            for factor in model.factors
        ],
    }


def evaluate_factor(factor: Factor, point: Sequence[int]) -> int:
    """Evaluate a factor MLE; Boolean axes are selected without interpolation."""

    work = list(factor.values)
    for variable in factor.scope:
        coordinate = point[variable] % MODULUS
        if coordinate == 0:
            work = work[0::2]
        elif coordinate == 1:
            work = work[1::2]
        else:
            complement = (1 - coordinate) % MODULUS
            work = [
                (complement * work[index] + coordinate * work[index + 1]) % MODULUS
                for index in range(0, len(work), 2)
            ]
    if len(work) != 1:
        raise AssertionError("factor MLE folding did not consume every axis")
    return work[0]


def evaluate_product(model: FactorModel, point: Sequence[int]) -> int:
    if len(point) != model.num_variables:
        raise ValueError("point dimension does not match the public instance")
    result = 1
    for factor in model.factors:
        result = result * evaluate_factor(factor, point) % MODULUS
    return result
