from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from aipbench.core.models import SessionMode
from aipbench.core.runtime import ArthurRuntime
from aipbench.registry import default_registry

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "prepare_evaluation.py"
REGISTRY = default_registry()
REPRESENTATIVE_CASES = {
    "t1.new_maxflow_min_cut": "c01",
    "t1.new_weighted_partial_maxsat": "c01",
    "t1.new_list_graph_homomorphism": "c01",
    "t1.new_rooted_group_steiner_tree": "c01",
    "t1.new_structured_closest_vector": "c01",
    "t1.new_structured_set_cover": "c01",
    "t2.new_graph_non_isomorphism": "c01",
    "t2.new_boolean_hypercube_sumcheck": "c01",
    "t2.new_gkr_layered_circuit": "c01",
    "t2.new_shamir_tqbf": "c01",
    "t2.new_hamiltonicity_bind_open": "c01",
    "t2.image_size_lower_bound": "c01",
    "t3.machine_checked_mathematics": "c01",
    "t3.dafny_verified_programs": "c01",
    "t3.drat_bounded_hardware_safety": "c01",
}
TASK_CASES = tuple((task_id, REPRESENTATIVE_CASES[task_id]) for task_id in REGISTRY.ids())
UNIFIED_SPECIFICATION_TASKS = {
    "t1.new_maxflow_min_cut",
    "t1.new_weighted_partial_maxsat",
    "t1.new_list_graph_homomorphism",
    "t1.new_rooted_group_steiner_tree",
    "t1.new_structured_closest_vector",
    "t1.new_structured_set_cover",
    "t2.new_graph_non_isomorphism",
    "t2.new_boolean_hypercube_sumcheck",
    "t2.new_gkr_layered_circuit",
    "t2.new_shamir_tqbf",
    "t2.new_hamiltonicity_bind_open",
    "t2.image_size_lower_bound",
    "t3.machine_checked_mathematics",
    "t3.dafny_verified_programs",
    "t3.drat_bounded_hardware_safety",
}


def _collect_schema_refs(value: object) -> set[str]:
    references: set[str] = set()
    if isinstance(value, dict):
        for key, nested in value.items():
            if key == "schema_ref":
                assert isinstance(nested, str)
                references.add(nested)
            else:
                references.update(_collect_schema_refs(nested))
    elif isinstance(value, list):
        for nested in value:
            references.update(_collect_schema_refs(nested))
    return references


