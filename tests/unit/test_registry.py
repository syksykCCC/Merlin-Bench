from __future__ import annotations

import copy
import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
import yaml

from aipbench.core.errors import ManifestError
from aipbench.registry import (
    TaskRegistry,
    default_registry,
    loads_manifest,
    manifest_digest,
    validate_manifest,
)


def valid_manifest() -> dict[str, Any]:
    return {
        "id": "t1.example_task",
        "version": "1.2.3",
        "tier": 1,
        "title": "Example task",
        "plugin": {"entrypoint": "example_plugin:create_task"},
        "protocol": {
            "api_version": "aip/1",
            "mode": "one_shot",
            "public_coin": False,
            "one_shot_eval": True,
            "max_events": 1,
        },
        "randomness": {
            "model": "none",
            "reveal_on_terminal": False,
            "domain_separation": "not_applicable",
        },
        "resources": {
            "wall_time_seconds": 10,
            "cpu_cores": 1,
            "memory_mb": 128,
            "disk_mb": 128,
            "max_artifact_bytes": 1024,
            "max_events": 1,
        },
        "audit": {
            "replay_mode": "strict",
            "require_signature": True,
            "require_seed_commitment": False,
            "require_instance_digest": True,
            "require_event_chain": True,
        },
        "scoring": {"primary": "binary_accept"},
        "cases": {"c01": {"parameters": {"size": 4}}},
    }


def test_loads_yaml_manifest_and_exposes_mapping_interface() -> None:
    manifest = loads_manifest(yaml.safe_dump(valid_manifest(), sort_keys=False))

    assert manifest.id == "t1.example_task"
    assert manifest["plugin"]["entrypoint"] == "example_plugin:create_task"
    assert dict(manifest)["protocol"]["max_events"] == 1


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda value: value.pop("plugin"), "plugin"),
        (lambda value: value.update(tier=5), "tier"),
        (
            lambda value: value["protocol"].update(api_version="aip/2"),
            "api_version",
        ),
        (
            lambda value: value["resources"].update(max_events=2),
            "max_events",
        ),
        (
            lambda value: value["randomness"].update(reveal_on_terminal=True),
            "randomness",
        ),
    ],
)
def test_invalid_manifests_are_rejected(mutation: Any, message: str) -> None:
    data = valid_manifest()
    mutation(data)

    with pytest.raises(ManifestError, match=message):
        validate_manifest(data)


def test_manifest_digest_is_canonical() -> None:
    first = valid_manifest()
    second = dict(reversed(list(first.items())))

    assert manifest_digest(first) == manifest_digest(second)
    assert manifest_digest(first).startswith("sha256:")


@dataclass(frozen=True)
class FakePlugin:
    manifest: Mapping[str, Any]
    case_parameters: Mapping[str, Mapping[str, Any]]
    generator: Any = None
    protocol: Any = None


def test_registry_lists_without_factory_and_lazily_caches_plugin() -> None:
    registry = TaskRegistry()
    calls = 0

    def factory() -> FakePlugin:
        nonlocal calls
        calls += 1
        return FakePlugin(valid_manifest(), {"c01": {"size": 4}})

    registry.register(valid_manifest(), factory)

    assert registry.ids() == ("t1.example_task",)
    assert registry.inspect("t1.example_task")["title"] == "Example task"
    assert calls == 0
    assert registry.get("t1.example_task") is registry.get("t1.example_task")
    assert calls == 1


def test_registry_rejects_duplicates_and_plugin_identity_mismatch() -> None:
    registry = TaskRegistry()
    registry.register(valid_manifest(), lambda: FakePlugin(valid_manifest(), {}))
    with pytest.raises(ManifestError, match="already registered"):
        registry.register(valid_manifest())

    mismatch = copy.deepcopy(valid_manifest())
    mismatch["id"] = "t1.other_task"
    registry = TaskRegistry()
    registry.register(valid_manifest(), lambda: FakePlugin(mismatch, {}))
    with pytest.raises(ManifestError, match="identity mismatch"):
        registry.get("t1.example_task")


