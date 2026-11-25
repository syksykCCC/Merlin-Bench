"""C01: independently hidden anchored binary paths."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from aipbench.tasks.new_homomorphism_cases.common import NewHomomorphismStream
from aipbench.tasks.shared.homomorphism_cases.common import (
    CaseBlueprint,
    complete_graph_edges,
    integer_parameter,
    normalized_edges,
)

CASE_ID: Final = "c01"
DEFAULT_PARAMETERS: Final[Mapping[str, Any]] = {
    "num_components": 64,
    "component_size": 16,
    "target_order": 3,
}


def build(stream: NewHomomorphismStream, parameters: Mapping[str, Any]) -> CaseBlueprint:
    unexpected = set(parameters) - set(DEFAULT_PARAMETERS)
    if unexpected:
        raise ValueError(f"unsupported c01 parameters: {sorted(unexpected)!r}")
    num_components = integer_parameter(parameters, "num_components", minimum=1)
    component_size = integer_parameter(parameters, "component_size", minimum=3)
    target_order = integer_parameter(parameters, "target_order", minimum=3)
    if num_components * component_size > 100_000 or target_order > 32:
        raise ValueError("c01 profile exceeds the supported envelope")

    edges: set[tuple[int, int]] = set()
    allowed: list[frozenset[int]] = []
    mapping: list[int] = []
    for component in range(num_components):
        start = component * component_size
        colors = list(range(target_order))
        stream.shuffle(colors)
        first, second = colors[:2]
        for offset in range(component_size):
            color = first if offset % 2 == 0 else second
            mapping.append(color)
            allowed.append(frozenset({color}) if offset == 0 else frozenset({first, second}))
            if offset:
                edges.add((start + offset - 1, start + offset))

    return CaseBlueprint(
        source_num_vertices=num_components * component_size,
        source_edges=normalized_edges(edges),
        target_num_vertices=target_order,
        target_edges=complete_graph_edges(target_order),
        allowed_targets=tuple(allowed),
        reference_mapping=tuple(mapping),
        metadata={
            "mathematical_family": "anchored_binary_path_components",
            "num_components": num_components,
            "component_size": component_size,
            "unique_mapping": True,
        },
    )


__all__ = ["CASE_ID", "DEFAULT_PARAMETERS", "build"]
