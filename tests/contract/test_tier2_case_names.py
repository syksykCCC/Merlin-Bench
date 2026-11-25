from __future__ import annotations

from pathlib import Path

import yaml

from aipbench.transport.http.observer import CASE_TITLES

ROOT = Path(__file__).resolve().parents[2]
TIER2_TASK_DIRECTORIES = {
    "T2.1": ("t2.new_graph_non_isomorphism", "new_graph_non_isomorphism", 7),
    "T2.2": (
        "t2.new_boolean_hypercube_sumcheck",
        "new_boolean_hypercube_sumcheck",
        7,
    ),
    "T2.3": ("t2.new_gkr_layered_circuit", "new_gkr_layered_circuit", 7),
    "T2.4": ("t2.image_size_lower_bound", "image_size_lower_bound", 6),
    "T2.5": ("t2.new_shamir_tqbf", "new_shamir_tqbf", 6),
    "T2.6": (
        "t2.new_hamiltonicity_bind_open",
        "new_hamiltonicity_bind_open",
        7,
    ),
}


def test_tier2_maintainer_case_names_match_catalog_but_observer_stays_opaque() -> None:
    catalog = yaml.safe_load(
        (ROOT / "catalog" / "benchmark_catalog.yaml").read_text(encoding="utf-8")
    )
    tier2 = next(tier for tier in catalog["tiers"] if tier["id"] == "T2")
    tasks = {task["id"]: task for task in tier2["tasks"]}

    assert set(tasks) == set(TIER2_TASK_DIRECTORIES)
    checked = 0
    for catalog_task_id, (runtime_task_id, directory, case_count) in TIER2_TASK_DIRECTORIES.items():
        catalog_cases = {case["id"].lower(): case for case in tasks[catalog_task_id]["cases"]}
        expected_ids = {f"c{index:02d}" for index in range(1, case_count + 1)}
        assert set(catalog_cases) == expected_ids

        for case_id, catalog_case in catalog_cases.items():
            case_path = (
                ROOT / "tasks" / "tier2_interactive" / directory / "cases" / f"{case_id}.yaml"
            )
            case_yaml = yaml.safe_load(case_path.read_text(encoding="utf-8"))
            assert case_yaml["id"] == case_id
            assert case_yaml["title"] == catalog_case["name"]
            assert case_yaml["title"] != case_id.upper()
            assert CASE_TITLES[(runtime_task_id, case_id)] == case_id.upper()
            checked += 1

    assert checked == 40
