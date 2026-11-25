# Tier-1 overview

Tier-1 has six deterministic proof-carrying tasks and 36 cases. Merlin submits one complete witness; Arthur checks it with exact arithmetic and no protocol randomness. All tasks use a 600-second wall-clock budget.

| Catalog | Runtime ID | Cases | Submitted evidence |
|---|---|---:|---|
| T1.1 | `t1.new_maxflow_min_cut` | 6 | edge flows, value, source-side cut |
| T1.2 | `t1.new_weighted_partial_maxsat` | 6 | complete Boolean assignment |
| T1.3 | `t1.new_structured_set_cover` | 6 | selected public set IDs |
| T1.4 | `t1.new_structured_closest_vector` | 6 | bounded integer coefficient vector |
| T1.5 | `t1.new_list_graph_homomorphism` | 6 | complete source-to-target mapping |
| T1.6 | `t1.new_rooted_group_steiner_tree` | 6 | selected public edge IDs |

