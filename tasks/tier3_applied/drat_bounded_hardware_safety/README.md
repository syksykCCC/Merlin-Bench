# DRAT-Certified Bounded Hardware Safety

Each case publishes a sequential ASCII AIGER circuit, an explicit time bound,
and a standard DIMACS formula encoding `Init ∧ Trans[0..H-1] ∧ Bad[0..H]`.
The circuit families are FIFO controllers, round-robin arbiters, credit-based
routers, and simplified pipeline control.  Merlin submits a standard DRAT
proof that the bounded bad-state formula is unsatisfiable; Arthur checks the
proof with pinned `drat-trim`.

This is bounded model checking.  It does not claim an unbounded inductive proof
and does not introduce a benchmark-specific proof language.
