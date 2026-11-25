from __future__ import annotations

import copy
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from aipbench.audit import audit_run
from aipbench.core.models import SessionMode
from aipbench.core.runtime import ArthurRuntime
from aipbench.tier3_plus.fixtures import (
    ROOT,
    extended_registry,
    fixture_plugin,
    inventory,
    load_fixture,
)
from aipbench.transport.inprocess import InProcessParticipantClient


@pytest.mark.parametrize("fixture_id", [case["id"] for case in inventory()])
def test_every_fixture_rejects_wrong_instance_and_replays(tmp_path: Path, fixture_id: str) -> None:
    case, public, protocol = load_fixture(fixture_id)
    plugin = fixture_plugin(fixture_id)
    runtime = ArthurRuntime.create(
        plugin=plugin,
        case_id=case["case_slot"],
        run_dir=tmp_path / "host",
        mode=SessionMode.EVAL,
        instance_seed=b"release-check" * 3,
    )
    assert runtime.get_instance() == public
    assert runtime.protocol_description == protocol
    assert runtime.generated_case.private_instance == {}
    client = InProcessParticipantClient(runtime)
    artifact = client.upload_artifact(content=b"invalid artifact\n", media_type="text/plain")
    response = client.submit_event(
        sequence=0,
        kind=protocol["initial_event_kinds"][0],
        payload={"instance_sha256": "0" * 64},
        artifact_refs=(artifact["artifact_id"],),
    )
    assert response["status"] == "REJECT"
    key = json.loads((runtime.run_dir / "official/signing_public_key.json").read_text())
    report = audit_run(
        runtime.run_dir, registry=extended_registry(), trusted_public_key_base64=key["public_key"]
    )
    assert report["audit_passed"] is True
    assert report["official_result"] == "FAIL"


@pytest.mark.parametrize("fixture_id", ["lean-01", "dafny-01", "drat-01"])
def test_prepared_extension_workspace_is_public_and_portable(
    tmp_path: Path, fixture_id: str
) -> None:
    repo = ROOT.parent
    env = {**os.environ, "PYTHONPATH": str(repo / "src"), "PYTHONDONTWRITEBYTECODE": "1"}
    host, workspace = tmp_path / "host", tmp_path / "workspace"
    completed = subprocess.run(
        [
            sys.executable,
            str(repo / "scripts/prepare_tier3_plus.py"),
            "--fixture",
            fixture_id,
            "--output-dir",
            str(host),
            "--workspace-dir",
            str(workspace),
        ],
        cwd=repo,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
    )
    assert completed.returncode == 0, completed.stderr
    case, public, protocol = load_fixture(fixture_id)
    assert json.loads((workspace / "instance.json").read_text(encoding="utf-8")) == public
    assert json.loads((workspace / "protocol.json").read_text(encoding="utf-8")) == protocol
    harness = json.loads((workspace / "harness.json").read_text(encoding="utf-8"))
    assert harness["case"]["fixture_id"] == fixture_id
    launch = subprocess.run(
        [
            sys.executable,
            str(repo / "scripts/run_harness.py"),
            "--workspace",
            str(workspace),
            "--prompt-mode",
            "environment",
            "--",
            sys.executable,
            "-c",
            "import os; print(os.environ['AIP_FIXTURE_ID'])",
        ],
        cwd=repo,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
    )
    assert launch.returncode == 0, launch.stderr
    assert launch.stdout.strip() == fixture_id
    assert "aipbench.tier3_plus.cli" in (host / "RUN_INSTRUCTIONS.md").read_text(encoding="utf-8")
    for filename, asset in case["assets"].items():
        assert (workspace / filename).read_bytes() == public[asset["field"]].encode()
    assert not list(workspace.rglob("*private*"))
    assert not (workspace / "src").exists()


def test_fixture_asset_tampering_and_unknown_ids_fail(tmp_path: Path) -> None:
    clone = tmp_path / "fixtures"
    shutil.copytree(ROOT, clone)
    case = inventory(clone)[0]
    asset = clone / Path(case["instance_path"]).parent / "Challenge.lean"
    asset.write_bytes(asset.read_bytes() + b"\n-- modified\n")
    with pytest.raises(ValueError, match="hash mismatch"):
        load_fixture(case["id"], clone)
    with pytest.raises(ValueError, match="unknown Tier 3"):
        load_fixture("lean-99")


def test_frozen_instance_is_seed_independent_and_identity_checked() -> None:
    case, public, _ = load_fixture("lean-01")
    plugin = fixture_plugin("lean-01")
    parameters = plugin.case_parameters[case["case_slot"]]
    first = plugin.generator.generate(
        instance_seed=b"a" * 32, case_id=case["case_slot"], case_parameters=parameters
    )
    second = plugin.generator.generate(
        instance_seed=b"b" * 32, case_id=case["case_slot"], case_parameters=parameters
    )
    assert first.public_instance == second.public_instance == public
    changed = copy.deepcopy(first)
    object.__setattr__(changed, "task_version", "9.9.9")
    with pytest.raises(ValueError, match="identity"):
        plugin.protocol.public_protocol_description(generated_case=changed)
    with pytest.raises(ValueError, match="identity"):
        plugin.generator.generate(
            instance_seed=b"a" * 32, case_id="c10", case_parameters=parameters
        )
