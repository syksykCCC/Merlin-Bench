#!/usr/bin/env python3
"""Run any external model harness against one prepared participant workspace.

The adapter is intentionally provider-neutral. It launches an argv vector without
a shell, publishes the Merlin-Bench contract through environment variables, and
copies only explicitly selected host environment variables by default.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

HARNESS_FILENAME = "harness.json"
HARNESS_SCHEMA_VERSION = "aip-harness/1"
PARTICIPANT_API_VERSION = "aip/1"
ENVIRONMENT_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
BASE_ENVIRONMENT_NAMES = (
    "COMSPEC",
    "PATH",
    "PATHEXT",
    "SystemRoot",
    "SYSTEMROOT",
    "TEMP",
    "TMP",
    "WINDIR",
)


class HarnessError(RuntimeError):
    """A safe, user-facing harness configuration error."""


def _load_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HarnessError(f"cannot read JSON object {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise HarnessError(f"{path} must contain one JSON object")
    return value


def _required_string(value: Mapping[str, Any], key: str, *, source: Path) -> str:
    result = value.get(key)
    if not isinstance(result, str) or not result.strip():
        raise HarnessError(f"{source} has no nonempty string {key!r}")
    return result.strip()


def _required_object(value: Mapping[str, Any], key: str, *, source: Path) -> dict[str, Any]:
    result = value.get(key)
    if not isinstance(result, dict):
        raise HarnessError(f"{source} has no object {key!r}")
    return result


def _workspace_file(workspace: Path, relative_value: Any, *, source: Path) -> Path:
    if not isinstance(relative_value, str) or not relative_value.strip():
        raise HarnessError(f"{source} contains an invalid workspace file reference")
    relative = Path(relative_value)
    if relative.is_absolute() or relative.drive or ".." in relative.parts:
        raise HarnessError(f"workspace file reference must be relative: {relative_value}")
    path = (workspace / relative).resolve()
    if workspace not in path.parents or not path.is_file():
        raise HarnessError(f"workspace file is missing or outside the workspace: {relative_value}")
    return path


def _load_contract(workspace_value: Path) -> tuple[dict[str, Any], dict[str, Path]]:
    workspace = workspace_value.expanduser().resolve()
    if not workspace.is_dir():
        raise HarnessError(f"workspace is not a directory: {workspace}")
    manifest_path = workspace / HARNESS_FILENAME
    manifest = _load_object(manifest_path)
    if manifest.get("schema_version") != HARNESS_SCHEMA_VERSION:
        raise HarnessError(
            f"unsupported harness schema version in {manifest_path}; "
            f"expected {HARNESS_SCHEMA_VERSION!r}"
        )
    if manifest.get("api_version") != PARTICIPANT_API_VERSION:
        raise HarnessError(
            f"unsupported Participant API version in {manifest_path}; "
            f"expected {PARTICIPANT_API_VERSION!r}"
        )
    files = _required_object(manifest, "files", source=manifest_path)
    resolved = {
        key: _workspace_file(workspace, files.get(key), source=manifest_path)
        for key in (
            "prompt",
            "task_specification",
            "instance",
            "protocol",
            "client",
            "connection",
        )
    }
    return manifest, resolved


def _positive_number(value: Any, *, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        raise HarnessError(f"{label} must be a positive number")
    return float(value)


def _child_environment(
    *,
    manifest_path: Path,
    manifest: Mapping[str, Any],
    files: Mapping[str, Path],
    inherited_names: Sequence[str],
    inherit_all: bool,
) -> dict[str, str]:
    if inherit_all:
        environment = dict(os.environ)
    else:
        environment = {
            name: os.environ[name] for name in BASE_ENVIRONMENT_NAMES if name in os.environ
        }
        for name in inherited_names:
            if ENVIRONMENT_NAME.fullmatch(name) is None:
                raise HarnessError(f"invalid environment variable name: {name!r}")
            if name not in os.environ:
                raise HarnessError(f"requested environment variable is not set: {name}")
            environment[name] = os.environ[name]

    task = _required_object(manifest, "task", source=manifest_path)
    case = _required_object(manifest, "case", source=manifest_path)
    limits = _required_object(manifest, "limits", source=manifest_path)
    connection = _load_object(files["connection"])
    if connection.get("api_version") != PARTICIPANT_API_VERSION:
        raise HarnessError(
            f"unsupported Participant API version in {files['connection']}; "
            f"expected {PARTICIPANT_API_VERSION!r}"
        )
    endpoint = _required_string(connection, "endpoint", source=files["connection"])
    session_token = _required_string(connection, "session_token", source=files["connection"])

    environment.update(
        {
            "AIP_HARNESS_SCHEMA_VERSION": HARNESS_SCHEMA_VERSION,
            "AIP_HARNESS_MANIFEST": str(manifest_path),
            "AIP_WORKSPACE": str(manifest_path.parent),
            "AIP_PROMPT_FILE": str(files["prompt"]),
            "AIP_TASK_SPECIFICATION_FILE": str(files["task_specification"]),
            "AIP_INSTANCE_FILE": str(files["instance"]),
            "AIP_PROTOCOL_FILE": str(files["protocol"]),
            "AIP_CLIENT_FILE": str(files["client"]),
            "AIP_CONNECTION_FILE": str(files["connection"]),
            "AIP_ENDPOINT": endpoint,
            "AIP_SESSION_TOKEN": session_token,
            "AIP_TASK_ID": _required_string(task, "id", source=manifest_path),
            "AIP_TASK_VERSION": _required_string(task, "version", source=manifest_path),
            "AIP_CASE_ID": _required_string(case, "id", source=manifest_path),
            "AIP_WALL_TIME_SECONDS": str(
                int(
                    _positive_number(
                        limits.get("wall_time_seconds"),
                        label="harness wall_time_seconds",
                    )
                )
            ),
            "PYTHONIOENCODING": "utf-8",
        }
    )
    if "fixture_id" in case:
        environment["AIP_FIXTURE_ID"] = _required_string(case, "fixture_id", source=manifest_path)
    return environment


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Launch a provider-neutral external model harness inside a prepared Merlin-Bench "
            "participant workspace. Add the command after `--`."
        )
    )
    parser.add_argument(
        "--workspace",
        type=Path,
        default=Path.cwd(),
        help="prepared participant workspace (default: current directory)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        help="harness process timeout; defaults to the task wall-time limit",
    )
    parser.add_argument(
        "--prompt-mode",
        choices=("environment", "stdin", "argument", "path-argument"),
        default="environment",
        help=(
            "publish only AIP_PROMPT_FILE (default), send prompt text on stdin, append prompt "
            "text as the final argument, or append the prompt path"
        ),
    )
    environment_group = parser.add_mutually_exclusive_group()
    environment_group.add_argument(
        "--inherit-env",
        action="append",
        default=[],
        metavar="NAME",
        help=(
            "copy one named host variable into the harness; repeat for provider API keys or "
            "model configuration. Values are never printed or written by this adapter"
        ),
    )
    environment_group.add_argument(
        "--inherit-all-env",
        action="store_true",
        help="explicit compatibility mode for harnesses that require the complete host environment",
    )
    parser.add_argument(
        "command", nargs=argparse.REMAINDER, help="executable and arguments after --"
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    command = list(args.command)
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        parser.error("a harness command is required after --")

    try:
        workspace = args.workspace.expanduser().resolve()
        manifest, files = _load_contract(workspace)
        manifest_path = workspace / HARNESS_FILENAME
        limits = _required_object(manifest, "limits", source=manifest_path)
        timeout = (
            _positive_number(args.timeout, label="--timeout")
            if args.timeout is not None
            else _positive_number(
                limits.get("wall_time_seconds"),
                label="harness wall_time_seconds",
            )
        )
        environment = _child_environment(
            manifest_path=manifest_path,
            manifest=manifest,
            files=files,
            inherited_names=args.inherit_env,
            inherit_all=args.inherit_all_env,
        )
        prompt_text: str | None = None
        if args.prompt_mode == "stdin":
            prompt_text = files["prompt"].read_text(encoding="utf-8")
        elif args.prompt_mode == "argument":
            command.append(files["prompt"].read_text(encoding="utf-8"))
        elif args.prompt_mode == "path-argument":
            command.append(str(files["prompt"]))

        completed = subprocess.run(
            command,
            cwd=workspace,
            env=environment,
            input=prompt_text,
            text=True,
            encoding="utf-8",
            timeout=timeout,
            check=False,
        )
        return completed.returncode
    except subprocess.TimeoutExpired:
        print("error: harness process exceeded its configured timeout", file=sys.stderr)
        return 124
    except (HarnessError, OSError, UnicodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
