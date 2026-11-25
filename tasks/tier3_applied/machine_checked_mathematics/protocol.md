# Protocol

All eight opaque cases use one deterministic, one-shot Lean proof protocol.

1. Merlin uploads one UTF-8 Lean source artifact.
2. Merlin sends sequence `0`, kind `lean.proof`, exact payload
   `{"instance_sha256":"<64 lowercase hex>"}`, and exactly one artifact ID.
3. Arthur binds the digest, validates the source envelope, rebuilds the public
   `AMBenchPrelude.lean` and `Challenge.lean`, and compiles the module chain
   with the pinned direct Lean 4.19.0 executable.
4. Only after `Solution.lean` compiles, Arthur writes a fresh, byte-checked wrapper requiring
   `AMBenchSolution.proof : Challenge.Target`; only that wrapper's output supplies the empty-axiom
   audit result.
5. Arthur accepts iff every check succeeds.  No participant-visible challenge,
   retry, preflight endpoint or detailed checker log exists.

Instance generation is deterministic from a seed supplied before session creation and the exact
generated instance is bound by its digest. The proof protocol samples no challenge coins and its
manifest therefore declares `randomness: none`.
It is deterministic proof-carrying verification, not a probabilistic AM
protocol.

The implementation deliberately fixes the core-only
`leanprover/lean4:v4.19.0` toolchain.  It resolves a direct executable from
`AIPBENCH_LEAN` or the matching local elan toolchain directory; it does not
silently invoke an updating `stable` shim.  Missing or mismatched toolchains are
host errors, never a Python substitute for kernel checking.