@pytest.mark.parametrize(
    ("task_id", "case_id"),
    TASK_CASES,
)
def test_prepare_evaluation_builds_loadable_run_and_agent_workspace(
    tmp_path: Path,
    task_id: str,
    case_id: str,
) -> None:
    run_dir = tmp_path / task_id
    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--task",
            task_id,
            "--case",
            case_id,
            "--seed",
            "ab" * 32,
            "--port",
            "18765",
            "--output-dir",
            str(run_dir),
        ],
        cwd=ROOT,
        capture_output=True,
        check=False,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    assert f"EVALUATION_DIRECTORY: {run_dir.resolve()}" in completed.stdout

    workspace = run_dir / "workspace"
    assert workspace.parent == run_dir
    assert workspace not in run_dir.parents
    assert not (run_dir / "agent").exists()
    assert not (run_dir / "public" / "prompt.md").exists()
    plugin = default_registry().get(task_id)
    protocol = json.loads((workspace / "protocol.json").read_text(encoding="utf-8"))
    public_schema = plugin.manifest["instance"]["public_schema"]
    public_references = {
        public_schema,
        *_collect_schema_refs(protocol),
    }
    expected_workspace_files = {
        ".aipbench-connection.json",
        "AGENT_PROMPT.md",
        "TASK_SPECIFICATION.md",
        "harness.json",
        "instance.json",
        "agent_client.py",
        "protocol.json",
        *(Path(reference).as_posix() for reference in public_references),
    }
    actual_workspace_files = {
        path.relative_to(workspace).as_posix() for path in workspace.rglob("*") if path.is_file()
    }
    assert not any(path.is_symlink() for path in workspace.rglob("*"))
    assert actual_workspace_files == expected_workspace_files
    for filename in ("instance.json", "protocol.json"):
        assert (workspace / filename).read_bytes() == (run_dir / "public" / filename).read_bytes()
    specification_path = (ROOT / public_schema).parent.parent / "TASK_SPECIFICATION.md"
    assert (workspace / "TASK_SPECIFICATION.md").read_bytes() == specification_path.read_bytes()
    specification_text = specification_path.read_text(encoding="utf-8")
    assert task_id in specification_text
    assert plugin.manifest["version"] in specification_text
    if task_id in UNIFIED_SPECIFICATION_TASKS:
        if task_id == "t2.new_graph_non_isomorphism":
            assert set(plugin.case_parameters) == {
                "c01",
                "c02",
                "c03",
                "c04",
                "c05",
                "c06",
                "c07",
            }
            assert all(
                registered_case_id not in specification_text
                for registered_case_id in plugin.case_parameters
            )
        if task_id == "t2.new_graph_non_isomorphism":
            pass
        elif task_id in {
            "t1.new_maxflow_min_cut",
            "t1.new_list_graph_homomorphism",
            "t1.new_rooted_group_steiner_tree",
            "t1.new_weighted_partial_maxsat",
            "t1.new_structured_closest_vector",
            "t1.new_structured_set_cover",
        }:
            assert all(
                registered_case_id not in specification_text
                for registered_case_id in plugin.case_parameters
            )
        elif task_id in {
            "t2.new_boolean_hypercube_sumcheck",
            "t2.new_gkr_layered_circuit",
            "t2.new_hamiltonicity_bind_open",
        }:
            assert set(plugin.case_parameters) == {
                "c01",
                "c02",
                "c03",
                "c04",
                "c05",
                "c06",
                "c07",
            }
        elif task_id.startswith("t3."):
            expected_case_counts = {
                "t3.machine_checked_mathematics": 8,
                "t3.dafny_verified_programs": 8,
                "t3.drat_bounded_hardware_safety": 8,
            }
            assert set(plugin.case_parameters) == {
                f"c{index:02d}" for index in range(1, expected_case_counts[task_id] + 1)
            }
        else:
            assert set(plugin.case_parameters) == {"c01", "c02", "c03", "c04", "c05", "c06"}
        specification_files = [
            path.relative_to(workspace).as_posix() for path in workspace.rglob("*SPECIFICATION*.md")
        ]
        assert specification_files == ["TASK_SPECIFICATION.md"]
    else:
        assert case_id in specification_text
    for reference in public_references:
        assert (workspace / reference).read_bytes() == (ROOT / reference).read_bytes()
    private_schema = plugin.manifest["instance"]["private_schema"]
    assert Path(private_schema).as_posix() not in actual_workspace_files
    assert not any(
        "private" in path.relative_to(workspace).parts
        for path in workspace.rglob("*")
        if path.is_file()
    )

    private_runtime = json.loads((run_dir / "private" / "runtime.json").read_text(encoding="utf-8"))
    connection = json.loads((workspace / ".aipbench-connection.json").read_text(encoding="utf-8"))
    assert connection == {
        "api_version": "aip/1",
        "endpoint": "http://127.0.0.1:18765",
        "session_token": private_runtime["session_token"],
    }
    harness = json.loads((workspace / "harness.json").read_text(encoding="utf-8"))
    assert harness == {
        "schema_version": "aip-harness/1",
        "api_version": "aip/1",
        "task": {
            "id": task_id,
            "version": str(plugin.manifest["version"]),
            "title": str(plugin.manifest["title"]),
        },
        "case": {"id": case_id},
        "limits": {"wall_time_seconds": int(plugin.manifest["resources"]["wall_time_seconds"])},
        "files": {
            "prompt": "AGENT_PROMPT.md",
            "task_specification": "TASK_SPECIFICATION.md",
            "instance": "instance.json",
            "protocol": "protocol.json",
            "client": "agent_client.py",
            "connection": ".aipbench-connection.json",
        },
    }
    assert private_runtime["session_token"] not in (workspace / "harness.json").read_text(
        encoding="utf-8"
    )
    workspace_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in workspace.rglob("*")
        if path.is_file() and path.suffix != ".pyc"
    )
    assert private_runtime["coin_seed_hex"] not in workspace_text
    assert private_runtime["signing_private_key"] not in workspace_text

    instructions = (run_dir / "RUN_INSTRUCTIONS.md").read_text(encoding="utf-8")
    assert "arthur" in instructions and "serve" in instructions
    assert "audit" in instructions and "result" in instructions and "show" in instructions
    assert str(workspace.resolve()) in instructions
    assert "AGENT_PROMPT.md" in instructions
    assert "harness.json" in instructions and "run_harness.py" in instructions
    budget_seconds = int(plugin.manifest["resources"]["wall_time_seconds"])
    budget_minutes = budget_seconds // 60
    assert f"{budget_seconds} seconds ({budget_minutes} minutes)" in instructions
    assert "arthur serve" in instructions and "countdown" in instructions
    agent_prompt = (workspace / "AGENT_PROMPT.md").read_text(encoding="utf-8")
    assert "TASK_SPECIFICATION.md" in agent_prompt
    assert agent_prompt.index("TASK_SPECIFICATION.md") < agent_prompt.index("instance.json")
    assert plugin.manifest["title"] in agent_prompt
    assert f"{budget_seconds} seconds ({budget_minutes} minutes)" in agent_prompt
    assert "arthur serve" in agent_prompt and "countdown" in agent_prompt
    reserve_seconds = min(
        300,
        max(1, budget_seconds // 6),
        max(0, budget_seconds - 1),
    )
    solve_seconds = budget_seconds - reserve_seconds
    assert f"about `{solve_seconds}` seconds" in agent_prompt
    assert "leaving at least" in agent_prompt and str(reserve_seconds) in agent_prompt
    assert "controls only the wait time for a single HTTP request" in agent_prompt
    assert "terminal response must be received before the deadline" in agent_prompt
    assert "TIMEOUT / BUDGET_EXCEEDED" in agent_prompt
    assert "python agent_client.py info" in agent_prompt
    assert "python agent_client.py event" in agent_prompt
    assert "path outside this workspace" in agent_prompt
    assert "Merlin-Bench" not in agent_prompt
    for secret_value in (
        private_runtime["session_token"],
        private_runtime["coin_seed_hex"],
        private_runtime["signing_private_key"],
    ):
        assert secret_value not in completed.stdout
        assert secret_value not in instructions
        assert secret_value not in agent_prompt
    assert f"HARNESS_MANIFEST: {workspace / 'harness.json'}" in completed.stdout

    trusted_key = run_dir.with_name(f"{run_dir.name}.trusted-key.json")
    assert (
        trusted_key.read_bytes() == (run_dir / "official" / "signing_public_key.json").read_bytes()
    )
    runtime = ArthurRuntime.load_prepared(
        plugin=default_registry().get(task_id),
        run_dir=run_dir,
    )
    assert runtime.mode is SessionMode.EVAL
    assert runtime.wall_time_seconds == int(plugin.manifest["resources"]["wall_time_seconds"])
    assert runtime.generated_case.case_id == case_id
    assert runtime.expected_sequence == 0


def test_prepare_evaluation_refuses_nonempty_output_directory(tmp_path: Path) -> None:
    run_dir = tmp_path / "existing"
    run_dir.mkdir()
    marker = run_dir / "keep.txt"
    marker.write_text("do not replace", encoding="utf-8")
    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--task",
            "t1.new_maxflow_min_cut",
            "--case",
            "c01",
            "--output-dir",
            str(run_dir),
        ],
        cwd=ROOT,
        capture_output=True,
        check=False,
        text=True,
    )
    assert completed.returncode == 2
    assert "must be new or empty" in completed.stderr
    assert marker.read_text(encoding="utf-8") == "do not replace"


