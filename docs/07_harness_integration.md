# External model and harness integration

Merlin-Bench does not depend on a model vendor or agent framework. Any local CLI, SDK program, executable, or existing agent harness can participate through the same prepared workspace and localhost Participant API. Container and VM integrations may consume the same manifest, but their host adapter must explicitly map workspace paths and preserve a secure route to Arthur.

## Stable integration artifacts

`scripts/prepare_evaluation.py` creates these files in every participant workspace:

| File | Purpose |
|---|---|
| `harness.json` | machine-readable task, case, limit, and file contract |
| `AGENT_PROMPT.md` | initial instructions for the evaluated agent |
| `TASK_SPECIFICATION.md` | task relation and protocol |
| `instance.json` | concrete public instance |
| `protocol.json` | machine-readable event protocol |
| `agent_client.py` | dependency-free Participant API client |
| `.aipbench-connection.json` | one-shot localhost endpoint and session credential |

The harness manifest conforms to [`schemas/harness-manifest.schema.json`](../schemas/harness-manifest.schema.json). It contains no model API key, private instance, reference answer, coin seed, or signing key.

## Command adapter

The provider-neutral adapter launches an argv vector directly, without a shell:

```bash
python scripts/run_harness.py \
  --workspace /path/to/prepared/workspace \
  --inherit-env PROVIDER_API_KEY \
  --prompt-mode stdin \
  -- python /path/to/my_model_harness.py
```

Use the appropriate variable name for the selected provider. Repeat `--inherit-env NAME` when a harness needs several values. The adapter copies values from its own environment directly into the child process; values are not placed in command arguments, workspace files, or adapter output.

Prompt modes are:

- `environment`: publish `AIP_PROMPT_FILE` and let the harness read it;
- `stdin`: send the full prompt as standard input;
- `argument`: append the full prompt as the final argv element;
- `path-argument`: append the prompt path as the final argv element.

`--inherit-all-env` is an explicit compatibility escape hatch for complex existing harnesses. The allowlist form is preferred for reproducibility and credential control.

## Child-process environment

Every launched harness receives:

| Variable | Value |
|---|---|
| `AIP_WORKSPACE` | absolute participant workspace |
| `AIP_HARNESS_MANIFEST` | absolute `harness.json` path |
| `AIP_PROMPT_FILE` | initial prompt path |
| `AIP_TASK_SPECIFICATION_FILE` | participant specification path |
| `AIP_INSTANCE_FILE` | public instance path |
| `AIP_PROTOCOL_FILE` | protocol description path |
| `AIP_CLIENT_FILE` | generic Python client path |
| `AIP_CONNECTION_FILE` | one-shot connection file path |
| `AIP_ENDPOINT` | localhost Arthur endpoint |
| `AIP_SESSION_TOKEN` | one-shot Participant API credential |
| `AIP_TASK_ID`, `AIP_TASK_VERSION`, `AIP_CASE_ID` | native task/version/case identity |
| `AIP_FIXTURE_ID` | unique Tier 3+ fixture ID, present only for extension runs; also in `harness.json` as `case.fixture_id` |
| `AIP_WALL_TIME_SECONDS` | configured total case budget |

The launcher reads the one-shot session token from the prepared connection file and also injects it into the child environment for harnesses that do not use the copied client. Model-provider credentials are inherited only when requested; the launcher itself never writes or prints their values.

## Direct SDK integration

A custom program may ignore the launcher and read `harness.json` directly. It can call Arthur by importing `AgentClient` from the copied `agent_client.py`, invoking that script as a subprocess, or implementing the documented HTTP API itself. The API contract is independent of how the model is queried.

The model-facing harness remains responsible for converting model output into exact task events, maintaining state across interactive rounds, uploading artifacts, enforcing its own model-call timeouts, and continuing until Arthur returns a terminal response.

## Fair-comparison requirements

- Use one fresh model session for one task/case/seed attempt.
- Record model identifier, reasoning setting, harness version, command, seed, and dependency versions.
- Do not reuse context, trajectories, outputs, or solver state across scored cases.
- Do not expose paths outside the participant workspace except the installed harness executable and required runtime libraries.
- Never write provider keys into configuration, result, trajectory, or archive files.
- Score only the signed terminal plus strict replay-derived official result.
