# Documentation index

This index covers the original 100-case benchmark. The complete release contains 124 test points; see [Tier 3+](../Tier%203+/README.md) for the additional 24 provisional fixtures and [release notes](RELEASE_NOTES.md) for composition.

## Start here

- [Architecture and API](01_repository_architecture_and_api.md): Arthur runtime, HTTP transport, artifacts, signing, and replay audit.
- [Manual evaluation](06_manual_agent_run.md): preparing a public workspace, launching Arthur, and closing/auditing a run.
- [External model and harness integration](07_harness_integration.md): connect arbitrary CLIs, SDK programs, executables, and agent frameworks.
- [Current tier and case overview](04_benchmark_tiers_and_testpoints.md).

## Task specifications

| Catalog | Runtime ID | Cases | Participant specification |
|---|---|---:|---|
| T1.1 | `t1.new_maxflow_min_cut` | 6 | [spec](../tasks/tier1_np/new_maxflow_min_cut/TASK_SPECIFICATION.md) |
| T1.2 | `t1.new_weighted_partial_maxsat` | 6 | [spec](../tasks/tier1_np/new_weighted_partial_maxsat/TASK_SPECIFICATION.md) |
| T1.3 | `t1.new_structured_set_cover` | 6 | [spec](../tasks/tier1_np/new_structured_set_cover/TASK_SPECIFICATION.md) |
| T1.4 | `t1.new_structured_closest_vector` | 6 | [spec](../tasks/tier1_np/new_structured_closest_vector/TASK_SPECIFICATION.md) |
| T1.5 | `t1.new_list_graph_homomorphism` | 6 | [spec](../tasks/tier1_np/new_list_graph_homomorphism/TASK_SPECIFICATION.md) |
| T1.6 | `t1.new_rooted_group_steiner_tree` | 6 | [spec](../tasks/tier1_np/new_rooted_group_steiner_tree/TASK_SPECIFICATION.md) |
| T2.1 | `t2.new_graph_non_isomorphism` | 7 | [spec](../tasks/tier2_interactive/new_graph_non_isomorphism/TASK_SPECIFICATION.md) |
| T2.2 | `t2.new_boolean_hypercube_sumcheck` | 7 | [spec](../tasks/tier2_interactive/new_boolean_hypercube_sumcheck/TASK_SPECIFICATION.md) |
| T2.3 | `t2.new_gkr_layered_circuit` | 7 | [spec](../tasks/tier2_interactive/new_gkr_layered_circuit/TASK_SPECIFICATION.md) |
| T2.4 | `t2.image_size_lower_bound` | 6 | [spec](../tasks/tier2_interactive/image_size_lower_bound/TASK_SPECIFICATION.md) |
| T2.5 | `t2.new_shamir_tqbf` | 6 | [spec](../tasks/tier2_interactive/new_shamir_tqbf/TASK_SPECIFICATION.md) |
| T2.6 | `t2.new_hamiltonicity_bind_open` | 7 | [spec](../tasks/tier2_interactive/new_hamiltonicity_bind_open/TASK_SPECIFICATION.md) |
| T3.1 | `t3.machine_checked_mathematics` | 8 | [spec](../tasks/tier3_applied/machine_checked_mathematics/TASK_SPECIFICATION.md) |
| T3.2 | `t3.dafny_verified_programs` | 8 | [spec](../tasks/tier3_applied/dafny_verified_programs/TASK_SPECIFICATION.md) |
| T3.3 | `t3.drat_bounded_hardware_safety` | 8 | [spec](../tasks/tier3_applied/drat_bounded_hardware_safety/TASK_SPECIFICATION.md) |

The machine-readable source of truth for the inventory is [`catalog/benchmark_catalog.yaml`](../catalog/benchmark_catalog.yaml). Evaluation outputs should be stored outside the source tree and must never be mixed into task specifications.
