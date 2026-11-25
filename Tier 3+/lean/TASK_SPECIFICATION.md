# Machine Checked Mathematics Long Horizon Proofs

Task identity: `t3.machine_checked_mathematics_long_horizon`, version `0.2.0`.
Eight fixed targets are selected by `lean-01` through `lean-08`. The `c09` and `c10` native slots are compatibility identifiers; the supplied `Challenge.Target` defines the actual problem.

Prove the exact `Challenge.Target` in the supplied `Challenge.lean`. Upload one UTF-8 `Solution.lean` artifact exporting `AMBenchSolution.proof : Challenge.Target`, using the original `lean.proof` event and the supplied instance digest. The public `protocol.json`, schemas, and participant client specify the API. The fixed Lean 4.19.0 kernel must accept the proof with no axioms. All original forbidden-source, artifact-size, single-event and protocol restrictions remain in force. The reference proof is not participant material.

## Exact source and artifact requirements

- Submit one nonempty UTF-8 artifact, at most 262144 bytes, media type `text/x-lean; charset=utf-8`. Its text must have no NUL, no initial byte-order mark, no carriage returns (use LF line endings), and must end with a newline.
- Its only import must be exactly `import Challenge`. The source must contain exactly one occurrence of the word `import`. Do not import additional modules or include extra import mentions in comments.
- Export `AMBenchSolution.proof : Challenge.Target`. The kernel must report that this declaration does not depend on any axioms. A locally accepted proof relying on axioms does not satisfy this task.
- The native source filter rejects lines beginning with optional whitespace followed by `#`, and these word tokens anywhere in the source, including comments: `sorry`, `admit`, `axiom`, `opaque`, `unsafe`, `unsafeCast`, `macro`, `syntax`, `elab`, `run_tac`, `initialize`, `builtin_initialize`, `set_option`, `native_decide`, `implemented_by`, `extern`.
- The filter also rejects `IO`, `EIO`, `BaseIO`, `FilePath`, `System`, and `Process` followed by whitespace, a dot, or end of input; and rejects `Lean.ofReduceBool` and `Lean.trustCompiler`.
- The host stages a fresh copy of the public challenge and prelude and an immutable verification wrapper. Do not attempt to modify the wrapper or verifier. The uploaded solution alone is checked; arbitrary extra local files are not incorporated into the proof environment.
- There is one submission event. Its kind is `lean.proof`, its payload has exactly `instance_sha256` matching this public instance, and it references exactly one uploaded artifact. Follow the provided session identity, sequence and client schema. Rejected, mismatched, late or malformed submissions do not establish acceptance.

The evaluation budget is 600 seconds, including construction, local checking, upload, and native verification. Local success alone does not count as acceptance. The host must enforce finite subprocess lifetimes and participant access restrictions. Follow the prepared workspace instructions and submit through its Participant API.
