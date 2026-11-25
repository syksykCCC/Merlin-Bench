"""Shared primitives used by the current Merlin-Bench tasks."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any


class CircuitBuilder:
    """Build a strictly topological Boolean gate table."""

    def __init__(self, num_inputs: int) -> None:
        self.num_inputs = num_inputs
        self.gates: list[dict[str, Any]] = []

    def _append(self, gate: dict[str, Any]) -> int:
        wire = self.num_inputs + len(self.gates)
        self.gates.append(gate)
        return wire

    def const(self, value: int) -> int:
        return self._append({"op": "const", "value": value})

    def negate(self, wire: int) -> int:
        return self._append({"op": "not", "input": wire})

    def binary(self, op: str, left: int, right: int) -> int:
        return self._append({"op": op, "left": left, "right": right})

    def ite(self, condition: int, zero: int, one: int) -> int:
        return self._append({"op": "ite", "condition": condition, "zero": zero, "one": one})

    def conjunction(self, wires: Sequence[int]) -> int:
        if not wires:
            return self.const(1)
        work = list(wires)
        while len(work) > 1:
            next_work: list[int] = []
            for index in range(0, len(work), 2):
                if index + 1 == len(work):
                    next_work.append(work[index])
                else:
                    next_work.append(self.binary("and", work[index], work[index + 1]))
            work = next_work
        return work[0]

    def disjunction(self, wires: Sequence[int]) -> int:
        if not wires:
            return self.const(0)
        work = list(wires)
        while len(work) > 1:
            next_work: list[int] = []
            for index in range(0, len(work), 2):
                if index + 1 == len(work):
                    next_work.append(work[index])
                else:
                    next_work.append(self.binary("or", work[index], work[index + 1]))
            work = next_work
        return work[0]


def add_semantic_padding(builder: CircuitBuilder, output: int, *, seed: bytes, case_id: str) -> int:
    """Vary the public encoding without changing the Boolean function."""

    digest = hashlib.sha256(b"aipbench/tqbf/" + case_id.encode() + b"/padding/" + seed).digest()
    result = output
    # Encode sixteen digest bits as equivalent gate identities.  A fixed number
    # of rounds prevents the short 1--3 round encoding from colliding often,
    # while keeping every instance comfortably below the public gate limit.
    for index in range(16):
        bit = (digest[index // 8] >> (index % 8)) & 1
        if bit == 0:
            result = builder.negate(builder.negate(result))
        else:
            one = builder.const(1)
            result = builder.binary("and", result, one)
    return result


@dataclass(frozen=True)
class TQBFBlueprint:
    quantifiers: tuple[str, ...]
    gates: tuple[Mapping[str, Any], ...]
    output: int
    family: str


def blueprint_to_public(blueprint: TQBFBlueprint) -> Mapping[str, Any]:
    return {
        "format_version": "aip-tqbf/1",
        "field_codec": "field61/hex-v1",
        "quantifiers": list(blueprint.quantifiers),
        "circuit": {
            "num_inputs": len(blueprint.quantifiers),
            "gates": [dict(gate) for gate in blueprint.gates],
            "output": blueprint.output,
        },
    }
