"""Independent deterministic primitives for New List Graph Homomorphism."""

from __future__ import annotations

from typing import Final

from aipbench.tasks.shared.homomorphism_cases.common import DeterministicStream


class NewHomomorphismStream(DeterministicStream):
    """Deterministic stream with a task-specific domain."""

    _DOMAIN: Final = b"aipbench/new-list-graph-homomorphism/generator/v1\x00"


__all__ = ["NewHomomorphismStream"]
