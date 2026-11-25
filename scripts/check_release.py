#!/usr/bin/env python3
"""Check dataset counts, fixture integrity, English text, and release contents."""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

from aipbench.registry import default_registry
from aipbench.tier3_plus.fixtures import fixture_plugin, inventory

ROOT = Path(__file__).resolve().parents[1]
IGNORED = {".git", ".venv", "__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache"}
FORBIDDEN = {"experiments", "results", "trajectories", "runs", "outputs"}
HAN_TEXT = re.compile(r"[\u3400-\u9fff\uf900-\ufaff\U00020000-\U000323af]")


def check_files() -> int:
    count = 0
    for path in sorted(ROOT.rglob("*")):
        relative = path.relative_to(ROOT)
        if not path.is_file():
            continue
        if any(part in IGNORED or part.endswith(".egg-info") for part in relative.parts):
            continue
        if path.suffix in {".pyc", ".pyo"}:
            continue
        if FORBIDDEN.intersection(relative.parts) or path.name in {
            ".aipbench-connection.json",
            "signing_private_key.json",
            ".env",
            "transcript.jsonl",
        }:
            raise ValueError(f"generated or private artifact in release: {relative}")
        content = path.read_bytes()
        text = content.decode("utf-8")
        if path.suffix == ".json":
            # Check decoded strings too, including escaped Unicode in JSON.
            text = json.dumps(json.loads(text), ensure_ascii=False)
        if HAN_TEXT.search(relative.as_posix() + text):
            raise ValueError(f"non-English CJK text in release: {relative}")
        count += 1
    return count


def check_inventory() -> None:
    catalog = json.loads((ROOT / "catalog/release_catalog.json").read_text(encoding="utf-8"))
    registry = default_registry()
    base = {(task, case) for task in registry.ids() for case in registry.get(task).case_parameters}
    fixtures = inventory()
    assert len(base) == 100
    assert Counter(case["domain"] for case in fixtures) == {"lean": 8, "dafny": 8, "drat": 8}
    assert len({case["canonical_instance_sha256"] for case in fixtures}) == 24
    rows = catalog["cases"]
    assert catalog["case_count"] == len(rows) == len({row["id"] for row in rows}) == 124
    assert {(row["task_id"], row["case_id"]) for row in rows if row["split"] == "base"} == base
    assert {row["fixture_id"] for row in rows if row["split"] == "tier3_plus"} == {
        case["id"] for case in fixtures
    }
    for row in rows:
        assert (ROOT / row["path"]).exists(), row["path"]
        if row["split"] == "base":
            assert row["task_version"] == registry.inspect(row["task_id"])["version"]
    for case in fixtures:
        fixture_plugin(case["id"])


def main() -> int:
    check_inventory()
    count = check_files()
    print(
        f"Release verified: 100 + 24 = 124 cases; {count} files; fixture integrity and content checks passed."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
