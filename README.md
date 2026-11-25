# Merlin-Bench

Merlin-Bench evaluates agents that solve problems, construct certificates, and
interact with a verifier. The agent plays **Merlin**; the trusted runtime plays
**Arthur**. This repository provides **124 test points** and their evaluation
interfaces, with a **600-second wall-clock budget per attempt**.

## Dataset

| Subset | Cases | Verification | Data |
|---|---:|---|---|
| Tier 1 | 36 | Deterministic certificates | [tasks/tier1_np](tasks/tier1_np/) |
| Tier 2 | 40 | Interactive proof protocols | [tasks/tier2_interactive](tasks/tier2_interactive/) |
| Tier 3 | 24 | Lean, Dafny/Z3, and DRAT | [tasks/tier3_applied](tasks/tier3_applied/) |
| Tier 3+ (provisional) | 24 | 8 Lean + 8 Dafny + 8 DRAT instances | [Tier 3+](Tier%203+/README.md) |
| **Total** | **124** | | |

The original **100 cases are generator-defined**: a task, case, and seed determine
an instance. **Tier 3+ contains 24 fixed instances**, each with a unique fixture
ID and verified source files. Report the base and extension scores separately.
The [complete catalog](catalog/release_catalog.json) lists all 124 points, task
versions, and preparation commands.

This is a dataset and evaluation-code release. It contains no experimental
results, model trajectories, historical runs, or bundled native binaries.

## Install

Use **Python 3.12**. From this checkout:

```bash
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install -e ".[dev]"
```

On Windows PowerShell, create and activate the environment with
`py -3.12 -m venv .venv` and `.\.venv\Scripts\Activate.ps1`, then run the same pip command.
Keep the checkout available: manifests and dataset files are loaded from it.

Tier 3 and Tier 3+ also need **Lean 4.19.0**, **Dafny 4.11.0 with bundled Z3 and
a JDK**, or the pinned **drat-trim** revision. See [native tool setup](docs/12_tier3_task_overview.md).
Python imports and environment variables retain the `aipbench` / `AIP_*` namespace.

## Quick start

Inspect the data and verify release integrity:

```bash
merlin-bench task list
merlin-bench case list --task t1.new_maxflow_min_cut
python scripts/prepare_tier3_plus.py --list
python scripts/check_release.py
```

Prepare a base case or a fixed Tier 3+ instance:

```bash
python scripts/prepare_evaluation.py --task t2.new_boolean_hypercube_sumcheck --case c01 --seed random
python scripts/prepare_tier3_plus.py --fixture lean-01
```

Tier 3+ IDs are `lean-01` through `lean-08`, `dafny-01` through `dafny-08`, and
`drat-01` through `drat-08`. Select by fixture ID: native case slots are reused.
Use an explicit hex seed of at least 128 bits for reproducible base instances.

Each command prints a host run directory, participant workspace, and trusted
public-key file. Outputs default to the system temporary directory. Use
`--output-dir` and `--workspace-dir` to choose fresh locations outside this repository.

1. Follow the generated host `RUN_INSTRUCTIONS.md` to start Arthur.
2. Give your agent only the prepared participant workspace. Its specifications,
   `instance.json`, `protocol.json`, client, and `harness.json` define the task and API.
3. After submission, run the generated audit command with the trusted public key.
   **PASS requires signed `ACCEPT`, a valid strict replay, and `official_result=PASS`.**

Any local CLI or SDK-based model harness can use the generic launcher:

```bash
python scripts/run_harness.py --workspace /path/to/workspace --inherit-env PROVIDER_API_KEY --prompt-mode stdin -- python /path/to/model_harness.py
```

See the [evaluation guide](docs/06_manual_agent_run.md) for the full workflow and
[harness integration](docs/07_harness_integration.md) for connection details.
For formal evaluations, enforce participant isolation as described in [SECURITY.md](SECURITY.md).
Keep reference solvers, host files, and generated results outside the participant workspace.

## Repository guide

- [catalog/](catalog/): the base catalog and combined 124-point index.
- [tasks/](tasks/) and [Tier 3+/](Tier%203+/README.md): specifications, parameters, schemas, and fixed instances.
- [src/aipbench/](src/aipbench/): runtime, protocols, and native verifiers.
- [scripts/](scripts/README.md) and [examples/](examples/): preparation, harness launcher, and participant client.
- [tests/](tests/): contract, security, and integration tests.
- [docs/](docs/README.md): API and task documentation; [benchmark card](BENCHMARK_CARD.md) and [release notes](docs/RELEASE_NOTES.md).

## Validation

```bash
python scripts/check_documentation.py
python scripts/check_release.py
python -m pytest tests/integration/test_tier3_plus.py tests/unit/test_harness_runner.py
```

For complete development checks, run `python -m pytest`, `ruff check .`,
`ruff format --check .`, and `mypy`. The full suite includes many-seed reference
solvers and can take tens of minutes. Tests needing unavailable native tools are
skipped; those skips do not establish native verification coverage.

## License

[Apache License 2.0](LICENSE). Separately installed native tools retain their
upstream licenses.