@pytest.mark.parametrize(
    ("workspace_name", "error_text"),
    (
        ("evaluation/private/workspace", "must stay outside"),
        (".", "must not contain"),
    ),
)
def test_prepare_evaluation_refuses_protected_or_parent_workspace(
    tmp_path: Path,
    workspace_name: str,
    error_text: str,
) -> None:
    run_dir = tmp_path / "evaluation"
    workspace = tmp_path / workspace_name
    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--task",
            "t1.new_maxflow_min_cut",
            "--case",
            "c01",
            "--output-dir",
            str(run_dir),
            "--workspace-dir",
            str(workspace),
        ],
        cwd=ROOT,
        capture_output=True,
        check=False,
        text=True,
    )
    assert completed.returncode == 2
    assert error_text in completed.stderr


def test_prepare_evaluation_supports_explicit_disjoint_workspace(tmp_path: Path) -> None:
    run_dir = tmp_path / "evaluation"
    workspace = tmp_path / "agent-root"
    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--task",
            "t1.new_maxflow_min_cut",
            "--case",
            "c01",
            "--seed",
            "cd" * 32,
            "--output-dir",
            str(run_dir),
            "--workspace-dir",
            str(workspace),
        ],
        cwd=ROOT,
        capture_output=True,
        check=False,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    assert f"AGENT_WORKSPACE: {workspace.resolve()}" in completed.stdout
    assert (workspace / "AGENT_PROMPT.md").is_file()
    assert (workspace / "harness.json").is_file()
    assert (run_dir / "private" / "runtime.json").is_file()
