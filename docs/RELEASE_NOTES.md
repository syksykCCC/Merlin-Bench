# Release composition

This source release contains 124 test points: the original 100-case inventory
and a separate provisional 24-case Tier 3+ extension. Existing base runtime IDs,
task versions, parameter YAML, and acceptance relations are preserved.

## Source reconciliation

The base retains the original benchmark and supplementary source distribution.
The supplementary version supplies the public release layout:
shared task implementation helpers, Merlin-Bench naming, portable native-tool
discovery, and 600-second native-checker limits subject to the same global budget.
Obsolete calibration scripts, paper sources, and historical experiment assets
are not part of the dataset release.

The additional cases are the eight frozen Lean targets and the eight Dafny plus
eight DRAT targets selected in the extension material. Their public instance and
protocol bytes were checked against the frozen fixture manifest. Only those
public payloads and the assets embedded in them are included. Historical
selection reports, run identities, scores, references, guides, and trajectories
are omitted. Original candidate IDs are retained as dataset provenance.

## Evaluation compatibility

The original `merlin-bench` CLI exposes 15 tasks and 100 cases. Tier 3+ is selected
by unique fixture ID using `scripts/prepare_tier3_plus.py`. It shares the same
workspace and external harness contract. The extension adapter replaces instance
generation with exact fixture loading; it does not replace native proof checking.

Lean extension targets use `t3.machine_checked_mathematics_long_horizon` version
`0.2.0`. Its native `c09`/`c10` slots are retained for compatibility, with fixture
IDs identifying the eight distinct targets. Only task identity validation is
specialized; proof restrictions, Lean kernel checking, and axiom auditing use
the base native verifier. Dafny and DRAT retain their native IDs and versions.

This dataset provides protocol-level scoring. It does not reconstruct historical
model-specific orchestration, study phases, or behavioral reviews. An evaluator
must define and enforce its own model/tool access policy. Tier 3+ was selected
during development and remains provisional; do not present its scores as an
independent held-out confirmation of the base benchmark.
