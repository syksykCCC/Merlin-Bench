# Tier-2 overview

Tier-2 has six interactive tasks and 40 cases. Merlin must bind a claim or commitment before consuming Arthur's fresh challenge. All tasks use a 600-second wall-clock budget and strict transcript replay.

| Catalog | Runtime ID | Cases | Protocol |
|---|---|---:|---|
| T2.1 | `t2.new_graph_non_isomorphism` | 7 | private-coin hidden-source classification |
| T2.2 | `t2.new_boolean_hypercube_sumcheck` | 7 | public-coin LFKN Sum-Check |
| T2.3 | `t2.new_gkr_layered_circuit` | 7 | public-coin layered GKR |
| T2.4 | `t2.image_size_lower_bound` | 6 | affine hashing and preimage openings |
| T2.5 | `t2.new_shamir_tqbf` | 6 | arithmetized TQBF rounds |
| T2.6 | `t2.new_hamiltonicity_bind_open` | 7 | 24-lane bind--challenge--open |

All six protocols bind Merlin's claim or commitment before Arthur derives fresh randomness. Each case uses the common 600-second wall-clock budget. Participant specifications are linked from the [documentation index](README.md).
