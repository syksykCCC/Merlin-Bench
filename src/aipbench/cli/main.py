"""The Merlin-Bench command-line interface."""

from __future__ import annotations

import hashlib
import json
import secrets
import tempfile
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import typer
import uvicorn
import yaml

from aipbench.audit import audit_run
from aipbench.core.models import SessionMode
from aipbench.core.runtime import ArthurRuntime
from aipbench.registry import default_registry
from aipbench.transport.http import create_app
from aipbench.transport.inprocess import InProcessParticipantClient

app = typer.Typer(help="Merlin-Bench Arthur runtime and audit tools.", no_args_is_help=True)
task_app = typer.Typer(help="Inspect registered task plugins.", no_args_is_help=True)
case_app = typer.Typer(help="Inspect and generate immutable task cases.", no_args_is_help=True)
arthur_app = typer.Typer(help="Run the Arthur participant service.", no_args_is_help=True)
dev_app = typer.Typer(help="Deterministic local virtual-agent runs.", no_args_is_help=True)
result_app = typer.Typer(help="Read official result artifacts.", no_args_is_help=True)
app.add_typer(task_app, name="task")
app.add_typer(case_app, name="case")
app.add_typer(arthur_app, name="arthur")
app.add_typer(dev_app, name="dev")
app.add_typer(result_app, name="result")


def _parse_seed(value: str) -> bytes:
    if value == "random":
        return secrets.token_bytes(32)
    normalized = value.removeprefix("0x")
    try:
        seed = bytes.fromhex(normalized)
    except ValueError as exc:
        raise typer.BadParameter("seed must be 'random' or an even-length hex string") from exc
    if len(seed) < 16:
        raise typer.BadParameter("seed must contain at least 128 bits")
    return seed


def _default_run_dir(*, task_id: str, case_id: str, agent_id: str) -> Path:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    suffix = secrets.token_hex(3)
    safe_task = task_id.replace(".", "-")
    return (
        Path(tempfile.gettempdir())
        / "merlin-bench-runs"
        / f"{timestamp}-{safe_task}-{case_id}-{agent_id}-{suffix}"
    )


def _virtual_agents(task_id: str) -> Mapping[str, Any]:
    if task_id == "t1.new_maxflow_min_cut":
        from aipbench.tasks.new_maxflow import VIRTUAL_AGENTS

        return VIRTUAL_AGENTS
    if task_id == "t1.new_weighted_partial_maxsat":
        from aipbench.tasks.new_weighted_partial_maxsat import VIRTUAL_AGENTS

        return VIRTUAL_AGENTS
    if task_id == "t1.new_list_graph_homomorphism":
        from aipbench.tasks.new_list_graph_homomorphism import VIRTUAL_AGENTS

        return VIRTUAL_AGENTS
    if task_id == "t1.new_rooted_group_steiner_tree":
        from aipbench.tasks.new_rooted_group_steiner_tree import VIRTUAL_AGENTS

        return VIRTUAL_AGENTS
    if task_id == "t1.new_structured_closest_vector":
        from aipbench.tasks.new_structured_closest_vector import VIRTUAL_AGENTS

        return VIRTUAL_AGENTS
    if task_id == "t1.new_structured_set_cover":
        from aipbench.tasks.new_structured_set_cover import VIRTUAL_AGENTS

        return VIRTUAL_AGENTS
    if task_id == "t2.new_graph_non_isomorphism":
        from aipbench.tasks.new_graph_non_isomorphism import VIRTUAL_AGENTS

        return VIRTUAL_AGENTS
    if task_id == "t2.new_boolean_hypercube_sumcheck":
        from aipbench.tasks.new_boolean_hypercube_sumcheck import VIRTUAL_AGENTS

        return VIRTUAL_AGENTS
    if task_id == "t2.new_gkr_layered_circuit":
        from aipbench.tasks.new_gkr_layered_circuit import VIRTUAL_AGENTS

        return VIRTUAL_AGENTS
    if task_id == "t2.image_size_lower_bound":
        from aipbench.tasks.image_size_lower_bound import VIRTUAL_AGENTS

        return VIRTUAL_AGENTS
    if task_id == "t2.new_shamir_tqbf":
        from aipbench.tasks.new_shamir_tqbf import VIRTUAL_AGENTS

        return VIRTUAL_AGENTS
    if task_id == "t2.new_hamiltonicity_bind_open":
        from aipbench.tasks.new_hamiltonicity_bind_open import VIRTUAL_AGENTS

        return VIRTUAL_AGENTS
    if task_id == "t3.machine_checked_mathematics":
        from aipbench.tasks.machine_checked_mathematics import VIRTUAL_AGENTS

        return VIRTUAL_AGENTS
    if task_id == "t3.dafny_verified_programs":
        from aipbench.tasks.dafny_verified_programs import VIRTUAL_AGENTS

        return VIRTUAL_AGENTS
    if task_id == "t3.drat_bounded_hardware_safety":
        from aipbench.tasks.drat_bounded_hardware_safety import VIRTUAL_AGENTS

        return VIRTUAL_AGENTS
    return {}


