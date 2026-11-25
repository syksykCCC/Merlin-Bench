from __future__ import annotations

import runpy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_catalog_registry_plugin_and_case_yaml_are_one_inventory() -> None:
    checker = runpy.run_path(str(ROOT / "scripts" / "check_documentation.py"))
    assert checker["check_catalog_contract"]() == []
