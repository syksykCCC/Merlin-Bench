"""Shared primitives used by the current Merlin-Bench tasks."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from math import log2
from typing import Any, Final

from aipbench.tasks.field61 import CODEC_NAME, MODULUS, decode_field, encode_field

__all__ = ["MODULUS"]

FORMAT_VERSION: Final = "aip-gkr-instance/1"

MODULUS_HEX: Final = "1fffffffffffffff"

MAX_INDEX_BITS: Final = 20

MAX_TOTAL_POSITIONS: Final = 1 << 20

MAX_BARRIERS: Final = 512

MAX_PUBLIC_BYTES: Final = 64 * 1024 * 1024


def _is_integer(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def require_integer(parameters: Mapping[str, Any], name: str, *, minimum: int, maximum: int) -> int:
    value = parameters.get(name)
    if not _is_integer(value):
        raise ValueError(f"{name} must be an integer")
    assert isinstance(value, int)
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be in [{minimum}, {maximum}]")
    return value


def is_power_of_two(value: int) -> bool:
    return value > 0 and value & (value - 1) == 0


def next_power_of_two(value: int) -> int:
    if value <= 0:
        raise ValueError("circuit layers must contain at least one position")
    return 1 << (value - 1).bit_length()


class DeterministicStream:
    """Small SHA-256 stream used only for deterministic instance generation."""

    _DOMAIN: Final = b"aipbench/gkr-layered-circuit/generator/v1\x00"

    def __init__(self, seed: bytes) -> None:
        self._seed = bytes(seed)
        self._counter = 0
        self._buffer = bytearray()

    def _refill(self) -> None:
        self._buffer.extend(
            hashlib.sha256(self._DOMAIN + self._seed + self._counter.to_bytes(8, "big")).digest()
        )
        self._counter += 1

    def bytes(self, length: int) -> bytes:
        while len(self._buffer) < length:
            self._refill()
        result = bytes(self._buffer[:length])
        del self._buffer[:length]
        return result

    def integer(self, upper_exclusive: int) -> int:
        if upper_exclusive <= 0:
            raise ValueError("upper_exclusive must be positive")
        width = max(1, (upper_exclusive.bit_length() + 7) // 8)
        ceiling = 1 << (8 * width)
        cutoff = ceiling - ceiling % upper_exclusive
        while True:
            candidate = int.from_bytes(self.bytes(width), "big")
            if candidate < cutoff:
                return candidate % upper_exclusive

    def field(self) -> int:
        return self.integer(MODULUS)

    def shuffle(self, values: list[int]) -> None:
        for index in range(len(values) - 1, 0, -1):
            other = self.integer(index + 1)
            values[index], values[other] = values[other], values[index]


@dataclass(frozen=True)
class Gate:
    a: int
    b: int
    c: int
    left: int
    right: int

    def normalized(self) -> Gate:
        return Gate(
            self.a % MODULUS,
            self.b % MODULUS,
            self.c % MODULUS,
            self.left,
            self.right,
        )


ZERO_GATE: Final = Gate(0, 0, 0, 0, 0)


def copy_gate(source: int, scalar: int = 1) -> Gate:
    return Gate(scalar % MODULUS, 0, 0, source, 0)


def add_gate(left: int, right: int) -> Gate:
    return Gate(1, 1, 0, left, right)


def sub_gate(left: int, right: int) -> Gate:
    return Gate(1, -1, 0, left, right).normalized()


def mul_gate(left: int, right: int) -> Gate:
    return Gate(0, 0, 1, left, right)


def or_gate(left: int, right: int) -> Gate:
    return Gate(1, 1, -1, left, right).normalized()


def padded_values(values: Sequence[int]) -> tuple[int, ...]:
    width = next_power_of_two(len(values))
    return tuple(value % MODULUS for value in values) + (0,) * (width - len(values))


def padded_stage(gates: Sequence[Gate], child_width: int) -> tuple[Gate, ...]:
    if not is_power_of_two(child_width):
        raise ValueError("child width must be a power of two")
    width = next_power_of_two(len(gates))
    normalized: list[Gate] = []
    for gate in gates:
        gate = gate.normalized()
        if not 0 <= gate.left < child_width or not 0 <= gate.right < child_width:
            raise ValueError("gate child is outside the preceding layer")
        normalized.append(gate)
    normalized.extend([ZERO_GATE] * (width - len(normalized)))
    return tuple(normalized)


def sum_reduction(width: int) -> list[tuple[Gate, ...]]:
    if not is_power_of_two(width):
        raise ValueError("sum reduction width must be a power of two")
    result: list[tuple[Gate, ...]] = []
    while width > 1:
        stage = tuple(add_gate(index, index + 1) for index in range(0, width, 2))
        result.append(stage)
        width //= 2
    return result


@dataclass(frozen=True)
class CircuitBlueprint:
    input_values: tuple[int, ...]
    forward_layers: tuple[tuple[Gate, ...], ...]
    semantic_output: int


@dataclass(frozen=True)
class ParsedCircuit:
    layer_widths: tuple[int, ...]
    layers: tuple[tuple[Gate, ...], ...]
    input_values: tuple[int, ...]

    @property
    def depth(self) -> int:
        return len(self.layers)

    @property
    def total_positions(self) -> int:
        return sum(self.layer_widths)

    @property
    def barriers(self) -> int:
        return sum(2 * (width.bit_length() - 1) + 1 for width in self.layer_widths[1:])


def evaluate_gate(gate: Gate, children: Sequence[int]) -> int:
    left = children[gate.left]
    right = children[gate.right]
    return (gate.a * left + gate.b * right + gate.c * left * right) % MODULUS


def evaluate_forward(
    input_values: Sequence[int], forward_layers: Sequence[Sequence[Gate]]
) -> tuple[tuple[int, ...], ...]:
    values: list[tuple[int, ...]] = [tuple(value % MODULUS for value in input_values)]
    for gates in forward_layers:
        child_values = values[-1]
        values.append(tuple(evaluate_gate(gate, child_values) for gate in gates))
    return tuple(values)


def evaluate_circuit(circuit: ParsedCircuit) -> tuple[tuple[int, ...], ...]:
    values: list[tuple[int, ...] | None] = [None] * len(circuit.layer_widths)
    values[-1] = circuit.input_values
    for layer in range(circuit.depth - 1, -1, -1):
        child_values = values[layer + 1]
        assert child_values is not None
        values[layer] = tuple(evaluate_gate(gate, child_values) for gate in circuit.layers[layer])
    return tuple(value for value in values if value is not None)


def _serialize_gate(gate: Gate) -> Mapping[str, Any]:
    return {
        "a": encode_field(gate.a),
        "b": encode_field(gate.b),
        "c": encode_field(gate.c),
        "left": gate.left,
        "right": gate.right,
    }


def finalize_blueprint(
    *, blueprint: CircuitBlueprint, stream: DeterministicStream
) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    logical_values = evaluate_forward(blueprint.input_values, blueprint.forward_layers)
    if len(logical_values[-1]) != 1:
        raise ValueError("GKR circuit must have one scalar output")
    if logical_values[-1][0] != blueprint.semantic_output % MODULUS:
        raise ValueError("case semantic evaluator disagrees with the logical circuit")

    widths = [len(blueprint.input_values)] + [len(layer) for layer in blueprint.forward_layers]
    if not all(is_power_of_two(width) for width in widths) or widths[-1] != 1:
        raise ValueError("all circuit widths must be powers of two and output width must be one")

    # old logical position -> new public position.  The scalar output is fixed.
    permutations: list[list[int]] = []
    for layer, width in enumerate(widths):
        permutation = list(range(width))
        if layer != len(widths) - 1:
            stream.shuffle(permutation)
        old_to_new = [0] * width
        for new, old in enumerate(permutation):
            old_to_new[old] = new
        permutations.append(old_to_new)

    public_forward: list[tuple[Gate, ...]] = []
    for stage_index, logical_gates in enumerate(blueprint.forward_layers):
        output = [ZERO_GATE] * len(logical_gates)
        child_permutation = permutations[stage_index]
        output_permutation = permutations[stage_index + 1]
        for old_output, gate in enumerate(logical_gates):
            if gate.a == gate.b == gate.c == 0:
                rewritten = ZERO_GATE
            else:
                rewritten = Gate(
                    gate.a,
                    gate.b,
                    gate.c,
                    child_permutation[gate.left],
                    child_permutation[gate.right],
                ).normalized()
            output[output_permutation[old_output]] = rewritten
        public_forward.append(tuple(output))

    public_inputs = [0] * widths[0]
    for old_position, value in enumerate(blueprint.input_values):
        public_inputs[permutations[0][old_position]] = value % MODULUS

    hidden_values = evaluate_forward(public_inputs, public_forward)
    if hidden_values[-1][0] != logical_values[-1][0]:
        raise AssertionError("layer permutation changed the circuit output")

    public_widths = list(reversed(widths))
    public_layers: list[Mapping[str, Any]] = []
    for gates, output_width, child_width in zip(
        reversed(public_forward), public_widths[:-1], public_widths[1:], strict=True
    ):
        public_layers.append(
            {
                "output_width": output_width,
                "child_width": child_width,
                "gates": [_serialize_gate(gate) for gate in gates],
            }
        )

    public_instance: Mapping[str, Any] = {
        "format_version": FORMAT_VERSION,
        "field": {"modulus_hex": MODULUS_HEX, "element_codec": CODEC_NAME},
        "index_bits": "lsb_first",
        "layer_widths": public_widths,
        "layers": public_layers,
        "input_values": [encode_field(value) for value in public_inputs],
    }
    circuit = parse_public_instance(public_instance)
    if evaluate_circuit(circuit)[0][0] != logical_values[-1][0]:
        raise AssertionError("serialized public circuit failed its independent evaluation")
    public_bytes = len(
        json.dumps(public_instance, sort_keys=True, separators=(",", ":")).encode("utf-8")
    )
    if public_bytes > MAX_PUBLIC_BYTES:
        raise ValueError("canonical public GKR instance exceeds 64 MiB")
    metadata = {
        "depth": circuit.depth,
        "total_positions": circuit.total_positions,
        "barriers": circuit.barriers,
        "public_bytes": public_bytes,
    }
    return public_instance, metadata


def _parse_gate(raw: object, child_width: int) -> Gate:
    if not isinstance(raw, Mapping) or set(raw) != {"a", "b", "c", "left", "right"}:
        raise ValueError("malformed GKR gate")
    left = raw.get("left")
    right = raw.get("right")
    if not _is_integer(left) or not _is_integer(right):
        raise ValueError("GKR child indices must be strict integers")
    assert isinstance(left, int) and isinstance(right, int)
    if not 0 <= left < child_width or not 0 <= right < child_width:
        raise ValueError("GKR child index is out of range")
    gate = Gate(
        decode_field(raw.get("a")),
        decode_field(raw.get("b")),
        decode_field(raw.get("c")),
        left,
        right,
    )
    if gate.a == gate.b == gate.c == 0 and (gate.left != 0 or gate.right != 0):
        raise ValueError("zero GKR gates must use canonical child indices")
    return gate


def parse_public_instance(raw: Mapping[str, Any]) -> ParsedCircuit:
    required = {
        "format_version",
        "field",
        "index_bits",
        "layer_widths",
        "layers",
        "input_values",
    }
    if set(raw) != required or raw.get("format_version") != FORMAT_VERSION:
        raise ValueError("malformed or unsupported GKR public instance")
    if raw.get("field") != {"modulus_hex": MODULUS_HEX, "element_codec": CODEC_NAME}:
        raise ValueError("unsupported GKR field description")
    if raw.get("index_bits") != "lsb_first":
        raise ValueError("unsupported GKR index convention")

    raw_widths = raw.get("layer_widths")
    if not isinstance(raw_widths, list) or len(raw_widths) < 2:
        raise ValueError("GKR layer_widths must contain output and input widths")
    if not all(_is_integer(width) and is_power_of_two(width) for width in raw_widths):
        raise ValueError("GKR layer widths must be strict positive powers of two")
    widths = tuple(int(width) for width in raw_widths)
    if widths[0] != 1 or max(width.bit_length() - 1 for width in widths) > MAX_INDEX_BITS:
        raise ValueError("GKR layer widths violate the formal envelope")

    raw_layers = raw.get("layers")
    if not isinstance(raw_layers, list) or len(raw_layers) != len(widths) - 1:
        raise ValueError("GKR layer array length is inconsistent")
    layers: list[tuple[Gate, ...]] = []
    for index, raw_layer in enumerate(raw_layers):
        if not isinstance(raw_layer, Mapping) or set(raw_layer) != {
            "output_width",
            "child_width",
            "gates",
        }:
            raise ValueError("malformed GKR layer")
        if raw_layer.get("output_width") != widths[index]:
            raise ValueError("GKR output_width is inconsistent")
        if raw_layer.get("child_width") != widths[index + 1]:
            raise ValueError("GKR child_width is inconsistent")
        raw_gates = raw_layer.get("gates")
        if not isinstance(raw_gates, list) or len(raw_gates) != widths[index]:
            raise ValueError("GKR gate count is inconsistent")
        layers.append(tuple(_parse_gate(gate, widths[index + 1]) for gate in raw_gates))

    raw_inputs = raw.get("input_values")
    if not isinstance(raw_inputs, list) or len(raw_inputs) != widths[-1]:
        raise ValueError("GKR input_values length is inconsistent")
    inputs = tuple(decode_field(value) for value in raw_inputs)
    circuit = ParsedCircuit(widths, tuple(layers), inputs)
    if circuit.total_positions > MAX_TOTAL_POSITIONS or circuit.barriers > MAX_BARRIERS:
        raise ValueError("GKR circuit violates the formal resource envelope")
    return circuit


def random_values(stream: DeterministicStream, count: int) -> list[int]:
    return [stream.field() for _ in range(count)]


def random_nonzero_values(stream: DeterministicStream, count: int) -> list[int]:
    result: list[int] = []
    while len(result) < count:
        value = stream.field()
        if value:
            result.append(value)
    return result


def width_bits(width: int) -> int:
    if not is_power_of_two(width):
        raise ValueError("width must be a power of two")
    return int(log2(width))
