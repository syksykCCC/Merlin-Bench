# Tier 3+ (provisional)

This extension contains **24 fixed test points: eight Lean, eight Dafny, and eight
DRAT cases**. It supplements the original 100-case benchmark. Every case has the
same 600-second global budget and native verification requirements as its domain.

## Use

From the repository root, after installation:

```bash
python scripts/prepare_tier3_plus.py --list
python scripts/prepare_tier3_plus.py --fixture lean-01
```

Follow the printed host run's `RUN_INSTRUCTIONS.md`. The prepared workspace uses
the same Participant API and `harness.json` as the base benchmark. The generated
serve/audit commands use `python -m aipbench.tier3_plus.cli` to register the
long-horizon Lean protocol. Use that CLI for extension runs, including their
independent audit. See the [main evaluation walkthrough](../README.md#evaluate-an-agent).

The unique fixture ID identifies a test point. Native task/case slots are retained
for compatibility and are reused across fixtures; never select or aggregate Tier
3+ by native slot alone. There is no seed option: these exact instances are fixed.
Each attempt still receives fresh session credentials and signing material.

## Contents and identity

Each case directory contains `instance.json`, `protocol.json`, and extracted
native assets. Lean provides `Challenge.lean` and `AMBenchPrelude.lean`; Dafny
provides `Challenge.dfy` and `Harness.dfy`; DRAT provides `circuit.aag` and
`bound.cnf`. The JSON instance is authoritative; extracted files must match its
embedded strings byte for byte. Preserve LF line endings in native submissions.

[manifest.json](manifest.json) records unique IDs, original candidate IDs, native
task/version/slot, file hashes, canonical JSON hashes, embedded instance digests,
and extracted asset hashes. The preparation command checks these before creating
a run. Native checker setup is documented [here](../docs/12_tier3_task_overview.md).

## Cases

| Fixture | Target | Native slot | Public files |
|---|---|---|---|
| `lean-01` | Transactional first-write rollback | `c09` | [files](lean/lean-01/) |
| `lean-02` | Lazy affine segment tree correctness | `c09` | [files](lean/lean-02/) |
| `lean-03` | Reverse-mode automatic differentiation | `c09` | [files](lean/lean-03/) |
| `lean-04` | Simply typed lambda calculus safety | `c10` | [files](lean/lean-04/) |
| `lean-05` | Exceptions and finally machine correctness | `c10` | [files](lean/lean-05/) |
| `lean-06` | Parallel reduction confluence for lambda calculus | `c09` | [files](lean/lean-06/) |
| `lean-07` | Typed closure machine safety | `c10` | [files](lean/lean-07/) |
| `lean-08` | Fuelled closure evaluator correctness | `c10` | [files](lean/lean-08/) |
| `dafny-01` | Affine loop safety by inductive halfspaces and Farkas certificates, with a faulty execution | `c04` | [files](dafny/dafny-01/) |
| `dafny-02` | Capture-avoiding beta reduction with typed traces under arbitrary binders | `c02` | [files](dafny/dafny-02/) |
| `dafny-03` | Fixed generalized Büchi intersection witnesses with executable certificate checking | `c06` | [files](dafny/dafny-03/) |
| `dafny-04` | Multi-pivot Davis–Putnam projection with constructive model reconstruction | `c03` | [files](dafny/dafny-04/) |
| `dafny-05` | Trace-oblivious compilation of stateful nested choices and indirect memory accesses | `c04` | [files](dafny/dafny-05/) |
| `dafny-06` | Reachability-game synthesis with paired strategies and finite-play certificates | `c08` | [files](dafny/dafny-06/) |
| `dafny-07` | Smith normal form certificates for two integer presentations | `c05` | [files](dafny/dafny-07/) |
| `dafny-08` | Longest strictly rising contiguous telemetry run | `c04` | [files](dafny/dafny-08/) |
| `drat-01` | serial-mod-five | `c05` | [files](drat/drat-01/) |
| `drat-02` | mesh-parity-conservation | `c06` | [files](drat/drat-02/) |
| `drat-03` | restartable-shift-add-multiplier | `c07` | [files](drat/drat-03/) |
| `drat-04` | self-routing-switch-fabric | `c08` | [files](drat/drat-04/) |
| `drat-05` | nested-checkpoint-undo-store | `c04` | [files](drat/drat-05/) |
| `drat-06` | dual-polynomial-retimed-crc | `c08` | [files](drat/drat-06/) |
| `drat-07` | epoch-tagged-carry-save-retirement | `c07` | [files](drat/drat-07/) |
| `drat-08` | buffered-dirty-eviction-refill | `c06` | [files](drat/drat-08/) |

## Participant specifications

- [Lean long-horizon proofs](lean/TASK_SPECIFICATION.md)
- [Dafny programs](../tasks/tier3_applied/dafny_verified_programs/TASK_SPECIFICATION.md)
- [DRAT proofs](../tasks/tier3_applied/drat_bounded_hardware_safety/TASK_SPECIFICATION.md)

For Dafny and DRAT, read the protocol and artifact sections of the native
specification; the original c01–c08 family descriptions apply to the base set.
The extension target is the exact supplied challenge/harness or circuit/CNF.

## Status

Tier 3+ is a provisional extension selected during development. Report its scores
separately from the original 100 cases. This directory contains no experimental
results, trajectories, reference solutions, or study guides. The toolkit enforces
native artifact/protocol checks; the evaluation host supplies process, filesystem,
and network isolation and records its tool-access policy.
