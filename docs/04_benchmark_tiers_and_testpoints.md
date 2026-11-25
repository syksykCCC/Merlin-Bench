# Current benchmark tiers and test points

The public suite contains 100 cases. Catalog IDs are presentation ordinals; `runtime_id` is the executable registry key.

| Tier | Tasks | Cases | Verification boundary |
|---|---:|---:|---|
| T1 | 6 | 36 | deterministic certificate verifier |
| T2 | 6 | 40 | Arthur challenge and transcript-bound interactive verifier |
| T3 | 3 | 24 | native Lean, Dafny/Z3, or DRAT checker |

All current manifests specify a 600-second total wall-clock budget. Exact task and case descriptions are in [`catalog/benchmark_catalog.yaml`](../catalog/benchmark_catalog.yaml) and the participant specifications under [`tasks/`](../tasks/).

## Tier-1

Tier-1 covers Max-Flow/Min-Cut, Weighted Partial MaxSAT, Structured Set Cover, Structured Closest Vector, List Graph Homomorphism, and Rooted Group Steiner Tree. Each task has six opaque cases and one deterministic proof-carrying acceptance relation. See [Tier-1 overview](10_tier1_task_overview.md).

## Tier-2

Tier-2 covers Graph Non-Isomorphism, Boolean-Hypercube Sum-Check, GKR layered circuits, Image-Size Lower Bound, Shamir-style TQBF, and Hamiltonicity bind--challenge--open. See [Tier-2 overview](11_tier2_task_overview.md).

## Tier-3

Tier-3 demonstrates generality across formal mathematics, verified software, and bounded hardware safety. Merlin submits standard `.lean`, `.dfy`, or `.drat` evidence and Arthur invokes the native checker. See [Tier-3 overview](12_tier3_task_overview.md).

## Evaluation artifacts

The catalog contains task definitions and frozen case parameters, not model scores. Store run evidence, trajectories, and analysis outputs outside the source release and identify every row by runtime ID, task version, case ID, seed, model, harness, and audit status.

## Provisional extension

The counts above describe the original 100 cases. This release additionally includes [Tier 3+](../Tier%203+/README.md), containing 24 fixed cases, for a total of 124 test points.
