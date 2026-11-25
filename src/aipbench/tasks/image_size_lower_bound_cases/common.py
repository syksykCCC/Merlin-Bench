"""Shared Boolean-circuit primitives for T2.4 Image-Size Lower Bound.

The first implementation deliberately uses correctness-scaled instances with at
most sixteen public input bits.  That lets the task-wide finalizer enumerate the
*final public circuit* and independently check the exact image cardinality promised
by every structural builder.  The 128-lane protocol itself is not scaled down.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Final, TypeGuard

MAX_INPUTS: Final = 16
MAX_OUTPUTS: Final = 64
MAX_GATES: Final = 20_000


def is_strict_integer(value: object) -> TypeGuard[int]:
    """Return true for JSON integers while rejecting booleans."""

    return isinstance(value, int) and not isinstance(value, bool)


class DeterministicStream:
    """Domain-separated SHA-256 stream used only by deterministic generation."""

    _DOMAIN: Final = b"aipbench/image-size-lower-bound/generator/v1\x00"

    def __init__(self, seed: bytes) -> None:
        self._seed = bytes(seed)
        self._counter = 0
        self._buffer = bytearray()

    def _refill(self) -> None:
        self._buffer.extend(
            hashlib.sha256(
                self._DOMAIN
                + len(self._seed).to_bytes(8, "big")
                + self._seed
                + self._counter.to_bytes(16, "big")
            ).digest()
        )
        self._counter += 1

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
        limit = sample_space - sample_space % upper_exclusive
        while True:
            candidate = int.from_bytes(self.take(width), "big")
            if candidate < limit:
                return candidate % upper_exclusive

    def bit(self) -> int:
        return self.randbelow(2)

    def shuffle(self, values: list[Any]) -> None:
        for index in range(len(values) - 1, 0, -1):
            other = self.randbelow(index + 1)
            values[index], values[other] = values[other], values[index]


def integer_parameter(
    parameters: Mapping[str, Any], name: str, *, minimum: int = 0, maximum: int | None = None
) -> int:
    value = parameters.get(name)
    if not is_strict_integer(value) or value < minimum:
        raise ValueError(f"case parameter {name!r} must be an integer >= {minimum}")
    if maximum is not None and value > maximum:
        raise ValueError(f"case parameter {name!r} must be at most {maximum}")
    return value


@dataclass(frozen=True)
class BooleanGate:
    op: str
    first: int | None = None
    second: int | None = None
    value: int | None = None


@dataclass(frozen=True)
class BooleanCircuit:
    num_inputs: int
    num_outputs: int
    gates: tuple[BooleanGate, ...]
    outputs: tuple[int, ...]


class CircuitBuilder:
    """Append-only topological Boolean circuit builder."""

    def __init__(self, num_inputs: int) -> None:
        if not 1 <= num_inputs <= MAX_INPUTS:
            raise ValueError(f"num_inputs must lie in [1, {MAX_INPUTS}]")
        self.num_inputs = num_inputs
        self.gates: list[dict[str, Any]] = []
        self._constants: dict[int, int] = {}

    def _append(self, gate: dict[str, Any]) -> int:
        if len(self.gates) >= MAX_GATES:
            raise ValueError("circuit exceeds the task-wide gate envelope")
        wire = self.num_inputs + len(self.gates)
        self.gates.append(gate)
        return wire

    def const(self, value: int) -> int:
        if value not in (0, 1):
            raise ValueError("a Boolean constant must be 0 or 1")
        existing = self._constants.get(value)
        if existing is not None:
            return existing
        wire = self._append({"op": "const", "value": value})
        self._constants[value] = wire
        return wire

    def not_(self, source: int) -> int:
        return self._append({"op": "not", "input": source})

    def xor(self, first: int, second: int) -> int:
        return self._append({"op": "xor", "left": first, "right": second})

    def and_(self, first: int, second: int) -> int:
        return self._append({"op": "and", "left": first, "right": second})

    def or_(self, first: int, second: int) -> int:
        # a OR b = (a XOR b) XOR (a AND b) over GF(2)
        return self.xor(self.xor(first, second), self.and_(first, second))

    def xor_many(self, sources: Sequence[int]) -> int:
        if not sources:
            return self.const(0)
        result = sources[0]
        for source in sources[1:]:
            result = self.xor(result, source)
        return result

    def and_many(self, sources: Sequence[int]) -> int:
        if not sources:
            return self.const(1)
        result = sources[0]
        for source in sources[1:]:
            result = self.and_(result, source)
        return result


@dataclass(frozen=True)
class CircuitBlueprint:
    num_inputs: int
    outputs: tuple[int, ...]
    gates: tuple[Mapping[str, Any], ...]
    image_size: int
    metadata: Mapping[str, Any] = field(default_factory=dict)


CaseBuilder = Callable[[DeterministicStream, Mapping[str, Any]], CircuitBlueprint]


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


def hide_outputs(
    builder: CircuitBuilder, outputs: Sequence[int], stream: DeterministicStream
) -> tuple[int, ...]:
    """Apply a seed-derived output permutation and affine shift."""

    hidden = list(outputs)
    stream.shuffle(hidden)
    for index in range(len(hidden)):
        if stream.bit():
            hidden[index] = builder.not_(hidden[index])
    return tuple(hidden)


def make_blueprint(
    *,
    builder: CircuitBuilder,
    outputs: Sequence[int],
    image_size: int,
    metadata: Mapping[str, Any],
) -> CircuitBlueprint:
    if not 1 <= len(outputs) <= MAX_OUTPUTS:
        raise ValueError(f"num_outputs must lie in [1, {MAX_OUTPUTS}]")
    return CircuitBlueprint(
        num_inputs=builder.num_inputs,
        outputs=tuple(outputs),
        gates=tuple(dict(gate) for gate in builder.gates),
        image_size=image_size,
        metadata=dict(metadata),
    )


def serialize_circuit(blueprint: CircuitBlueprint) -> dict[str, Any]:
    return {
        "num_inputs": blueprint.num_inputs,
        "num_outputs": len(blueprint.outputs),
        "gates": [dict(gate) for gate in blueprint.gates],
        "outputs": list(blueprint.outputs),
    }


def parse_public_circuit(raw: object) -> BooleanCircuit:
    """Strictly parse the topological circuit schema."""

    if not isinstance(raw, Mapping) or set(raw) != {
        "num_inputs",
        "num_outputs",
        "gates",
        "outputs",
    }:
        raise ValueError("circuit must contain exactly num_inputs, num_outputs, gates, outputs")
    num_inputs = raw["num_inputs"]
    num_outputs = raw["num_outputs"]
    if not is_strict_integer(num_inputs) or not 1 <= num_inputs <= MAX_INPUTS:
        raise ValueError("num_inputs is outside the supported strict integer envelope")
    if not is_strict_integer(num_outputs) or not 1 <= num_outputs <= MAX_OUTPUTS:
        raise ValueError("num_outputs is outside the supported strict integer envelope")
    raw_gates = raw["gates"]
    if not isinstance(raw_gates, list) or len(raw_gates) > MAX_GATES:
        raise ValueError("gates must be an array inside the supported envelope")
    gates: list[BooleanGate] = []
    for gate_index, raw_gate in enumerate(raw_gates):
        if not isinstance(raw_gate, Mapping):
            raise ValueError("every gate must be an object")
        op = raw_gate.get("op")
        current_wire = num_inputs + gate_index
        if op == "const":
            if set(raw_gate) != {"op", "value"} or raw_gate.get("value") not in (0, 1):
                raise ValueError("const gate must contain exactly an integer value 0 or 1")
            if isinstance(raw_gate.get("value"), bool):
                raise ValueError("Boolean JSON values are not integer circuit bits")
            gates.append(BooleanGate(op="const", value=raw_gate["value"]))
            continue
        if op == "not":
            if set(raw_gate) != {"op", "input"}:
                raise ValueError("not gate must contain exactly op and input")
            source = raw_gate.get("input")
            if not is_strict_integer(source) or not 0 <= source < current_wire:
                raise ValueError("not operand must be a prior wire")
            gates.append(BooleanGate(op="not", first=source))
            continue
        if op in {"xor", "and"}:
            if set(raw_gate) != {"op", "left", "right"}:
                raise ValueError("binary gate must contain exactly op, left, and right")
            first = raw_gate.get("left")
            second = raw_gate.get("right")
            if (
                not is_strict_integer(first)
                or not is_strict_integer(second)
                or not 0 <= first < current_wire
                or not 0 <= second < current_wire
            ):
                raise ValueError("binary operands must be prior wires")
            gates.append(BooleanGate(op=op, first=first, second=second))
            continue
        raise ValueError("unsupported Boolean gate operation")

    raw_outputs = raw["outputs"]
    if not isinstance(raw_outputs, list) or len(raw_outputs) != num_outputs:
        raise ValueError("outputs must be an array of length num_outputs")
    wire_count = num_inputs + len(gates)
    outputs: list[int] = []
    for output in raw_outputs:
        if not is_strict_integer(output) or not 0 <= output < wire_count:
            raise ValueError("every output must reference an existing wire")
        outputs.append(output)
    return BooleanCircuit(num_inputs, num_outputs, tuple(gates), tuple(outputs))


def evaluate_circuit(circuit: BooleanCircuit, input_word: int) -> int:
    """Evaluate a parsed circuit; bit i of each word is coordinate i."""

    if not is_strict_integer(input_word) or not 0 <= input_word < 1 << circuit.num_inputs:
        raise ValueError("input word is outside the circuit domain")
    wires = [(input_word >> index) & 1 for index in range(circuit.num_inputs)]
    for gate in circuit.gates:
        if gate.op == "const":
            assert gate.value is not None
            wires.append(gate.value)
        elif gate.op == "not":
            assert gate.first is not None
            wires.append(wires[gate.first] ^ 1)
        else:
            assert gate.first is not None and gate.second is not None
            if gate.op == "xor":
                wires.append(wires[gate.first] ^ wires[gate.second])
            else:
                wires.append(wires[gate.first] & wires[gate.second])
    result = 0
    for index, wire in enumerate(circuit.outputs):
        result |= wires[wire] << index
    return result


def enumerate_image(circuit: BooleanCircuit) -> dict[int, int]:
    """Map each public image word to its lexicographically first preimage."""

    image: dict[int, int] = {}
    for input_word in range(1 << circuit.num_inputs):
        image.setdefault(evaluate_circuit(circuit, input_word), input_word)
    return image


def finalize_blueprint(
    *, case_id: str, blueprint: CircuitBlueprint, stream: DeterministicStream
) -> FinalizedCase:
    """Validate and independently recount the final public circuit image."""

    del stream  # All semantic hiding is already represented in the public circuit.
    public_circuit = serialize_circuit(blueprint)
    parsed = parse_public_circuit(public_circuit)
    exact_image_size = len(enumerate_image(parsed))
    if exact_image_size != blueprint.image_size:
        raise ValueError("builder image-size certificate disagrees with final public semantics")
    if exact_image_size < 16:
        raise ValueError("correctness-scaled instances must have image size at least 16")
    threshold_exponent = exact_image_size.bit_length() - 1 - 4
    if not 16 * (1 << threshold_exponent) <= exact_image_size:
        raise AssertionError("threshold construction violated the YES promise")
    public_instance: Mapping[str, Any] = {
        "format_version": "aip-image-size/1",
        "circuit": public_circuit,
        "threshold_exponent": threshold_exponent,
        "hash_lanes": 128,
    }
    metadata: Mapping[str, Any] = {
        "generator": f"image_size_lower_bound/{case_id}/v1",
        "case_id": case_id,
        "num_inputs": parsed.num_inputs,
        "num_outputs": parsed.num_outputs,
        "num_gates": len(parsed.gates),
        "exact_image_size": exact_image_size,
        **dict(blueprint.metadata),
    }
    return FinalizedCase(public_instance, {}, metadata)


def parity(row: int, word: int) -> int:
    return (row & word).bit_count() & 1


def hash_word(rows: Sequence[int], word: int) -> int:
    result = 0
    for index, row in enumerate(rows):
        result |= parity(row, word) << index
    return result


def encode_gf2_bits(word: int, length: int) -> str:
    """Canonical ``gf2-bits/hex-v1`` encoding."""

    if not is_strict_integer(length) or length < 0:
        raise ValueError("bit-vector length must be a nonnegative integer")
    if not is_strict_integer(word) or not 0 <= word < 1 << length:
        raise ValueError("bit-vector word is outside its declared length")
    return word.to_bytes((length + 7) // 8, "little").hex()


def decode_gf2_bits(raw: object, length: int) -> int:
    """Strict decoder rejecting uppercase, bad width, and nonzero padding."""

    if not isinstance(raw, str):
        raise ValueError("encoded bit vector must be a string")
    expected_length = 2 * ((length + 7) // 8)
    if len(raw) != expected_length or raw != raw.lower():
        raise ValueError("encoded bit vector has noncanonical width or case")
    if any(character not in "0123456789abcdef" for character in raw):
        raise ValueError("encoded bit vector is not lowercase hexadecimal")
    word = int.from_bytes(bytes.fromhex(raw), "little") if raw else 0
    if word >= 1 << length:
        raise ValueError("encoded bit vector has nonzero padding bits")
    return word


__all__ = [
    "BooleanCircuit",
    "CaseBuilder",
    "CaseDefinition",
    "CircuitBlueprint",
    "CircuitBuilder",
    "DeterministicStream",
    "FinalizedCase",
    "decode_gf2_bits",
    "encode_gf2_bits",
    "enumerate_image",
    "evaluate_circuit",
    "finalize_blueprint",
    "hash_word",
    "hide_outputs",
    "integer_parameter",
    "make_blueprint",
    "parse_public_circuit",
]
