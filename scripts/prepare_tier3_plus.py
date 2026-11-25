#!/usr/bin/env python3
"""Prepare one fixed Tier 3+ instance through the standard evaluation interface."""

from __future__ import annotations

import argparse
import json
import secrets
from pathlib import Path

from prepare_evaluation import _parse_port, prepare_evaluation

from aipbench.tier3_plus.fixtures import ROOT, fixture_plugin, inventory, load_fixture


def prepare(
    fixture_id: str,
    *,
    port: int = 8765,
    output_dir: Path | None = None,
    workspace_dir: Path | None = None,
) -> tuple[Path, Path, Path]:
    case, public, _ = load_fixture(fixture_id)
    plugin = fixture_plugin(fixture_id)
    specification = ROOT / "lean" / "TASK_SPECIFICATION.md" if case["domain"] == "lean" else None
    run, workspace, key = prepare_evaluation(
        task_id=case["task_id"],
        case_id=case["case_slot"],
        seed=secrets.token_bytes(32),
        port=port,
        output_dir=output_dir,
        workspace_dir=workspace_dir,
        plugin=plugin,
        cli_module="aipbench.tier3_plus.cli",
        specification_path=specification,
    )
    for filename, asset in case["assets"].items():
        (workspace / filename).write_bytes(public[asset["field"]].encode("utf-8"))
    harness_path = workspace / "harness.json"
    harness = json.loads(harness_path.read_text(encoding="utf-8"))
    harness["case"]["fixture_id"] = fixture_id
    harness_path.write_text(json.dumps(harness, indent=2) + "\n", encoding="utf-8", newline="\n")
    with (workspace / "AGENT_PROMPT.md").open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(f"\nTier 3+ fixture: `{fixture_id}`. Title: {case['title']}.\n")
    return run, workspace, key


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--list", action="store_true")
    selection.add_argument("--fixture", choices=[case["id"] for case in inventory()])
    parser.add_argument("--port", type=_parse_port, default=8765)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--workspace-dir", type=Path)
    args = parser.parse_args()
    if args.list:
        for case in inventory():
            print(f"{case['id']}\t{case['title']}")
        return 0
    run, workspace, key = prepare(
        args.fixture, port=args.port, output_dir=args.output_dir, workspace_dir=args.workspace_dir
    )
    print(f"Host run: {run}\nParticipant workspace: {workspace}\nTrusted key: {key}")
    print(f"Next: follow {run / 'RUN_INSTRUCTIONS.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
