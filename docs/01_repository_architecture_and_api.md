# Repository architecture and Arthur API

## Trust boundary

Merlin receives a public workspace and communicates through the participant API. Arthur owns generation, fresh randomness, private instance data, artifact storage, transcript hashing, the signing key, verification, and timeout materialization. A result becomes official only after independent strict replay audit.

```text
public task + seed
        |
        v
   ArthurRuntime  <---- participant HTTP events/artifacts ----  Merlin
        |
        +---- public/      immutable instance and protocol
        +---- private/     seeds, private instance, runtime secret
        +---- official/    transcript, result, signature, audit
```

The generated workspace is a disclosure boundary, not an OS sandbox. Production evaluation must enforce filesystem, process, network, memory, CPU, and child-process restrictions outside Python.

## Main components

- `aipbench.registry`: validates `task.yaml` and exposes only the 15 current task IDs. Registry listing loads manifests without importing plugin implementations.
- `aipbench.core.runtime.ArthurRuntime`: owns one task/case session, enforces sequence and resource limits, stores artifacts, calls the protocol, and signs a terminal result.
- `aipbench.transport.http`: authenticated participant endpoints and a separate read-only bounded observer.
- `aipbench.transport.inprocess`: deterministic developer/test adapter with the same event envelope semantics.
- `aipbench.audit`: revalidates files, signature, digests, randomness, event chain, artifacts, and protocol replay.
- `aipbench.tasks`: generators and protocol/verifier implementations. The [registry](../src/aipbench/registry/task_registry.py) lists the current entry points. [Shared components](../src/aipbench/tasks/shared/) contain protocol and generation primitives reused by these tasks; they do not register additional tasks.

## Task plugin contract

A plugin exposes four values:

```python
manifest          # validated task metadata
case_parameters   # c01...cNN -> generator parameters
generator         # seed + case -> public/private GeneratedCase
protocol          # initialize + handle_event state machine
```

The registered manifest must exactly equal the plugin manifest. The active manifest list is explicit in `src/aipbench/registry/task_registry.py`.

All current manifests set `wall_time_seconds: 600`. Protocol `max_events` and resource `max_events` must agree. Tier-1 and Tier-3 are one-shot; Tier-2 protocols may use multiple messages or a bind/challenge/open exchange.

## Participant API

Every request uses the session bearer token. The public surface is:

- `GET /v1/session`: identity, lifecycle, commitment, and budgets;
- `GET /v1/protocol`: event kinds, schemas, and protocol metadata;
- `GET /v1/instance`: immutable public instance;
- `POST /v1/artifacts`: content-addressed artifact upload within size/time limits;
- `POST /v1/events`: the next strictly sequenced participant event.

There is no participant endpoint for private instances, seeds, resets, retries, checker logs, or reference solutions. Evaluation feedback is minimal. A terminal session rejects additional events.

The event envelope is:

```json
{
  "api_version": "aip/1",
  "session_id": "...",
  "sequence": 0,
  "kind": "task-specific.kind",
  "payload": {},
  "artifact_refs": []
}
```

JSON shape, session binding, exact next sequence, allowed kind, payload schema, and artifact references are checked before task logic runs.

## Randomness and transcript

Tasks that use Arthur randomness derive it from a committed seed with domain-separated tags such as:

```text
t2.new_graph_non_isomorphism/c01/gni/lane-17/source-bit
```

The commitment is published before interaction and the seed is revealed only at terminal. Each transcript record binds the previous hash, direction, event/reply data, and relevant digests. Strict audit regenerates the case and replays the protocol instead of trusting the immediate verdict.

## Run layout

```text
<evaluation>/
├── RUN_INSTRUCTIONS.md
├── public/
│   ├── instance.json
│   └── protocol.json
├── private/
│   ├── generation.metadata.json
│   ├── instance.private.json
│   └── runtime.json
├── official/
│   ├── artifacts/
│   ├── session.json
│   ├── task_manifest.json
│   ├── transcript.jsonl
│   ├── result.json
│   ├── result.sig
│   └── audit.json
└── workspace/
    ├── AGENT_PROMPT.md
    ├── TASK_SPECIFICATION.md
    ├── agent_client.py
    ├── instance.json
    ├── protocol.json
    └── copied public schemas
```

The trusted public key should be stored outside the Agent's writable area. Files under `private/` and the bearer token must never enter experiment logs or a published workspace.

## Terminal and scoring semantics

Arthur can end in `ACCEPT`, `REJECT`, `TIMEOUT`, or a host/system error state. A mathematically rejected submission is a normal, auditable run. Official PASS requires:

1. a valid signed terminal result with `terminal_status=ACCEPT`;
2. a successful strict replay audit;
3. `official_result=PASS` in scorer-authorized output.

Evaluation records may additionally disqualify an Arthur-accepted run for a procedural boundary violation. Such a row remains `official_result=FAIL` in the experiment CSV; analysis must not infer success from `terminal_status` alone.

## Observer

The optional observer has a separate read-only token. It shows the task/case, at most two public size features, bounded event summaries, elapsed time, and the current/audited outcome. It never serializes full instances, challenges, certificates, source files, seeds, tokens, or private data.

## Current task-specific details

The architecture is task-neutral. Exact event kinds, payloads, native checker commands, and soundness arguments belong in the participant specifications under `tasks/`. The current inventory is summarized in [`04_benchmark_tiers_and_testpoints.md`](04_benchmark_tiers_and_testpoints.md).
