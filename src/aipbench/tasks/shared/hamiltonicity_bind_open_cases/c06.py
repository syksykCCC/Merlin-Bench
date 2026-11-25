"""Shared primitives used by the current Merlin-Bench tasks."""

from __future__ import annotations


def reflected_combinations(n: int, k: int) -> list[tuple[int, ...]]:
    if k == 0:
        return [()]
    if k == n:
        return [tuple(range(n))]
    first = reflected_combinations(n - 1, k)
    second = [tuple((*subset, n - 1)) for subset in reversed(reflected_combinations(n - 1, k - 1))]
    return first + second