def test_default_registry_describes_all_builtin_tasks_without_importing_plugins() -> None:
    registry = default_registry()

    assert registry.ids() == (
        "t1.new_list_graph_homomorphism",
        "t1.new_maxflow_min_cut",
        "t1.new_rooted_group_steiner_tree",
        "t1.new_structured_closest_vector",
        "t1.new_structured_set_cover",
        "t1.new_weighted_partial_maxsat",
        "t2.image_size_lower_bound",
        "t2.new_boolean_hypercube_sumcheck",
        "t2.new_gkr_layered_circuit",
        "t2.new_graph_non_isomorphism",
        "t2.new_hamiltonicity_bind_open",
        "t2.new_shamir_tqbf",
        "t3.dafny_verified_programs",
        "t3.drat_bounded_hardware_safety",
        "t3.machine_checked_mathematics",
    )
    for task_id in (task_id for task_id in registry.ids() if task_id.startswith("t1.")):
        assert registry.inspect(task_id)["protocol"]["mode"] == "one_shot"
        assert registry.inspect(task_id)["resources"]["wall_time_seconds"] == 600
    assert registry.inspect("t2.new_graph_non_isomorphism")["protocol"]["mode"] == "interactive"
    assert registry.inspect("t2.new_graph_non_isomorphism")["protocol"]["public_coin"] is False
    assert registry.inspect("t2.new_graph_non_isomorphism")["resources"]["wall_time_seconds"] == 600
    for task_id in (
        "t2.new_boolean_hypercube_sumcheck",
        "t2.new_gkr_layered_circuit",
        "t2.new_shamir_tqbf",
        "t2.new_hamiltonicity_bind_open",
    ):
        manifest = registry.inspect(task_id)
        assert manifest["protocol"]["mode"] == "interactive"
        assert manifest["protocol"]["public_coin"] is True
        assert manifest["resources"]["wall_time_seconds"] == 600
    image_size_manifest = registry.inspect("t2.image_size_lower_bound")
    assert image_size_manifest["protocol"]["mode"] == "interactive"
    assert image_size_manifest["protocol"]["public_coin"] is True
    assert image_size_manifest["resources"]["wall_time_seconds"] == 600
    for task_id in (
        "t3.machine_checked_mathematics",
        "t3.dafny_verified_programs",
        "t3.drat_bounded_hardware_safety",
    ):
        manifest = registry.inspect(task_id)
        assert manifest["protocol"]["mode"] == "one_shot"
        assert manifest["protocol"]["public_coin"] is False
        assert manifest["resources"]["wall_time_seconds"] == 600
    assert registry.inspect("t3.dafny_verified_programs")["version"] == "0.2.0"
    assert registry.inspect("t3.drat_bounded_hardware_safety")["version"] == "0.8.0"


def test_default_registry_loads_all_builtin_plugins() -> None:
    registry = default_registry()

    new_maxflow = registry.get("t1.new_maxflow_min_cut")
    assert new_maxflow.manifest["id"] == "t1.new_maxflow_min_cut"
    assert tuple(new_maxflow.case_parameters) == (
        "c01",
        "c02",
        "c03",
        "c04",
        "c05",
        "c06",
    )
    new_maxsat = registry.get("t1.new_weighted_partial_maxsat")
    assert new_maxsat.manifest["id"] == "t1.new_weighted_partial_maxsat"
    assert tuple(new_maxsat.case_parameters) == (
        "c01",
        "c02",
        "c03",
        "c04",
        "c05",
        "c06",
    )
    new_group_steiner = registry.get("t1.new_rooted_group_steiner_tree")
    assert new_group_steiner.manifest["id"] == "t1.new_rooted_group_steiner_tree"
    assert tuple(new_group_steiner.case_parameters) == (
        "c01",
        "c02",
        "c03",
        "c04",
        "c05",
        "c06",
    )
    new_closest_vector = registry.get("t1.new_structured_closest_vector")
    assert new_closest_vector.manifest["id"] == "t1.new_structured_closest_vector"
    assert tuple(new_closest_vector.case_parameters) == (
        "c01",
        "c02",
        "c03",
        "c04",
        "c05",
        "c06",
    )
    new_set_cover = registry.get("t1.new_structured_set_cover")
    assert new_set_cover.manifest["id"] == "t1.new_structured_set_cover"
    assert tuple(new_set_cover.case_parameters) == (
        "c01",
        "c02",
        "c03",
        "c04",
        "c05",
        "c06",
    )
    new_gni = registry.get("t2.new_graph_non_isomorphism")
    assert new_gni.manifest["id"] == "t2.new_graph_non_isomorphism"
    assert tuple(new_gni.case_parameters) == ("c01", "c02", "c03", "c04", "c05", "c06", "c07")
    expected_case_counts = {
        "t2.image_size_lower_bound": 6,
        "t2.new_boolean_hypercube_sumcheck": 7,
        "t2.new_gkr_layered_circuit": 7,
        "t2.new_hamiltonicity_bind_open": 7,
        "t2.new_shamir_tqbf": 6,
        "t3.machine_checked_mathematics": 8,
        "t3.dafny_verified_programs": 8,
        "t3.drat_bounded_hardware_safety": 8,
    }
    for task_id, case_count in expected_case_counts.items():
        plugin = registry.get(task_id)
        assert plugin.manifest["id"] == task_id
        assert tuple(plugin.case_parameters) == tuple(
            f"c{index:02d}" for index in range(1, case_count + 1)
        )


