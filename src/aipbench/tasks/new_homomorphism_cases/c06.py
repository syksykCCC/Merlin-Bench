"""C06: an independently randomized C04 difficulty replicate."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from typing import Any, Final

from aipbench.tasks.new_homomorphism_cases import c04
from aipbench.tasks.new_homomorphism_cases.common import NewHomomorphismStream
from aipbench.tasks.shared.homomorphism_cases.common import CaseBlueprint

CASE_ID: Final = "c06"
DEFAULT_PARAMETERS: Final[Mapping[str, Any]] = dict(c04.DEFAULT_PARAMETERS)
_DOMAIN_TAG: Final = b"aipbench/new-list-homomorphism/c06-replicate/v1\x00"


def build(stream: NewHomomorphismStream, parameters: Mapping[str, Any]) -> CaseBlueprint:
    """Build C04's frozen profile from a C06-specific derived stream."""

    replicate_stream = NewHomomorphismStream(_DOMAIN_TAG + stream.take(32))
    blueprint = c04.build(replicate_stream, parameters)
    return replace(
        blueprint,
        metadata={
            **dict(blueprint.metadata),
            "difficulty_replicate_of": "c04",
            "replicate_domain": "c06-replicate/v1",
        },
    )


__all__ = ["CASE_ID", "DEFAULT_PARAMETERS", "build"]
