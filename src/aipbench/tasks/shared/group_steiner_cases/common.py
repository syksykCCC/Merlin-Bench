"""Shared primitives used by the current Merlin-Bench tasks."""

from __future__ import annotations

import hashlib
from typing import Any, Final


class DeterministicStream:
    """Domain-separated SHA-256 stream used only for instance generation."""

    _DOMAIN: Final = b"aipbench/rooted-group-steiner-tree/generator/v1\x00"

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

    def randint(self, lower: int, upper: int) -> int:
        if lower > upper:
            raise ValueError("lower must not exceed upper")
        return lower + self.randbelow(upper - lower + 1)

    def shuffle(self, values: list[Any]) -> None:
        for index in range(len(values) - 1, 0, -1):
            swap_index = self.randbelow(index + 1)
            values[index], values[swap_index] = values[swap_index], values[index]
