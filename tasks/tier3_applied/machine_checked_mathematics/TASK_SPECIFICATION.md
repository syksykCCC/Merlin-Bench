# Machine-Checked Mathematics

You must submit one Lean 4 source file proving the exact proposition published
as `Challenge.Target`.  Arthur accepts only if the pinned Lean 4.19.0 kernel
checks your proof and its axiom audit is empty.

- Task ID: `t3.machine_checked_mathematics`
- Task version: `0.1.0`

## 1. Public input

The public instance has format `aip-lean-proof-instance/1` and contains:

- `toolchain`: exactly `leanprover/lean4:v4.19.0`;
- `prelude_source`: the complete UTF-8 source for `AMBenchPrelude.lean`;
- `challenge_source`: the complete UTF-8 source for `Challenge.lean`;
- `prelude_sha256` and `challenge_sha256`: lowercase SHA-256 hashes of those
  exact UTF-8 byte strings;
- `target_name`: exactly `Challenge.Target`;
- `proof_name`: exactly `AMBenchSolution.proof`;
- `problem`: a structured copy of the mathematical data;
- `public_features`: auxiliary public metadata;
- `instance_sha256`: the lowercase digest that must be echoed at submission.

All lists and array-like objects use zero-based indexing. `Challenge.lean` is
authoritative if a redundant explanatory field differs from it.

## 2. Required proof file

Upload exactly one ordinary UTF-8 file named conceptually `Solution.lean`.
Its required interface is:

```lean
import Challenge

namespace AMBenchSolution

theorem proof : Challenge.Target := by
  -- your proof

end AMBenchSolution
```

The source must:

1. contain exactly one import, `import Challenge`;
2. be UTF-8 without BOM, NUL or carriage-return bytes and end in one newline;
3. be at most 262,144 bytes;
4. export `AMBenchSolution.proof` with a type definitionally equal to
   `Challenge.Target`.

The submission is source only.  Do not upload `.olean`, a directory, an
archive, a host path or a command line.

The following are rejected before or during checking: `sorry`, `admit`, a new
`axiom` or `opaque` declaration, `unsafe`, custom `macro`/`syntax`/`elab`,
`run_tac`, `initialize`, `set_option`, every participant top-level `#` command,
the `IO`/`EIO`/`BaseIO` and host file/process namespaces, `@[extern]`, or any import other
than `Challenge`.  `implemented_by`, `Lean.ofReduceBool`, `Lean.trustCompiler` and
`native_decide` are also forbidden.

## 3. Submission protocol

This is a one-shot protocol.  There is no retry and no checker feedback before
the terminal result.

1. Upload `Solution.lean` through the artifact endpoint, with media type
   `text/x-lean; charset=utf-8`, and save the returned
   `sha256:<64 lowercase hex>` artifact ID.
2. Send sequence `0`, kind `lean.proof`, with exact payload

   ```json
   {"instance_sha256":"<the public instance_sha256>"}
   ```

   and exactly one `artifact_ref`, the uploaded source artifact.

## 4. Arthur's checks

Arthur verifies the exact event contract and instance digest, the source byte
profile and source restrictions, the hashes of the two public modules, and
compilation under the pinned Lean 4.19.0 toolchain. It then checks
`AMBenchSolution.proof` at the exact type `Challenge.Target` and rejects any
axioms reported for that declaration.

## 5. Time budget

The complete evaluation has a 600-second wall-clock budget starting when
Arthur loads the run. Reading, computation, local checking, upload and the
terminal response all share that budget. An HTTP timeout does not extend it.