def test_cli_exposes_virtual_agents_for_every_new_tier2_task() -> None:
    from aipbench.cli.main import _virtual_agents

    agents = _virtual_agents("t2.image_size_lower_bound")
    assert "virtual-honest" in agents
    assert len(agents) >= 2
    for task_id in (
        "t2.new_graph_non_isomorphism",
        "t2.new_boolean_hypercube_sumcheck",
        "t2.new_gkr_layered_circuit",
        "t2.new_shamir_tqbf",
        "t2.new_hamiltonicity_bind_open",
    ):
        agents = _virtual_agents(task_id)
        assert isinstance(agents, Mapping)


def test_cli_exposes_virtual_agents_for_every_tier3_task() -> None:
    from aipbench.cli.main import _virtual_agents

    for task_id in (
        "t3.machine_checked_mathematics",
        "t3.dafny_verified_programs",
        "t3.drat_bounded_hardware_safety",
    ):
        agents = _virtual_agents(task_id)
        assert "virtual-honest" in agents
        assert len(agents) >= 2


def test_new_tier2_task_yaml_matches_the_registered_manifest() -> None:
    repository_root = Path(__file__).resolve().parents[2]
    registry = default_registry()
    task_directories = {
        "t2.image_size_lower_bound": "image_size_lower_bound",
        "t2.new_graph_non_isomorphism": "new_graph_non_isomorphism",
        "t2.new_boolean_hypercube_sumcheck": "new_boolean_hypercube_sumcheck",
        "t2.new_gkr_layered_circuit": "new_gkr_layered_circuit",
        "t2.new_shamir_tqbf": "new_shamir_tqbf",
        "t2.new_hamiltonicity_bind_open": "new_hamiltonicity_bind_open",
    }

    for task_id, directory in task_directories.items():
        task_yaml = yaml.safe_load(
            (repository_root / "tasks" / "tier2_interactive" / directory / "task.yaml").read_text(
                encoding="utf-8"
            )
        )
        manifest = registry.inspect(task_id)
        for field in (
            "id",
            "version",
            "tier",
            "title",
            "plugin",
            "protocol",
            "randomness",
            "resources",
            "audit",
            "scoring",
            "soundness",
        ):
            assert task_yaml[field] == manifest[field]
        for visibility in ("public_schema", "private_schema"):
            assert manifest["instance"][visibility].endswith(task_yaml["instance"][visibility])


def test_tier3_task_yaml_matches_the_registered_manifest() -> None:
    repository_root = Path(__file__).resolve().parents[2]
    registry = default_registry()
    task_directories = {
        "t3.machine_checked_mathematics": "machine_checked_mathematics",
        "t3.dafny_verified_programs": "dafny_verified_programs",
        "t3.drat_bounded_hardware_safety": "drat_bounded_hardware_safety",
    }
    for task_id, directory in task_directories.items():
        task_yaml = yaml.safe_load(
            (repository_root / "tasks" / "tier3_applied" / directory / "task.yaml").read_text(
                encoding="utf-8"
            )
        )
        manifest = registry.inspect(task_id)
        for field in (
            "id",
            "version",
            "tier",
            "title",
            "plugin",
            "protocol",
            "randomness",
            "resources",
            "audit",
            "scoring",
            "soundness",
        ):
            assert task_yaml[field] == manifest[field]
        for visibility in ("public_schema", "private_schema"):
            assert manifest["instance"][visibility].endswith(task_yaml["instance"][visibility])


def test_published_json_schemas_are_parseable_and_have_required_identity() -> None:
    repository_root = Path(__file__).resolve().parents[2]
    schema_paths = [
        repository_root / "schemas" / "task-manifest.schema.json",
        *sorted((repository_root / "schemas" / "participant-api" / "v1").glob("*.json")),
    ]

    assert {path.name for path in schema_paths} == {
        "task-manifest.schema.json",
        "session.schema.json",
        "event.schema.json",
        "reply.schema.json",
        "result.schema.json",
    }
    for path in schema_paths:
        schema = json.loads(path.read_text(encoding="utf-8"))
        assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        assert schema["$id"].startswith("https://aip-bench.local/schemas/")
