"""Merlin-Bench: an Agent-as-Merlin interactive-proof benchmark runtime."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("merlin-bench")
except PackageNotFoundError:  # pragma: no cover - source checkout without installation
    __version__ = "0.1.0"

__all__ = ["__version__"]
