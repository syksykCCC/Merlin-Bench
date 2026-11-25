"""Shared data structures for the eight Dafny verification cases."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Final


@dataclass(frozen=True)
class DafnyCaseBlueprint:
    """A public Dafny challenge plus a maintainer reference implementation."""

    title: str
    challenge_source: str
    harness_source: str
    reference_solution: str
    public_features: dict[str, int | str]


class DeterministicStream:
    """Small SHA-256 counter stream used only to vary executable examples."""

    _DOMAIN: Final = b"aipbench/t3-dafny-verified-programs/cases/v1\x00"

    def __init__(self, seed: bytes) -> None:
        self._seed = bytes(seed)
        self._counter = 0

    def randbelow(self, bound: int) -> int:
        if bound <= 0:
            raise ValueError("bound must be positive")
        while True:
            block = hashlib.sha256(
                self._DOMAIN + self._seed + self._counter.to_bytes(8, "big")
            ).digest()
            self._counter += 1
            value = int.from_bytes(block, "big")
            limit = (1 << 256) - ((1 << 256) % bound)
            if value < limit:
                return value % bound

    def randint(self, lower: int, upper: int) -> int:
        if lower > upper:
            raise ValueError("invalid inclusive range")
        return lower + self.randbelow(upper - lower + 1)


def dafny_int_seq(values: list[int] | tuple[int, ...]) -> str:
    return "[" + ", ".join(str(value) for value in values) + "]"


def dafny_bool_seq(values: list[bool] | tuple[bool, ...]) -> str:
    return "[" + ", ".join("true" if value else "false" for value in values) + "]"
