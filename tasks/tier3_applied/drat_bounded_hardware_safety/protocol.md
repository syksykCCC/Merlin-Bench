# Protocol

1. Merlin reads the public AIGER circuit and DIMACS bounded miter.
2. Merlin may use any SAT solver capable of emitting a standard DRAT proof.
3. Merlin uploads exactly one `.drat` artifact and submits sequence `0`, kind
   `hardware.drat`, with the exact public instance digest.
4. Arthur validates the digest and artifact envelope, then invokes the pinned
   native `drat-trim` checker on the exact public DIMACS bytes.
5. Arthur accepts only when `drat-trim` reports a verified derivation of the
   empty clause.

CaDiCaL is used by maintainers to construct reference proofs, but it is outside
Arthur's trusted acceptance boundary.  AIGER and DIMACS make the compiled
bounded problem independently inspectable.
