"""Use the existing Arthur CLI with the long-horizon protocol registered."""

from __future__ import annotations

from typing import Any

from aipbench.audit import audit_run
from aipbench.cli import main as upstream
from aipbench.tier3_plus.fixtures import extended_registry


def _audit(*args: Any, **kwargs: Any) -> Any:
    kwargs.setdefault("registry", extended_registry())
    return audit_run(*args, **kwargs)


def main() -> None:
    upstream.default_registry = extended_registry  # type: ignore[attr-defined]
    upstream.audit_run = _audit  # type: ignore[attr-defined]
    upstream.app()


if __name__ == "__main__":
    main()
