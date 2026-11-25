# Merlin-Bench benchmark card

## Scope

The release contains 124 test points: 100 base cases across 15 tasks, plus 24 provisional fixed cases in [Tier 3+](Tier%203+/README.md). Every task has a 600-second wall-clock limit, binary official scoring, signed result artifacts, and strict replay audit.

| Tier | Cases | Evidence style |
|---|---:|---|
| Tier-1 | 36 | deterministic answer plus polynomial-time certificate |
| Tier-2 | 40 | interactive transcript bound to Arthur's fresh challenge |
| Tier-3 | 24 | source/proof artifact checked by Lean, Dafny/Z3, or drat-trim |
| Tier-3+ | 24 | provisional fixed native-tool instances (8 per domain) |

## Base tasks

| ID | Cases | Merlin evidence | Arthur check |
|---|---:|---|---|
| `t1.new_maxflow_min_cut` | 6 | flow and cut | exact primal/dual equality |
| `t1.new_weighted_partial_maxsat` | 6 | complete assignment | hard clauses and weighted threshold |
| `t1.new_structured_set_cover` | 6 | selected set IDs | coverage and budget |
| `t1.new_structured_closest_vector` | 6 | integer coefficients | exact rational squared distance |
| `t1.new_list_graph_homomorphism` | 6 | complete mapping | lists and edge preservation |
| `t1.new_rooted_group_steiner_tree` | 6 | selected edge IDs | root connectivity, groups, budget |
| `t2.new_graph_non_isomorphism` | 7 | hidden-source responses | private-coin transcript replay |
| `t2.new_boolean_hypercube_sumcheck` | 7 | Sum-Check messages | public-coin algebraic checks |
| `t2.new_gkr_layered_circuit` | 7 | layered GKR messages | public-coin circuit reduction |
| `t2.image_size_lower_bound` | 6 | affine-hash preimages | image-size lower-bound protocol |
| `t2.new_shamir_tqbf` | 6 | arithmetized QBF messages | Shamir-style round checks |
| `t2.new_hamiltonicity_bind_open` | 7 | commitments and openings | bind--challenge--open verification |
| `t3.machine_checked_mathematics` | 8 | `Solution.lean` | Lean 4.19 kernel and axiom audit |
| `t3.dafny_verified_programs` | 8 | `Solution.dfy` | Dafny 4.11/Z3 plus fixed execution harness |
| `t3.drat_bounded_hardware_safety` | 8 | standard DRAT proof | drat-trim against public bounded CNF |

## Evaluation protocol

- One fresh task/case/seed run (base), or fixed-fixture run (Tier 3+), per model attempt; no retry is merged into a score.
- The model receives only the generated public workspace.
- Resource-limit, timeout, rejection, and compliant no-submission outcomes are scored failures unless the evaluation record explicitly marks the attempt as excluded or infrastructure-invalid.
- The signed terminal plus strict audit-derived `official_result` is authoritative; diagnostic labels and participant prose do not change it.
- Results and trajectories are external evaluation artifacts and are intentionally not bundled with this source release.

## Limitations

- The fixed case inventory does not establish statistical generalization across seeds or model runs.
- Tier-3 claims bounded hardware safety, not unbounded model checking.
- Workspace separation is not an operating-system sandbox.
- Comparisons must use the exact runtime IDs and task versions in the catalog.

Tier 3+ targets were selected during development and should be reported separately. Use unique fixture IDs and hashes, not reused native slots, to identify extension cases.