@task_app.command("list")
def task_list() -> None:
    """List registered task identifiers and titles."""
    for manifest in default_registry().list():
        typer.echo(f"{manifest['id']}\t{manifest['version']}\t{manifest['title']}")


@task_app.command("inspect")
def task_inspect(task_id: str) -> None:
    """Print a validated task manifest without importing its plugin."""
    try:
        manifest = default_registry().inspect(task_id)
    except KeyError as exc:
        raise typer.BadParameter(str(exc)) from exc
    # Built-in manifests intentionally do not duplicate the plugin's case table.
    # Suppress the Pydantic default instead of printing ``cases: {}``, which can
    # otherwise be mistaken for an empty runtime inventory.  ``case list`` is the
    # authoritative, plugin-backed inventory command.
    if not manifest.get("cases"):
        manifest.pop("cases", None)
    if not manifest.get("metadata"):
        manifest.pop("metadata", None)
    typer.echo(yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False).rstrip())


@case_app.command("list")
def case_list(task_id: str = typer.Option(..., "--task")) -> None:
    """List the real case identifiers exposed by a task plugin."""
    try:
        plugin = default_registry().get(task_id)
    except KeyError as exc:
        raise typer.BadParameter(str(exc)) from exc
    for case_id in plugin.case_parameters:
        typer.echo(case_id)


@case_app.command("generate")
def case_generate(
    task_id: str = typer.Option(..., "--task"),
    case_id: str = typer.Option(..., "--case"),
    seed: str = typer.Option("random", "--seed"),
    output: Path = typer.Option(..., "--output"),
    mode: SessionMode = typer.Option(SessionMode.EVAL, "--mode"),
) -> None:
    """Generate a prepared, one-shot run directory."""
    registry = default_registry()
    try:
        plugin = registry.get(task_id)
    except KeyError as exc:
        raise typer.BadParameter(str(exc)) from exc
    runtime = ArthurRuntime.create(
        plugin=plugin,
        case_id=case_id,
        run_dir=output,
        mode=mode,
        instance_seed=_parse_seed(seed),
        coin_seed=secrets.token_bytes(32),
    )
    typer.echo(f"RUN_DIRECTORY: {runtime.run_dir}")
    typer.echo(f"SESSION_ID: {runtime.session_id}")
    typer.echo("STATE: PREPARED")


@arthur_app.command("serve")
def arthur_serve(
    run_dir: Path = typer.Option(..., "--run-dir", exists=True, file_okay=False),
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8765, "--port", min=1, max=65535),
) -> None:
    """Serve a prepared case through the participant HTTP API."""
    session_path = run_dir / "official" / "session.json"
    session = json.loads(session_path.read_text(encoding="utf-8"))
    plugin = default_registry().get(session["task_id"])
    runtime = ArthurRuntime.load_prepared(plugin=plugin, run_dir=run_dir)
    observer_token = secrets.token_urlsafe(32)
    if host == "0.0.0.0":
        display_host = "127.0.0.1"
    elif host == "::":
        display_host = "[::1]"
    elif ":" in host and not host.startswith("["):
        display_host = f"[{host}]"
    else:
        display_host = host
    typer.echo(f"AIP_ENDPOINT=http://{display_host}:{port}")
    typer.echo(f"AIP_SESSION_TOKEN={runtime.session_token}")
    typer.echo(f"AIP_OBSERVER_URL=http://{display_host}:{port}/observer#token={observer_token}")
    uvicorn.run(
        create_app(runtime, observer_token=observer_token),
        host=host,
        port=port,
        log_level="info",
    )


