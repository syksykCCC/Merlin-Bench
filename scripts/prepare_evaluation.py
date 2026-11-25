#!/usr/bin/env python3
"""Prepare one manual Agent evaluation without starting Arthur."""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import re
import secrets
import shlex
import shutil
import sys
import tempfile
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path

from aipbench.core.errors import AIPBenchError
from aipbench.core.models import SessionMode
from aipbench.core.protocol import TaskPlugin
from aipbench.core.runtime import ArthurRuntime
from aipbench.registry import default_registry

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
CONNECTION_FILENAME = ".aipbench-connection.json"
HARNESS_MANIFEST_FILENAME = "harness.json"
HARNESS_SCHEMA_VERSION = "aip-harness/1"


def _parse_seed(value: str) -> bytes:
    if value == "random":
        return secrets.token_bytes(32)
    normalized = value.removeprefix("0x")
    try:
        seed = bytes.fromhex(normalized)
    except ValueError as exc:
        raise ValueError("--seed must be 'random' or an even-length hex string") from exc
    if len(seed) < 16:
        raise ValueError("--seed must contain at least 128 bits")
    return seed


def _parse_port(value: str) -> int:
    try:
        port = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("port must be an integer") from exc
    if not 1 <= port <= 65535:
        raise argparse.ArgumentTypeError("port must be between 1 and 65535")
    return port


def _safe_component(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "-", value).strip("-") or "evaluation"


def _public_schema_reference(manifest: Mapping[str, object]) -> str:
    instance = manifest.get("instance")
    if not isinstance(instance, Mapping):
        raise ValueError("task manifest has no instance object")
    reference = instance.get("public_schema")
    if not isinstance(reference, str) or not reference.strip():
        raise ValueError("task manifest has no public instance schema reference")
    return reference


def _repository_file(reference: str) -> tuple[Path, Path]:
    relative = Path(reference)
    if relative.is_absolute() or relative.drive or ".." in relative.parts:
        raise ValueError(f"public file reference must stay inside the repository: {reference}")
    source = (REPOSITORY_ROOT / relative).resolve()
    try:
        normalized_relative = source.relative_to(REPOSITORY_ROOT.resolve())
    except ValueError as exc:
        raise ValueError(f"public file reference escapes the repository: {reference}") from exc
    if not source.is_file():
        raise ValueError(f"required public file does not exist: {source}")
    return source, normalized_relative


def _task_specification_path(manifest: Mapping[str, object]) -> Path:
    public_schema, _ = _repository_file(_public_schema_reference(manifest))
    specification = (public_schema.parent.parent / "TASK_SPECIFICATION.md").resolve()
    try:
        specification.relative_to(REPOSITORY_ROOT.resolve())
    except ValueError as exc:
        raise ValueError(f"task specification escapes the repository: {specification}") from exc
    if not specification.is_file():
        raise ValueError(f"task has no TASK_SPECIFICATION.md: {specification}")
    return specification


def _schema_references(value: object) -> set[str]:
    references: set[str] = set()
    if isinstance(value, Mapping):
        for key, nested in value.items():
            if key == "schema_ref":
                if not isinstance(nested, str) or not nested.strip():
                    raise ValueError("protocol schema_ref must be a nonempty string")
                references.add(nested)
            else:
                references.update(_schema_references(nested))
    elif isinstance(value, (list, tuple)):
        for nested in value:
            references.update(_schema_references(nested))
    return references


def _copy_repository_file(*, reference: str, workspace: Path) -> Path:
    source, relative = _repository_file(reference)
    destination = workspace / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    return destination


def _create_empty_output_dir(*, task_id: str, case_id: str, output_dir: Path | None) -> Path:
    if output_dir is not None:
        resolved = output_dir.expanduser().resolve()
        resolved.mkdir(parents=True, exist_ok=True)
        if any(resolved.iterdir()):
            raise ValueError(f"--output-dir must be new or empty: {resolved}")
        return resolved

    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    prefix = f"{timestamp}-{_safe_component(task_id)}-{_safe_component(case_id)}-"
    return Path(tempfile.mkdtemp(prefix=prefix)).resolve()


