from __future__ import annotations

from pathlib import Path

import yaml

from aipbench.transport.http.observer import CASE_TITLES

ROOT = Path(__file__).resolve().parents[2]

EXPECTED = {
    "t3.machine_checked_mathematics": (
        "machine_checked_mathematics",
        (
            ("c01", "Dense binary linear certificate", "H1"),
            ("c02", "Shuffled CRT reconstruction certificate", "H1"),
            ("c03", "Hidden line-graph root certificate", "H2"),
            ("c04", "Anonymous affine-plane decoding certificate", "H3"),
            ("c05", "Anonymous modular column equivalence", "H3"),
            ("c06", "Composite cube-root certificate", "H3"),
            ("c07", "Anonymous modular subset certificate", "H4"),
            ("c08", "Anonymous binary syndrome certificate", "H4"),
        ),
    ),
    "t3.dafny_verified_programs": (
        "dafny_verified_programs",
        (
            ("c01", "Stable partition preservation", "H1"),
            ("c02", "Boundary-safe lower-bound search", "H1"),
            ("c03", "Capacity-constrained reservation update", "H2"),
            ("c04", "Precedence-constrained earliest schedule", "H2"),
            ("c05", "Dependency-order validation", "H3"),
            ("c06", "Audited priority firewall batch evaluation", "H3"),
            ("c07", "Reference-counted handle-table invariant preservation", "H4"),
            ("c08", "Free-list memory-pool invariant preservation", "H4"),
        ),
    ),
    "t3.drat_bounded_hardware_safety": (
        "drat_bounded_hardware_safety",
        (
            ("c01", "FIFO occupancy safety", "H1"),
            ("c02", "FIFO underflow safety", "H1"),
            ("c03", "Round-robin mutual exclusion", "H2"),
            ("c04", "Round-robin bounded fairness", "H3"),
            ("c05", "Credit-router conservation", "H3"),
            ("c06", "Credit-router forwarding safety", "H3"),
            ("c07", "Pipeline flush-stall safety", "H4"),
            ("c08", "Pipeline writeback consistency", "H4"),
        ),
    ),
}


def test_tier3_case_yaml_uses_one_named_shape_and_matches_observer() -> None:
    for task_id, (directory, cases) in EXPECTED.items():
        case_dir = ROOT / "tasks" / "tier3_applied" / directory / "cases"
        assert [path.stem for path in sorted(case_dir.glob("c*.yaml"))] == [
            case_id for case_id, _, _ in cases
        ]
        for case_id, title, difficulty in cases:
            record = yaml.safe_load((case_dir / f"{case_id}.yaml").read_text(encoding="utf-8"))
            assert set(record) == {"id", "title", "difficulty", "parameters"}
            assert (record["id"], record["title"], record["difficulty"]) == (
                case_id,
                title,
                difficulty,
            )
            assert CASE_TITLES[(task_id, case_id)] == title


def test_tier3_catalog_names_match_case_yaml() -> None:
    catalog = yaml.safe_load((ROOT / "catalog" / "benchmark_catalog.yaml").read_text("utf-8"))
    tier3 = next(tier for tier in catalog["tiers"] if tier["id"] == "T3")
    catalog_tasks = {task["id"]: task for task in tier3["tasks"]}
    for ordinal, (_, (_, expected_cases)) in enumerate(EXPECTED.items(), start=1):
        catalog_task = catalog_tasks[f"T3.{ordinal}"]
        assert [(case["id"].lower(), case["name"]) for case in catalog_task["cases"]] == [
            (case_id, title) for case_id, title, _ in expected_cases
        ]
