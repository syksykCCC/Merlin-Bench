# Protocol

All eight cases use one deterministic one-shot protocol.

1. Merlin uploads one standard Dafny source artifact.
2. Merlin submits sequence `0`, kind `dafny.program`, the exact public instance
   digest, and exactly one artifact reference.
3. Arthur validates the source envelope and recreates a fresh combined source
   from the digest-bound public challenge, the submitted module, and the fixed
   harness.
4. Arthur runs pinned native `dafny verify` with deterministic settings and a
   finite verification limit.
5. Arthur runs the already-verified source through Dafny's Java target and
   accepts only if the fixed marker is produced exactly once.

The protocol is deterministic proof-carrying verification, not a probabilistic
coin-flip protocol.  Missing or mismatched native tools are host errors and are
never replaced by a Python verifier.
