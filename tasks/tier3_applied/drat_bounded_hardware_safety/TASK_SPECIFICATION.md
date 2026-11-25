# Task Specification

Task ID: `t3.drat_bounded_hardware_safety`. Version: `0.8.0`.

The public instance contains:

- `aiger_aag`: a standard sequential ASCII AIGER circuit with one `bad` output;
- `bound`: the public bounded-model-checking horizon;
- `bound_cnf`: a standard DIMACS CNF encoding the initialized circuit through
  that horizon together with the assertion that `bad` holds in at least one
  frame;
- SHA-256 digests and exact CNF dimensions.

Submit a single standard DRAT proof showing that `bound_cnf` is unsatisfiable.
ASCII and binary DRAT are both accepted by the native checker, subject to the
artifact-size limit.  Arthur writes the digest-bound DIMACS bytes and submitted
proof into a fresh directory and invokes pinned `drat-trim`; no Python proof
checker or benchmark-specific inference rule is used.

Upload the proof artifact, then send the one allowed event:

```json
{
  "sequence": 0,
  "kind": "hardware.drat",
  "payload": {"instance_sha256": "<public instance digest>"},
  "artifact_refs": ["<uploaded artifact id>"]
}
```

Evaluation is one-shot.  There is no preflight checker or detailed checker log.
The accepted claim is bounded safety only, for the exact published horizon.