def _resolve_agent_workspace(*, run_dir: Path, workspace_dir: Path | None) -> Path:
    workspace = (
        workspace_dir.expanduser().resolve() if workspace_dir is not None else run_dir / "workspace"
    )
    if workspace == run_dir or workspace in run_dir.parents:
        raise ValueError("Agent workspace must not contain the evaluation directory")
    protected_roots = tuple(run_dir / name for name in ("public", "official", "private"))
    if any(workspace == root or root in workspace.parents for root in protected_roots):
        raise ValueError("Agent workspace must stay outside public/, official/, and private/")
    if workspace.exists() and (not workspace.is_dir() or any(workspace.iterdir())):
        raise ValueError(f"Agent workspace must be new or empty: {workspace}")
    return workspace


def _write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _write_text(path: Path, value: str) -> None:
    path.write_text(value, encoding="utf-8", newline="\n")


def _powershell_command(arguments: Sequence[str]) -> str:
    quoted = ["'" + argument.replace("'", "''") + "'" for argument in arguments]
    return "& " + " ".join(quoted)


def _command_block(command_lines: Sequence[Sequence[str]]) -> str:
    if os.name == "nt":
        rendered = "\n".join(_powershell_command(arguments) for arguments in command_lines)
        return f"```powershell\n{rendered}\n```"
    rendered = "\n".join(shlex.join(arguments) for arguments in command_lines)
    return f"```bash\n{rendered}\n```"


