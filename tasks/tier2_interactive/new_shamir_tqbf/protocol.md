# Protocol summary

1. Submit `tqbf.claim` with the canonical field encoding of one.
2. Read the first public round specification.
3. For every round, submit exactly `degree_bound + 1` increasing-power
   coefficients in `tqbf.polynomial`.
4. Arthur checks the current anchor before sampling and returning a fresh field
   point and the next round specification.
5. After the final round Arthur directly evaluates the public arithmetized
   circuit at the accumulated point.

Any malformed or inconsistent event terminates the one-shot run.
