"""Shared primitives used by the current Merlin-Bench tasks."""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Final

MAX_EXACT_SEARCH_NODES: Final = 5_000_000

MAX_RANDBELOW_REJECTION_ATTEMPTS: Final = 128

MAX_NUM_ELEMENTS: Final = 4_096

MAX_NUM_SETS: Final = 10_000

MAX_TOTAL_INCIDENCE: Final = 100_000


class DeterministicStream:
    """Domain-separated deterministic byte stream for instance generation."""

    _DOMAIN: Final = b"aipbench/structured-set-cover/generator/v1\x00"

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
        candidate = 0
        for _ in range(MAX_RANDBELOW_REJECTION_ATTEMPTS):
            candidate = int.from_bytes(self.take(width), "big")
            if candidate < rejection_limit:
                return candidate % upper_exclusive
        # The failure probability is below 2^-128 even in the worst byte-width
        # interval.  Modulo reduction makes the generator total under a faulty
        # or adversarial byte source instead of leaving an unbounded loop.
        return candidate % upper_exclusive

    def shuffle(self, values: list[Any]) -> None:
        for index in range(len(values) - 1, 0, -1):
            swap_index = self.randbelow(index + 1)
            values[index], values[swap_index] = values[swap_index], values[index]


@dataclass(frozen=True)
class ExactCoverSolution:
    candidate_indices: tuple[int, ...]
    search_nodes: int


def _validate_candidates(
    universe_size: int,
    candidates: Sequence[frozenset[int]],
) -> int:
    if isinstance(universe_size, bool) or not isinstance(universe_size, int) or universe_size < 1:
        raise ValueError("set-cover universe size must be a positive integer")
    if universe_size > MAX_NUM_ELEMENTS:
        raise ValueError("set-cover universe size exceeds the task safety envelope")
    if not candidates:
        raise ValueError("set-cover candidate family must be nonempty")
    if len(candidates) > MAX_NUM_SETS:
        raise ValueError("set-cover candidate count exceeds the task safety envelope")
    seen: set[frozenset[int]] = set()
    set_size: int | None = None
    covered: set[int] = set()
    total_incidence = 0
    for candidate in candidates:
        if not isinstance(candidate, frozenset) or not candidate:
            raise ValueError("every logical candidate must be a nonempty frozenset")
        total_incidence += len(candidate)
        if total_incidence > MAX_TOTAL_INCIDENCE:
            raise ValueError("set-cover total incidence exceeds the task safety envelope")
        if any(
            isinstance(element, bool)
            or not isinstance(element, int)
            or not 0 <= element < universe_size
            for element in candidate
        ):
            raise ValueError("logical candidate contains an invalid universe element")
        if candidate in seen:
            raise ValueError("logical candidates must be incidence-distinct")
        seen.add(candidate)
        covered.update(candidate)
        if set_size is None:
            set_size = len(candidate)
        elif len(candidate) != set_size:
            raise ValueError("scaled T1.6 candidates must all have the same size")
    if len(covered) != universe_size:
        raise ValueError("logical candidate family does not cover the universe")
    assert set_size is not None
    if universe_size % set_size:
        raise ValueError("scaled T1.6 universe size must be divisible by candidate size")
    return set_size


def solve_exact_partition(
    universe_size: int,
    candidates: Sequence[frozenset[int]],
    *,
    max_nodes: int = MAX_EXACT_SEARCH_NODES,
) -> ExactCoverSolution:
    """Find an exact cover with deterministic iterative Algorithm X.

    The solver consumes only incidence data.  It deliberately has no access to
    case metadata, coordinates, or a planted selection.
    """

    set_size = _validate_candidates(universe_size, candidates)
    if isinstance(max_nodes, bool) or not isinstance(max_nodes, int) or max_nodes < 1:
        raise ValueError("max_nodes must be a positive integer")
    full_mask = (1 << universe_size) - 1
    masks = tuple(sum(1 << element for element in candidate) for candidate in candidates)
    incidence: list[list[int]] = [[] for _ in range(universe_size)]
    for candidate_index, candidate in enumerate(candidates):
        for element in candidate:
            incidence[element].append(candidate_index)

    # Each state is immutable, so backtracking cannot leak a mutation from one
    # branch into another.  MRV chooses the uncovered element with the fewest
    # candidates disjoint from the current partial exact cover.
    stack: list[tuple[int, tuple[int, ...]]] = [(0, ())]
    search_nodes = 0
    target_size = universe_size // set_size
    while stack:
        covered_mask, selected = stack.pop()
        search_nodes += 1
        if search_nodes > max_nodes:
            raise ValueError("scaled exact-cover search node envelope exceeded")
        if covered_mask == full_mask:
            if len(selected) != target_size:
                raise RuntimeError("exact-cover solver recovered an invalid selection size")
            return ExactCoverSolution(selected, search_nodes)
        if len(selected) >= target_size:
            continue

        best_options: list[int] | None = None
        remaining = full_mask ^ covered_mask
        while remaining:
            bit = remaining & -remaining
            element = bit.bit_length() - 1
            options = [
                candidate_index
                for candidate_index in incidence[element]
                if masks[candidate_index] & covered_mask == 0
            ]
            if not options:
                best_options = []
                break
            if best_options is None or len(options) < len(best_options):
                best_options = options
                if len(best_options) == 1:
                    break
            remaining ^= bit
        if not best_options:
            continue
        # Reverse push order so the smallest logical candidate index is tried
        # first when the LIFO stack is popped.
        for candidate_index in reversed(best_options):
            stack.append(
                (
                    covered_mask | masks[candidate_index],
                    (*selected, candidate_index),
                )
            )
    raise ValueError("logical T1.6 instance has no exact cover")
