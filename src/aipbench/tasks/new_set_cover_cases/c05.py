"""C05: calibrated width-18 weighted hitting-set path."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from typing import Any, Final

from aipbench.tasks.new_set_cover_cases import c04
from aipbench.tasks.new_set_cover_cases.common import CaseBlueprint, NewSetCoverStream

CASE_ID: Final = "c05"
DEFAULT_PARAMETERS: Final[Mapping[str, Any]] = {
    "num_bags": 124,
    "bag_width": 18,
    "overlap_width": 9,
    "clauses_per_bag": 32,
    "min_weight": 19,
    "max_weight": 1_993,
}


def build(stream: NewSetCoverStream, parameters: Mapping[str, Any]) -> CaseBlueprint:
    blueprint = c04.build(stream, parameters)
    return replace(
        blueprint,
        metadata={
            **dict(blueprint.metadata),
            "mathematical_family": "marked_width18_weighted_hitting_set_path",
            "optimality_certificate": "exact_width18_separator_dynamic_program",
        },
    )


__all__ = ["CASE_ID", "DEFAULT_PARAMETERS", "build"]
