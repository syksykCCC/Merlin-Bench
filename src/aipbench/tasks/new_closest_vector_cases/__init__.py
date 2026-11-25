"""Independent case registry for New Structured Closest Vector."""

from aipbench.tasks.new_closest_vector_cases.common import (
    NewClosestVectorStream,
    finalize_blueprint,
)
from aipbench.tasks.new_closest_vector_cases.registry import CASE_DEFINITIONS, CASE_PARAMETERS

__all__ = [
    "CASE_DEFINITIONS",
    "CASE_PARAMETERS",
    "NewClosestVectorStream",
    "finalize_blueprint",
]
