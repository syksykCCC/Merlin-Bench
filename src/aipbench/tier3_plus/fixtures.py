"""Load exact public fixtures; never generate replacement extension instances."""

from __future__ import annotations

import copy
import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from aipbench.core.canonical import canonical_json_bytes
from aipbench.core.models import GeneratedCase
from aipbench.core.protocol import ArthurProtocol, InstanceGenerator, TaskPlugin
from aipbench.registry import TaskRegistry, default_registry
from aipbench.tasks import dafny_verified_programs as dafny
from aipbench.tasks import drat_bounded_hardware_safety as drat
from aipbench.tasks import machine_checked_mathematics as lean

ROOT = Path(__file__).resolve().parents[3] / "Tier 3+"
LONG_TASK_ID = "t3.machine_checked_mathematics_long_horizon"
LONG_TASK_VERSION = "0.2.0"
LONG_MANIFEST = copy.deepcopy(dict(lean.TASK_MANIFEST))
LONG_MANIFEST.update(
    id=LONG_TASK_ID,
    version=LONG_TASK_VERSION,
    title="Machine-Checked Mathematics Long-Horizon Proofs",
    plugin={"entrypoint": "aipbench.tier3_plus.fixtures:create_long_task"},
)


class LongProtocol(lean.MachineCheckedMathematicsProtocol):
    """Retain the native verifier and override only extension identity validation."""

    task_id = LONG_TASK_ID
    task_version = LONG_TASK_VERSION

    @staticmethod
    def _validate_identity(generated_case: GeneratedCase) -> None:
        if (generated_case.task_id, generated_case.task_version) != (
            LONG_TASK_ID,
            LONG_TASK_VERSION,
        ) or generated_case.case_id not in ("c09", "c10"):
            raise ValueError("invalid long-horizon task/version/case identity")


class SelectFixtureGenerator:
    def generate(
        self, *, instance_seed: bytes, case_id: str, case_parameters: Mapping[str, Any]
    ) -> GeneratedCase:
        raise ValueError("Select a unique Tier 3+ fixture with scripts/prepare_tier3_plus.py")


@dataclass
class FixtureTask:
    manifest: Mapping[str, Any]
    case_parameters: Mapping[str, Mapping[str, Any]]
    generator: InstanceGenerator
    protocol: ArthurProtocol


def create_long_task() -> TaskPlugin:
    return FixtureTask(
        manifest=LONG_MANIFEST,
        case_parameters={"c09": {}, "c10": {}},
        generator=SelectFixtureGenerator(),
        protocol=LongProtocol(),
    )


def extended_registry() -> TaskRegistry:
    registry = default_registry()
    registry.register(LONG_MANIFEST, create_long_task)
    return registry


def inventory(root: Path = ROOT) -> list[dict[str, Any]]:
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    cases: list[dict[str, Any]] = manifest["cases"]
    if manifest["schema_version"] != "merlin-bench-tier3-plus/1" or len(cases) != 24:
        raise ValueError("invalid Tier 3+ inventory")
    if len({case["id"] for case in cases}) != 24:
        raise ValueError("duplicate Tier 3+ fixture identity")
    return cases


def _checked_file(root: Path, relative: str, digest: str) -> Path:
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError("fixture path escapes Tier 3+")
    if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
        raise ValueError(f"fixture hash mismatch: {relative}")
    return path


def load_fixture(
    fixture_id: str, root: Path = ROOT
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    matches = [case for case in inventory(root) if case["id"] == fixture_id]
    if len(matches) != 1:
        raise ValueError(f"unknown Tier 3+ fixture: {fixture_id}")
    case = matches[0]
    instance_path = _checked_file(root, case["instance_path"], case["instance_file_sha256"])
    protocol_path = _checked_file(root, case["protocol_path"], case["protocol_file_sha256"])
    public = json.loads(instance_path.read_text(encoding="utf-8"))
    protocol = json.loads(protocol_path.read_text(encoding="utf-8"))
    if (
        hashlib.sha256(canonical_json_bytes(public)).hexdigest()
        != case["canonical_instance_sha256"]
    ):
        raise ValueError("canonical fixture digest mismatch")
    if public["instance_sha256"] != case["embedded_instance_sha256"]:
        raise ValueError("embedded fixture digest mismatch")
    for filename, asset in case["assets"].items():
        path = _checked_file(
            root, (instance_path.parent / filename).relative_to(root).as_posix(), asset["sha256"]
        )
        if path.read_bytes() != public[asset["field"]].encode("utf-8"):
            raise ValueError(f"asset differs from public instance: {filename}")
    {"lean": lean, "dafny": dafny, "drat": drat}[case["domain"]]._validate_public_instance(public)
    return case, public, protocol


class FrozenGenerator:
    def __init__(self, case: dict[str, Any], public: dict[str, Any]) -> None:
        self.case, self.public = case, public

    def generate(
        self, *, instance_seed: bytes, case_id: str, case_parameters: Mapping[str, Any]
    ) -> GeneratedCase:
        if case_id != self.case["case_slot"] or case_parameters != {"fixture_id": self.case["id"]}:
            raise ValueError("fixture identity mismatch")
        return GeneratedCase(
            task_id=self.case["task_id"],
            task_version=self.case["task_version"],
            case_id=case_id,
            public_instance=copy.deepcopy(self.public),
            private_instance={},
            generation_metadata={
                "fixture_id": self.case["id"],
                "candidate_id": self.case["candidate_id"],
                "canonical_instance_sha256": self.case["canonical_instance_sha256"],
                "source": "frozen_public_fixture",
            },
        )


def fixture_plugin(fixture_id: str, root: Path = ROOT) -> TaskPlugin:
    case, public, protocol = load_fixture(fixture_id, root)
    native = extended_registry().get(case["task_id"])
    if (
        native.manifest["version"] != case["task_version"]
        or case["case_slot"] not in native.case_parameters
    ):
        raise ValueError("fixture/runtime identity mismatch")
    generator = FrozenGenerator(case, public)
    generated = generator.generate(
        instance_seed=b"", case_id=case["case_slot"], case_parameters={"fixture_id": fixture_id}
    )
    if native.protocol.public_protocol_description(generated_case=generated) != protocol:
        raise ValueError("fixture/runtime protocol mismatch")
    return FixtureTask(
        manifest=native.manifest,
        protocol=native.protocol,
        generator=generator,
        case_parameters={case["case_slot"]: {"fixture_id": fixture_id}},
    )
