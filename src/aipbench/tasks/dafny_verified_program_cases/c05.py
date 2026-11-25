"""C05: validate a dependency topological order."""

from __future__ import annotations

from collections.abc import Mapping

from aipbench.tasks.dafny_verified_program_cases.common import (
    DafnyCaseBlueprint,
    DeterministicStream,
    dafny_int_seq,
)

CHALLENGE = """module Challenge {
  datatype Edge = Edge(source: int, target: int)

  predicate NodesInRange(order: seq<int>, nodeCount: int) {
    |order| == nodeCount &&
    (forall i :: 0 <= i < |order| ==> 0 <= order[i] < nodeCount)
  }

  predicate NoDuplicates(order: seq<int>) {
    forall i, j :: 0 <= i < j < |order| ==> order[i] != order[j]
  }

  function Position(order: seq<int>, node: int): int
    decreases |order|
  {
    if |order| == 0 then -1
    else if order[0] == node then 0
    else
      var suffix := Position(order[1..], node);
      if suffix == -1 then -1 else suffix + 1
  }

  predicate IsTopological(order: seq<int>, edges: seq<Edge>, nodeCount: int) {
    NodesInRange(order, nodeCount) && NoDuplicates(order) &&
    (forall e :: e in edges ==>
      0 <= e.source < nodeCount && 0 <= e.target < nodeCount &&
      Position(order, e.source) < Position(order, e.target))
  }

  trait {:termination false} Candidate {
    method ValidateOrder(order: seq<int>, edges: seq<Edge>, nodeCount: int)
        returns (valid: bool)
      requires NodesInRange(order, nodeCount)
      requires NoDuplicates(order)
      requires forall e :: e in edges ==>
        0 <= e.source < nodeCount && 0 <= e.target < nodeCount
      ensures valid == IsTopological(order, edges, nodeCount)
  }
}
"""

REFERENCE = """module Solution {
  import C = Challenge

  class Candidate extends C.Candidate {
    constructor() {}

    method ValidateOrder(order: seq<int>, edges: seq<C.Edge>, nodeCount: int)
        returns (valid: bool)
      requires C.NodesInRange(order, nodeCount)
      requires C.NoDuplicates(order)
      requires forall e :: e in edges ==>
        0 <= e.source < nodeCount && 0 <= e.target < nodeCount
      ensures valid == C.IsTopological(order, edges, nodeCount)
    {
      var i := 0;
      while i < |edges|
        invariant 0 <= i <= |edges|
        invariant forall j :: 0 <= j < i ==>
          C.Position(order, edges[j].source) < C.Position(order, edges[j].target)
        decreases |edges| - i
      {
        var edge := edges[i];
        if C.Position(order, edge.source) >= C.Position(order, edge.target) {
          valid := false;
          return;
        }
        i := i + 1;
      }
      valid := true;
    }
  }
}
"""


def build(stream: DeterministicStream, parameters: Mapping[str, int]) -> DafnyCaseBlueprint:
    if parameters:
        raise ValueError("c05 accepts no case parameters")
    count = 10
    order = list(range(count))
    edges: list[tuple[int, int]] = []
    for target in range(1, count):
        edges.append((stream.randbelow(target), target))
        if target > 2 and stream.randbelow(2):
            edges.append((stream.randbelow(target), target))
    edge_text = "[" + ", ".join(f"C.Edge({u}, {v})" for u, v in edges) + "]"
    harness = f"""module ArthurHarness {{
  import S = Solution
  import C = Challenge
  method Main() {{
    var implementation: C.Candidate := new S.Candidate();
    var valid := implementation.ValidateOrder(
      {dafny_int_seq(order)}, {edge_text}, {count});
    expect valid;
    print "AIPBENCH_DAFNY_OK:c05\\n";
  }}
}}
"""
    return DafnyCaseBlueprint(
        title="Dependency-order validation",
        challenge_source=CHALLENGE,
        harness_source=harness,
        reference_solution=REFERENCE,
        public_features={"api": "Candidate.ValidateOrder", "sample_nodes": count},
    )
