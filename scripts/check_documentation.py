#!/usr/bin/env python3
"""Validate release documentation links and task-document coverage."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import unquote

import yaml

from aipbench.registry import default_registry

ROOT = Path(__file__).resolve().parents[1]
EXCLUDED_PARTS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "runs",
}
LINK_RE = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")
EXTERNAL_PREFIXES = ("http://", "https://", "mailto:", "aipbench:", "data:")


def _included(path: Path) -> bool:
    relative = path.relative_to(ROOT)
    return not any(
        part in EXCLUDED_PARTS
        or part.startswith("pytest-of-")
        or part.startswith(".tmp_")
        or part.endswith(".egg-info")
        for part in relative.parts
    )


def markdown_files() -> list[Path]:
    return sorted(path for path in ROOT.rglob("*.md") if path.is_file() and _included(path))


def check_text_integrity(files: list[Path]) -> list[str]:
    """Reject corrupted UTF-8, replacement characters and embedded control bytes."""

    errors: list[str] = []
    for source in files:
        relative = source.relative_to(ROOT).as_posix()
        raw = source.read_bytes()
        if b"\r" in raw:
            errors.append(f"{relative}: contains CR bytes; release Markdown must use LF")
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            errors.append(f"{relative}: invalid UTF-8: {exc}")
            continue
        if "\ufffd" in text:
            errors.append(f"{relative}: contains Unicode replacement character U+FFFD")
        controls = sorted({ord(character) for character in text if ord(character) < 32})
        unexpected = [value for value in controls if value not in (9, 10)]
        if unexpected:
            rendered = ", ".join(f"U+{value:04X}" for value in unexpected)
            errors.append(f"{relative}: contains unexpected control characters: {rendered}")
    return errors


def _link_target(raw: str) -> str:
    target = raw.strip()
    if target.startswith("<") and ">" in target:
        target = target[1 : target.index(">")]
    elif " " in target:
        # Optional Markdown link titles are irrelevant for local path resolution.
        target = target.split(" ", 1)[0]
    return unquote(target)


def check_links(files: list[Path]) -> list[str]:
    errors: list[str] = []
    for source in files:
        text = source.read_text(encoding="utf-8")
        for match in LINK_RE.finditer(text):
            target = _link_target(match.group(1))
            if not target or target.startswith("#") or target.lower().startswith(EXTERNAL_PREFIXES):
                continue
            path_part = target.split("#", 1)[0]
            if not path_part:
                continue
            destination = (source.parent / path_part).resolve()
            if not destination.exists():
                line = text.count("\n", 0, match.start()) + 1
                relative = source.relative_to(ROOT).as_posix()
                errors.append(f"{relative}:{line}: missing local link target {target!r}")
    return errors


def check_task_documentation() -> list[str]:
    errors: list[str] = []
    registry = default_registry()
    task_ids = registry.ids()
    index_text = (ROOT / "docs" / "README.md").read_text(encoding="utf-8")
    if len(task_ids) != 15:
        errors.append(f"registry exposes {len(task_ids)} tasks instead of 15")

    for task_id in task_ids:
        manifest = registry.inspect(task_id)
        public_schema = manifest.get("instance", {}).get("public_schema")
        if not isinstance(public_schema, str):
            errors.append(f"{task_id}: manifest has no public schema path")
            continue
        task_directory = ROOT / Path(public_schema).parent.parent
        for filename in ("README.md", "TASK_SPECIFICATION.md", "protocol.md", "task.yaml"):
            if not (task_directory / filename).is_file():
                errors.append(f"{task_id}: missing {task_directory.relative_to(ROOT) / filename}")
        plugin = registry.get(task_id)
        case_ids = tuple(plugin.case_parameters)
        yaml_ids = tuple(path.stem for path in sorted((task_directory / "cases").glob("c*.yaml")))
        if yaml_ids != case_ids:
            errors.append(
                f"{task_id}: case YAML IDs {yaml_ids!r} do not match plugin IDs {case_ids!r}"
            )
        if task_id not in index_text:
            errors.append(f"{task_id}: missing from docs/README.md")
    return errors


def check_catalog_contract() -> list[str]:
    """Cross-check the human catalog against every executable case inventory."""

    errors: list[str] = []
    catalog_path = ROOT / "catalog" / "benchmark_catalog.yaml"
    try:
        catalog: Any = yaml.safe_load(catalog_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        return [f"cannot load catalog/benchmark_catalog.yaml: {exc}"]
    if not isinstance(catalog, dict) or not isinstance(catalog.get("benchmark"), dict):
        return ["catalog/benchmark_catalog.yaml: expected benchmark and tiers mappings"]
    if not isinstance(catalog.get("tiers"), list):
        return ["catalog/benchmark_catalog.yaml: tiers must be a list"]

    registry = default_registry()
    registry_ids = set(registry.ids())
    plugin_case_count = sum(len(registry.get(task_id).case_parameters) for task_id in registry_ids)
    catalog_tasks: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for tier in catalog["tiers"]:
        if not isinstance(tier, dict) or not isinstance(tier.get("tasks"), list):
            errors.append("catalog: every tier must be a mapping with a tasks list")
            continue
        catalog_tasks.extend((tier, task) for task in tier["tasks"] if isinstance(task, dict))

    declared_count = catalog["benchmark"].get("case_count")
    catalog_case_count = sum(
        len(task.get("cases", []))
        for _, task in catalog_tasks
        if isinstance(task.get("cases"), list)
    )
    if len(registry_ids) != 15:
        errors.append(f"registry exposes {len(registry_ids)} tasks instead of 15")
    if len(catalog_tasks) != 15:
        errors.append(f"catalog exposes {len(catalog_tasks)} tasks instead of 15")
    if plugin_case_count != 100:
        errors.append(f"plugins expose {plugin_case_count} cases instead of 100")
    if declared_count != 100:
        errors.append(f"catalog benchmark.case_count is {declared_count!r} instead of 100")
    if catalog_case_count != declared_count:
        errors.append(
            "catalog case rows do not equal benchmark.case_count: "
            f"{catalog_case_count} != {declared_count!r}"
        )
    if catalog_case_count != plugin_case_count:
        errors.append(
            f"catalog and plugins disagree on total cases: {catalog_case_count} != "
            f"{plugin_case_count}"
        )

    seen_runtime_ids: set[str] = set()
    for tier, catalog_task in catalog_tasks:
        catalog_task_id = catalog_task.get("id", "<missing-id>")
        runtime_id = catalog_task.get("runtime_id")
        if not isinstance(runtime_id, str):
            errors.append(f"catalog {catalog_task_id}: missing string runtime_id")
            continue
        if runtime_id in seen_runtime_ids:
            errors.append(f"catalog {catalog_task_id}: duplicate runtime_id {runtime_id}")
        seen_runtime_ids.add(runtime_id)
        if runtime_id not in registry_ids:
            errors.append(f"catalog {catalog_task_id}: unknown runtime_id {runtime_id}")
            continue

        manifest = registry.inspect(runtime_id)
        expected_tier = f"T{manifest['tier']}"
        if tier.get("id") != expected_tier:
            errors.append(
                f"catalog {catalog_task_id}: tier {tier.get('id')!r} does not match "
                f"runtime tier {expected_tier}"
            )
        plugin_case_parameters = registry.get(runtime_id).case_parameters
        plugin_case_ids = tuple(plugin_case_parameters)
        catalog_cases = catalog_task.get("cases")
        if not isinstance(catalog_cases, list) or not all(
            isinstance(case, dict) for case in catalog_cases
        ):
            errors.append(f"catalog {catalog_task_id}: cases must be a list of mappings")
            continue
        # Catalog uses presentation IDs such as C01; runtime/YAML use canonical c01.
        catalog_presentation_ids = tuple(str(case.get("id", "")) for case in catalog_cases)
        expected_presentation_ids = tuple(case_id.upper() for case_id in plugin_case_ids)
        if catalog_presentation_ids != expected_presentation_ids:
            errors.append(
                f"catalog {catalog_task_id}: presentation case IDs "
                f"{catalog_presentation_ids!r} do not match canonical plugin IDs "
                f"{expected_presentation_ids!r}"
            )

        instance = manifest.get("instance")
        if not isinstance(instance, dict) or not isinstance(instance.get("public_schema"), str):
            errors.append(f"{runtime_id}: manifest has no public schema path")
            continue
        task_directory = ROOT / Path(instance["public_schema"]).parent.parent
        for case_id, catalog_case in zip(plugin_case_ids, catalog_cases, strict=False):
            case_path = task_directory / "cases" / f"{case_id}.yaml"
            try:
                case_yaml: Any = yaml.safe_load(case_path.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, yaml.YAMLError) as exc:
                errors.append(f"{runtime_id}/{case_id}: cannot load case YAML: {exc}")
                continue
            if not isinstance(case_yaml, dict):
                errors.append(f"{runtime_id}/{case_id}: case YAML must be a mapping")
                continue
            expected = {
                "id": case_id,
                "title": catalog_case.get("name"),
                "difficulty": catalog_case.get("case_profile", catalog_case.get("difficulty")),
            }
            actual = {key: case_yaml.get(key) for key in expected}
            if actual != expected:
                errors.append(
                    f"{runtime_id}/{case_id}: catalog/YAML identity mismatch: "
                    f"expected {expected!r}, got {actual!r}"
                )
            if case_yaml.get("parameters") != plugin_case_parameters[case_id]:
                errors.append(
                    f"{runtime_id}/{case_id}: case YAML parameters do not match "
                    "plugin.case_parameters"
                )

    missing_runtime_ids = registry_ids - seen_runtime_ids
    extra_runtime_ids = seen_runtime_ids - registry_ids
    if missing_runtime_ids:
        errors.append(f"catalog is missing runtime tasks: {sorted(missing_runtime_ids)!r}")
    if extra_runtime_ids:
        errors.append(f"catalog has unknown runtime tasks: {sorted(extra_runtime_ids)!r}")
    return errors


def main() -> int:
    files = markdown_files()
    errors = [
        *check_text_integrity(files),
        *check_links(files),
        *check_task_documentation(),
        *check_catalog_contract(),
    ]
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(f"Documentation check passed: {len(files)} Markdown files, 15 active tasks.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
