# Evaluation guide

Run the commands below from the repository root after installation.

## 1. Prepare one test point

For the base benchmark:

```bash
python scripts/prepare_evaluation.py --task t2.new_boolean_hypercube_sumcheck --case c01 --seed random
```

Use an explicit hex seed of at least 128 bits instead of `random` when a fixed
generated instance is needed. Record the task/version, case, and seed in your
evaluation records.

For Tier 3+:

```bash
python scripts/prepare_tier3_plus.py --fixture lean-01
```

Use `lean-01` through `lean-08`, `dafny-01` through `dafny-08`, or `drat-01`
through `drat-08`. These fixture IDs are unique; native case slots such as `c04`,
`c09`, and `c10` are reused and cannot identify an extension test point alone.

Both preparation commands print a **host run directory**, a **participant
workspace**, and a **trusted public-key file**. By default, generated files go
to the system temporary directory. For persistent evaluations, pass
`--output-dir /path/to/new/host-run` and `--workspace-dir /path/to/new/workspace`,
using fresh directories outside this checkout. Keep the host run and trusted key
under evaluator control. Do not give the participant the full repository.

## 2. Start Arthur, then launch your agent

Follow the generated `RUN_INSTRUCTIONS.md` in the host run directory. It contains
exact, platform-specific commands to start the HTTP verifier, audit the run, and
show its result. For Tier 3+, these commands select the extension-aware CLI.
Do not restart Arthur to extend an attempt's budget.

Give the agent only its prepared workspace. It contains `AGENT_PROMPT.md`,
`TASK_SPECIFICATION.md`, `instance.json`, `protocol.json`, JSON schemas,
`agent_client.py`, connection data, and `harness.json`. Tier 3+ also extracts the
native challenge/prelude, Dafny harness, or circuit/CNF into readable files.

Any local CLI or SDK-based harness can use the same API:

```bash
python scripts/run_harness.py --workspace /path/to/workspace --inherit-env PROVIDER_API_KEY --prompt-mode stdin -- python /path/to/model_harness.py
```

Replace the credential variable with the one your harness needs. Credentials are
passed only when explicitly selected; they are not stored by the launcher. See
[harness integration](07_harness_integration.md) for environment variables,
prompt delivery, and the `harness.json` contract.

Inside the participant workspace, `python agent_client.py info` inspects the
session. The agent uploads artifacts with `upload` and submits protocol messages
with `event`; `python agent_client.py --help` describes the interface. Follow the
task-specific event schema and submission limits. A Tier 3/3+ local compiler or
checker success is insufficient: the artifact must be uploaded and submitted to
Arthur before the deadline.

## 3. Audit and score

After the terminal result, execute the generated audit command with the external
trusted public key. **PASS requires a signed `ACCEPT`, a valid strict replay
audit, and `official_result=PASS`.** A valid audit of a rejection is still FAIL.
Missing native checkers and host failures are infrastructure failures and must
not be reported as agent capability failures. Keep outputs outside this dataset
repository and record the exact release, case identity, model, seed (base cases),
tool configuration, and attempt policy for any comparison.

Workspace separation alone is not an operating-system sandbox. A formal host
must enforce participant filesystem, network, and process limits using a separate
user, container, or VM. See [SECURITY.md](../SECURITY.md) and the
[repository overview](../README.md).