@dev_app.command("run")
def dev_run(
    task_id: str = typer.Option(..., "--task"),
    case_id: str = typer.Option(..., "--case"),
    agent_id: str = typer.Option(..., "--agent"),
    output: Path | None = typer.Option(None, "--output"),
) -> None:
    """Run a deterministic virtual agent in process and audit the result."""
    registry = default_registry()
    try:
        plugin = registry.get(task_id)
    except KeyError as exc:
        raise typer.BadParameter(str(exc)) from exc
    agents = _virtual_agents(task_id)
    if agent_id not in agents:
        choices = ", ".join(sorted(agents))
        raise typer.BadParameter(f"unknown agent {agent_id!r}; choose one of: {choices}")
    run_dir = output or _default_run_dir(task_id=task_id, case_id=case_id, agent_id=agent_id)
    instance_seed = hashlib.sha256(f"aipbench/dev/instance/{task_id}/{case_id}".encode()).digest()
    coin_seed = hashlib.sha256(f"aipbench/dev/coins/{task_id}/{case_id}".encode()).digest()
    runtime = ArthurRuntime.create(
        plugin=plugin,
        case_id=case_id,
        run_dir=run_dir,
        mode=SessionMode.DEV,
        instance_seed=instance_seed,
        coin_seed=coin_seed,
        session_token="dev-session-token",
    )
    client = InProcessParticipantClient(runtime)
    workspace = runtime.run_dir / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    agents[agent_id].run(client=client, workspace=workspace)
    if runtime.terminal_result is None:
        typer.echo(f"RUN_DIRECTORY: {run_dir}")
        typer.echo("SYSTEM_ERROR: virtual agent stopped before a terminal result")
        raise typer.Exit(code=5)
    report = audit_run(run_dir, registry=registry)
    typer.echo(f"RUN_DIRECTORY: {run_dir.resolve()}")
    typer.echo(f"TERMINAL_STATUS: {runtime.terminal_result['terminal_status']}")
    typer.echo(f"REASON_CODE: {runtime.terminal_result['reason_code']}")
    typer.echo(f"AUDIT_VALID: {'PASS' if report['audit_passed'] else 'FAIL'}")
    typer.echo(f"OFFICIAL_RESULT: {report['official_result']}")
    if not report["audit_passed"]:
        raise typer.Exit(code=4)


@app.command("audit")
def audit_command(
    run_dir: Path = typer.Argument(..., exists=True, file_okay=False),
    trusted_public_key: Path | None = typer.Option(
        None, "--trusted-public-key", exists=True, dir_okay=False
    ),
) -> None:
    """Independently replay and validate a completed run directory."""
    trusted_key_value: str | None = None
    if trusted_public_key is not None:
        key_text = trusted_public_key.read_text(encoding="utf-8").strip()
        if key_text.startswith("{"):
            key_document = json.loads(key_text)
            trusted_key_value = str(key_document["public_key"])
        else:
            trusted_key_value = key_text
    report = audit_run(run_dir, trusted_public_key_base64=trusted_key_value)
    for check in report["checks"]:
        typer.echo(f"{check['name']}: {'VALID' if check['valid'] else 'INVALID'}")
    typer.echo(f"OFFICIAL_RESULT: {report['official_result']}")
    if not report["audit_passed"]:
        raise typer.Exit(code=4)


@result_app.command("show")
def result_show(run_dir: Path = typer.Argument(..., exists=True, file_okay=False)) -> None:
    """Show only scorer-authorized official result and audit fields."""
    official = run_dir / "official"
    payload = {
        "audit": json.loads((official / "audit.json").read_text(encoding="utf-8"))
        if (official / "audit.json").exists()
        else None,
        "result": json.loads((official / "result.json").read_text(encoding="utf-8")),
    }
    typer.echo(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":  # pragma: no cover
    app()
