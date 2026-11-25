from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import yaml
from typer.testing import CliRunner

import aipbench.cli.main as cli

RUNNER = CliRunner()


def test_task_inspect_is_lazy_and_does_not_report_an_empty_case_inventory(
    monkeypatch: Any,
) -> None:
    class InspectOnlyRegistry:
        def inspect(self, task_id: str) -> dict[str, Any]:
            assert task_id == "t1.example"
            return {
                "id": task_id,
                "version": "1.0.0",
                "title": "Example",
                "cases": {},
                "metadata": {},
            }

        def get(self, task_id: str) -> Any:  # pragma: no cover - must stay lazy
            raise AssertionError(f"task inspect imported plugin {task_id}")

    monkeypatch.setattr(cli, "default_registry", InspectOnlyRegistry)

    result = RUNNER.invoke(cli.app, ["task", "inspect", "t1.example"])

    assert result.exit_code == 0, result.output
    assert yaml.safe_load(result.stdout) == {
        "id": "t1.example",
        "version": "1.0.0",
        "title": "Example",
    }


def test_case_list_reads_the_plugin_inventory_in_stable_order(monkeypatch: Any) -> None:
    class Plugin:
        case_parameters: Mapping[str, Mapping[str, Any]] = {
            "c01": {"size": 4},
            "c02": {"size": 8},
        }

    class PluginRegistry:
        def get(self, task_id: str) -> Plugin:
            assert task_id == "t1.example"
            return Plugin()

    monkeypatch.setattr(cli, "default_registry", PluginRegistry)

    result = RUNNER.invoke(cli.app, ["case", "list", "--task", "t1.example"])

    assert result.exit_code == 0, result.output
    assert result.stdout.splitlines() == ["c01", "c02"]