def _commands(
    *, run_dir: Path, trusted_key: Path, port: int, cli_module: str = "aipbench.cli.main"
) -> dict[str, list[str]]:
    python = str(Path(sys.executable).resolve())
    common = [python, "-m", cli_module]
    return {
        "serve": [
            *common,
            "arthur",
            "serve",
            "--run-dir",
            str(run_dir),
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        "audit": [
            *common,
            "audit",
            str(run_dir),
            "--trusted-public-key",
            str(trusted_key),
        ],
        "result": [*common, "result", "show", str(run_dir)],
    }


def _wall_time_label(wall_time_seconds: int) -> str:
    if wall_time_seconds <= 0:
        raise ValueError("wall_time_seconds must be positive")
    if wall_time_seconds % 60 == 0:
        return f"{wall_time_seconds} seconds ({wall_time_seconds // 60} minutes)"
    return f"{wall_time_seconds} seconds"


def _agent_prompt(
    *,
    task_id: str,
    task_title: str,
    case_id: str,
    wall_time_seconds: int,
) -> str:
    wall_time_label = _wall_time_label(wall_time_seconds)
    submission_reserve_seconds = min(
        300,
        max(1, wall_time_seconds // 6),
        max(0, wall_time_seconds - 1),
    )
    primary_work_seconds = wall_time_seconds - submission_reserve_seconds
    return f"""# Begin the Current Task

You must solve a specific instance and submit the answer to the local verifier, Arthur.

- Task: `{task_title}` (`{task_id}`)
- Test point: `{case_id}`
- Evaluation mode: one-shot session; it cannot be reset or retried
- Total wall-clock budget: `{wall_time_label}`

## Time Budget (Mandatory)

The countdown begins when the host starts `arthur serve` and loads this runtime, not when you
start a solver or make your first submission. The countdown will normally already have begun when
you see these instructions; reading the task, writing code, running solvers, checking answers, and
submitting all count against the same budget.

- Immediately run `python agent_client.py info` to confirm the connection and public total budget,
  and record elapsed time yourself from now on.
- Every solver and subprocess must have a finite timeout; do not let one attempt consume the whole budget.
- If there is no additional startup delay, the main solving phase should finish no later than about `{primary_work_seconds}` seconds, leaving at least
  `{submission_reserve_seconds}` seconds for independent checks, payload generation, and submission; finish proportionally earlier if time has elapsed.
- `agent_client.py --timeout` controls only the wait time for a single HTTP request; it cannot extend
  the global wall-clock budget above.
- Arthur's terminal response must be received before the deadline. Merely starting a submission before
  the deadline, or having a request reach the server, does not count as completion; Arthur's verification
  time also counts against the budget.
- Near the deadline, proactively terminate unfinished attempts and switch to validating and submitting
  an existing candidate; once the budget is exhausted, Arthur returns `TIMEOUT / BUDGET_EXCEEDED`.

## What You Need To Do

1. Read `TASK_SPECIFICATION.md` in full. It defines the problem, mathematical notation, interaction
   order, message fields, and acceptance conditions.
2. Read `instance.json` for this run's actual input and `protocol.json` to confirm the message types
   and ordering allowed for this run. Examples in `TASK_SPECIFICATION.md` explain the format only; they
   are not the answer to this instance.
3. Run `python agent_client.py info` to confirm that Arthur is reachable and that the initial
   `next_sequence` is `0`.
4. Write the solver, prover, payload, or helper scripts needed in the current directory, then compute
   the answer for the actual instance.
5. Submit every required message according to the specification:

   ```text
   python agent_client.py event --sequence N --kind KIND --payload-file payload.json
   ```

   Use `python agent_client.py event --help` to view all parameters. The `sequence` of each message
   must start at `0` and increase strictly. In a multi-round protocol, calculate the next message only
   from the challenge Arthur returned after the previous submission.
6. Continue until Arthur returns a terminal status. `ACCEPT` means the protocol passed; any other
   terminal status means this one-shot evaluation has ended. The final score is confirmed by the host's
   independent post-terminal audit.

## Files in the Current Directory

- `TASK_SPECIFICATION.md`: the authoritative description of the task and submission protocol;
- `instance.json`: the public input for this run;
- `protocol.json`: interaction messages accepted by Arthur;
- `agent_client.py`: a general client for querying Arthur and submitting messages; it does not contain
  the answer to the task;
- `{HARNESS_MANIFEST_FILENAME}`: provider-neutral metadata for an external model harness;
- `schemas/` or schemas under the task path: use these to check JSON fields when needed;
- `{CONNECTION_FILENAME}`: a one-shot connection credential automatically read by the client. Do not
  print, repost, or include it in a report.

## Boundaries

The current workspace contains every file you are allowed to use. Do not read, search, or modify any
path outside this workspace, and do not look for reference solvers, generator source code, or the
evaluator's `private/` or `official/` files. Your only objective is to solve using the public inputs above
and complete the interaction through `agent_client.py`.

Start solving now; do not provide only a plan.
"""


def _run_instructions(
    *,
    task_id: str,
    case_id: str,
    run_dir: Path,
    workspace: Path,
    trusted_key: Path,
    wall_time_seconds: int,
    commands: dict[str, list[str]],
) -> str:
    serve_block = _command_block([commands["serve"]])
    finish_block = _command_block([commands["audit"], commands["result"]])
    wall_time_label = _wall_time_label(wall_time_seconds)
    return f"""# Run Instructions for This Evaluation

- Task: `{task_id}`
- Test point: `{case_id}`
- Host evaluation directory: `{run_dir}`
- Agent's only workspace: `{workspace}`
- Local copy of the public key for auditing: `{trusted_key}`
- Wall-clock time budget after Arthur starts: `{wall_time_label}`

Data generation for this directory is complete. This is a one-shot evaluation session; do not reuse or reset it.

## 1. Start Arthur in the Host Terminal

The following commands are already written for the operating system currently used to generate this evaluation:

{serve_block}

Keep the Arthur process running, especially after the first event; the current runtime cannot resume an
active session. Its printed token has already been written to the Agent workspace's one-shot connection
file, so there is no need to copy environment variables manually. The wall-clock countdown begins when
`arthur serve` loads this runtime; the time spent starting the Agent, reading the task, and solving all
counts against the budget above.

Arthur also prints `AIP_OBSERVER_URL`. Open the complete URL in a local browser to observe the current
task, test point, at most two simple data features, elapsed time, redacted key interactions, and result.
The URL carries a separate read-only observer credential, not the participant token used by the Agent; do
not give it to the Agent or publish it in logs, screenshots, or reports. The Observer reads only bounded
summaries, cannot submit events, and does not show the private instance, seed, complete payload, or other
runtime secrets.

## 2. Start the Agent Under Evaluation

Set the evaluated Agent's readable and writable root directory to this workspace:

```text
{workspace}
```

Then use the full contents of `AGENT_PROMPT.md` in that workspace as the Agent's initial instructions.
For a CLI, SDK program, or existing model harness, the host may instead launch the repository's
`scripts/run_harness.py`; it reads `{HARNESS_MANIFEST_FILENAME}`, supports common prompt-delivery modes,
and passes only explicitly selected provider environment variables by default.
Do not use the entire repository, the Host evaluation directory, or their common parent directory as the
Agent workspace. This is a one-task, one-test-point, one-shot evaluation; do not create additional
`suite/run/case` subdirectories.

## 3. Audit and View the Score After a Terminal Status

After Arthur returns a terminal status, keep the service running if you want the Observer to display the
audit result as well, and run the following in another host terminal:

{finish_block}

`audit` should report `VALID` for every structural check; use `OFFICIAL_RESULT` and `result show`
for the final score. An `ACCEPT` returned by Arthur alone is not yet an official `PASS`; until the
independent audit completes, the Observer shows only “Awaiting audit.” After the page shows the audit
result, return to the Arthur terminal and stop the service with Ctrl+C. If you do not need the web result,
you may stop the service before running the CLI above.

## Structural and Actual Permission Boundaries

`{CONNECTION_FILENAME}` in the workspace is a one-shot secret; do not share it. On POSIX, the script
attempts to set `0600`, but this is not equivalent to an owner-only ACL on Windows. The public instance,
protocol, specification, schemas, client, and connection configuration needed by the Agent are all
concentrated in the Agent workspace. Its default location is the top-level `workspace/` in the Host
evaluation directory; see the beginning of this document for the actual path for this run. The Agent does
not need access to the workspace's parent directory or any other Host files.

However, “open only the workspace in Agent tools” and the prompt's prohibition on leaving it are not
operating-system permission mechanisms. If the Agent and Arthur run as the same OS user and the Agent has
unrestricted filesystem tools, it can theoretically read the Host directory through `..` or absolute
paths. The default layout is therefore structural isolation to prevent mistakes and is suitable for local
debugging by honest Agents; it must not be claimed to resist malicious Agents. Where strong isolation is
needed, use different OS users on Windows or POSIX, or use containers, VMs, or a remote Arthur, and expose
only the workspace and Participant API to the Agent.

The public key above is a local copy outside the run; it can serve as a trust anchor only if the Agent
truly cannot modify it. The separate read-only credential in `AIP_OBSERVER_URL` is likewise a temporary
secret. It does not permit participant write operations, but it exposes public statistics and interaction
summaries for this run, so use it only in a local human observer's browser. Formal evaluations must still
isolate `private/` and `official/` with different users, containers, or remote Arthur, and keep the public
key in a location the Agent cannot read or write.
"""


def prepare_evaluation(
    *,
    task_id: str,
    case_id: str,
    seed: bytes,
    port: int,
    output_dir: Path | None,
    workspace_dir: Path | None = None,
    plugin: TaskPlugin | None = None,
    cli_module: str = "aipbench.cli.main",
    specification_path: Path | None = None,
) -> tuple[Path, Path, Path]:
    """Generate a run and Agent workspace with public task files plus one-shot credentials."""

    plugin = plugin or default_registry().get(task_id)
    if plugin.manifest["id"] != task_id:
        raise ValueError("plugin task identity mismatch")
    if case_id not in plugin.case_parameters:
        choices = ", ".join(sorted(plugin.case_parameters))
        raise ValueError(f"unknown case {case_id!r} for {task_id}; choose one of: {choices}")
    specification = specification_path or _task_specification_path(plugin.manifest)
    public_schema_reference = _public_schema_reference(plugin.manifest)

    run_dir = _create_empty_output_dir(
        task_id=task_id,
        case_id=case_id,
        output_dir=output_dir,
    )
    workspace = _resolve_agent_workspace(run_dir=run_dir, workspace_dir=workspace_dir)
    trusted_key = run_dir.with_name(f"{run_dir.name}.trusted-key.json")
    if trusted_key.exists():
        raise ValueError(f"refusing to overwrite existing trusted key: {trusted_key}")

    runtime = ArthurRuntime.create(
        plugin=plugin,
        case_id=case_id,
        run_dir=run_dir,
        mode=SessionMode.EVAL,
        instance_seed=seed,
        coin_seed=secrets.token_bytes(32),
    )
    workspace.mkdir(parents=True, exist_ok=True)
    if any(workspace.iterdir()):
        raise ValueError(f"Agent workspace must be new or empty: {workspace}")
    for filename in ("instance.json", "protocol.json"):
        shutil.copy2(runtime.run_dir / "public" / filename, workspace / filename)
    shutil.copy2(REPOSITORY_ROOT / "examples" / "agent_client.py", workspace)
    shutil.copy2(specification, workspace / "TASK_SPECIFICATION.md")
    schema_references = {
        public_schema_reference,
        *_schema_references(runtime.protocol_description),
    }
    for reference in sorted(schema_references):
        _copy_repository_file(reference=reference, workspace=workspace)

    connection_path = workspace / CONNECTION_FILENAME
    _write_json(
        connection_path,
        {
            "api_version": "aip/1",
            "endpoint": f"http://127.0.0.1:{port}",
            "session_token": runtime.session_token,
        },
    )
    with contextlib.suppress(OSError):
        connection_path.chmod(0o600)

    wall_time_seconds = int(plugin.manifest["resources"]["wall_time_seconds"])
    _write_text(
        workspace / "AGENT_PROMPT.md",
        _agent_prompt(
            task_id=task_id,
            task_title=str(plugin.manifest["title"]),
            case_id=case_id,
            wall_time_seconds=wall_time_seconds,
        ),
    )
    _write_json(
        workspace / HARNESS_MANIFEST_FILENAME,
        {
            "schema_version": HARNESS_SCHEMA_VERSION,
            "api_version": "aip/1",
            "task": {
                "id": task_id,
                "version": str(plugin.manifest["version"]),
                "title": str(plugin.manifest["title"]),
            },
            "case": {"id": case_id},
            "limits": {"wall_time_seconds": wall_time_seconds},
            "files": {
                "prompt": "AGENT_PROMPT.md",
                "task_specification": "TASK_SPECIFICATION.md",
                "instance": "instance.json",
                "protocol": "protocol.json",
                "client": "agent_client.py",
                "connection": CONNECTION_FILENAME,
            },
        },
    )
    shutil.copy2(runtime.run_dir / "official" / "signing_public_key.json", trusted_key)

    command_set = _commands(
        run_dir=runtime.run_dir, trusted_key=trusted_key, port=port, cli_module=cli_module
    )
    _write_text(
        runtime.run_dir / "RUN_INSTRUCTIONS.md",
        _run_instructions(
            task_id=task_id,
            case_id=case_id,
            run_dir=runtime.run_dir,
            workspace=workspace,
            trusted_key=trusted_key,
            wall_time_seconds=wall_time_seconds,
            commands=command_set,
        ),
    )
    return runtime.run_dir, workspace, trusted_key


def _build_parser() -> argparse.ArgumentParser:
    registry = default_registry()
    parser = argparse.ArgumentParser(
        description=("Generate one fresh eval directory, one Agent workspace, and run commands.")
    )
    parser.add_argument("--task", dest="task_id", choices=registry.ids(), required=True)
    parser.add_argument("--case", dest="case_id", required=True)
    parser.add_argument(
        "--seed",
        default="random",
        help="instance seed: 'random' (default) or at least 128 bits of hex",
    )
    parser.add_argument("--port", type=_parse_port, default=8765)
    parser.add_argument(
        "--output-dir",
        type=Path,
        help=(
            "new or empty evaluation directory; default creates a unique directory under "
            "the operating system's temporary directory"
        ),
    )
    parser.add_argument(
        "--workspace-dir",
        type=Path,
        help=("new or empty Agent workspace; default is <evaluation-directory>/workspace"),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        seed = _parse_seed(args.seed)
        run_dir, workspace, trusted_key = prepare_evaluation(
            task_id=args.task_id,
            case_id=args.case_id,
            seed=seed,
            port=args.port,
            output_dir=args.output_dir,
            workspace_dir=args.workspace_dir,
        )
    except (AIPBenchError, KeyError, OSError, ValueError) as exc:
        parser.error(str(exc))

    print(f"EVALUATION_DIRECTORY: {run_dir}")
    print(f"AGENT_WORKSPACE: {workspace}")
    print(f"AGENT_PROMPT: {workspace / 'AGENT_PROMPT.md'}")
    print(f"HARNESS_MANIFEST: {workspace / HARNESS_MANIFEST_FILENAME}")
    print(f"TRUSTED_PUBLIC_KEY: {trusted_key}")
    print(f"NEXT: read {run_dir / 'RUN_INSTRUCTIONS.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
