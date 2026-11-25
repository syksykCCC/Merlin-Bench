# Tier 3 overview

Tier 3 contains 24 cases whose final certificates are checked by native verification tools. Each case has a total wall-clock budget of **600 seconds**, including solving, submission, and verification. The Python runtime validates protocol framing and artifacts; the native checker validates the proof object.

| Catalog | Runtime ID | Cases | Participant specification | Native checker |
|---|---|---:|---|---|
| T3.1 | `t3.machine_checked_mathematics` | 8 | [Lean task](../tasks/tier3_applied/machine_checked_mathematics/TASK_SPECIFICATION.md) | Lean 4.19.0 |
| T3.2 | `t3.dafny_verified_programs` | 8 | [Dafny task](../tasks/tier3_applied/dafny_verified_programs/TASK_SPECIFICATION.md) | Dafny 4.11.0 with bundled Z3 |
| T3.3 | `t3.drat_bounded_hardware_safety` | 8 | [DRAT task](../tasks/tier3_applied/drat_bounded_hardware_safety/TASK_SPECIFICATION.md) | `drat-trim` |

## Reader-installed tools

Native executables are not bundled or installed by Merlin-Bench. Install them outside the extracted source directory, following the official upstream instructions:

- **Lean 4.19.0:** use the [official Lean installation instructions](https://lean-lang.org/install/) and select toolchain `leanprover/lean4:v4.19.0`. Set `AIPBENCH_LEAN` to the direct executable inside that toolchain. The runtime also recognizes this version in the standard elan toolchain directory. A PATH shim is used only when explicitly enabled with `AIPBENCH_ALLOW_ELAN_SHIM=1`; prefer the direct executable to avoid an implicit toolchain download.
- **Dafny 4.11.0:** install the matching official distribution, including its bundled Z3, using the [Dafny installation instructions](https://dafny.org/dafny/Installation). Set `AIPBENCH_DAFNY` to the executable, or add its directory to PATH. The fixed execution harness uses the Java backend, so install a JDK (JDK 17 is suitable), including `java`, `javac`, and `jar`. Set `AIPBENCH_JAVA_HOME` or `JAVA_HOME` to the JDK root, or put its `bin` directory on PATH.
- **drat-trim:** build [the upstream source](https://github.com/marijnheule/drat-trim) at commit `2e3b2dc0ecf938addbd779d42877b6ed69d9a985`. Set `AIPBENCH_DRAT_TRIM` to the executable, or add its directory to PATH. The host must provision the pinned revision; the runtime does not establish its provenance from the binary.
- **CaDiCaL 3.0.1:** install [release 3.0.1](https://github.com/arminbiere/cadical/releases/tag/rel-3.0.1) if running the supplied reference proof generator. Set `AIPBENCH_CADICAL` to the executable, or add its directory to PATH. Certificate checking itself uses drat-trim.

Environment variables above contain paths chosen by the reader. Executable variables point to a file; the Java home variables point to the JDK directory. For example, in PowerShell, use `$env:AIPBENCH_LEAN = (Resolve-Path "<toolchain-directory>/bin/lean.exe").Path` after replacing the placeholder with your installation location. On POSIX systems use `export AIPBENCH_LEAN="<toolchain-directory>/bin/lean"` with your chosen path. Apply the same pattern to the other executable variables. Do not put host installation paths or credentials in submitted artifacts.

## Trust and execution boundary

- Checker executables and versions are controlled by the evaluation host.
- The participant submits content-addressed artifacts; checker paths are host configuration.
- Native proof-checking calls default to a 600-second subprocess timeout. Acceptance also requires completion before the case's 600-second global deadline; subprocess timeouts do not extend it. Short version checks are infrastructure probes.
- Native checker stdout and stderr are diagnostic; the signed terminal and strict replay determine the official result.
- Replay repeats native verification from preserved inputs and artifacts after the participant session.

## Task summaries

**Machine-Checked Mathematics** asks for a Lean source artifact proving a generated theorem under a fixed prelude. The cases cover linear certificates, CRT reconstruction, graph-root recovery, affine and modular reconstruction, cube roots, subset certificates, and binary syndromes.

**Dafny-Verified Programs** asks for a Dafny artifact satisfying a generated functional and invariant specification. Cases progress from array properties to schedules, dependency validation, policy evaluation, handle tables, and memory-pool invariants.

**DRAT-Certified Bounded Hardware Safety** publishes a bounded transition-system CNF and requires a DRAT refutation of the unsafe formula. Cases cover FIFOs, arbitration, credit routing, and pipelines.

## Local validation

After installing and configuring the tools, run from the repository root:

```bash
python -m pytest tests/tasks/test_machine_checked_mathematics.py tests/tasks/test_dafny_verified_programs.py tests/tasks/test_drat_bounded_hardware_safety.py tests/integration/test_machine_checked_mathematics_end_to_end.py
```

Some tests skip when a native tool is unavailable. Read the skip summary: skipped native tests do not establish a successful Tier 3 validation. A missing checker is an infrastructure problem and must be resolved before evaluating that task.

For formal evaluation, use a separate user or container and limit participant access to host checker installations. See [manual evaluation](06_manual_agent_run.md) and [SECURITY.md](../SECURITY.md).
