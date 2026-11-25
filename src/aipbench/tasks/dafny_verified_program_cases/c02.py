"""C02: lower-bound binary search with boundary invariants."""

from __future__ import annotations

from collections.abc import Mapping

from aipbench.tasks.dafny_verified_program_cases.common import (
    DafnyCaseBlueprint,
    DeterministicStream,
    dafny_int_seq,
)

CHALLENGE = """module Challenge {
  predicate Sorted(a: seq<int>) {
    forall i, j :: 0 <= i < j < |a| ==> a[i] <= a[j]
  }

  predicate LowerBoundPost(a: seq<int>, key: int, index: int) {
    0 <= index <= |a| &&
    (forall i :: 0 <= i < index ==> a[i] < key) &&
    (forall i :: index <= i < |a| ==> key <= a[i])
  }

  trait {:termination false} Candidate {
    method LowerBound(a: seq<int>, key: int) returns (index: int)
      requires Sorted(a)
      ensures LowerBoundPost(a, key, index)
  }
}
"""

REFERENCE = """module Solution {
  import C = Challenge

  class Candidate extends C.Candidate {
    constructor() {}

    method LowerBound(a: seq<int>, key: int) returns (index: int)
      requires C.Sorted(a)
      ensures C.LowerBoundPost(a, key, index)
    {
      var low := 0;
      var high := |a|;
      while low < high
        invariant 0 <= low <= high <= |a|
        invariant forall i :: 0 <= i < low ==> a[i] < key
        invariant forall i :: high <= i < |a| ==> key <= a[i]
        decreases high - low
      {
        var middle := low + (high - low) / 2;
        if a[middle] < key {
          low := middle + 1;
        } else {
          high := middle;
        }
      }
      index := low;
    }
  }
}
"""


def build(stream: DeterministicStream, parameters: Mapping[str, int]) -> DafnyCaseBlueprint:
    if parameters:
        raise ValueError("c02 accepts no case parameters")
    values = sorted(stream.randint(-30, 30) for _ in range(18))
    key = stream.randint(-25, 25)
    expected = next((index for index, value in enumerate(values) if value >= key), len(values))
    harness = f"""module ArthurHarness {{
  import C = Challenge
  import S = Solution
  method Main() {{
    var implementation: C.Candidate := new S.Candidate();
    var index := implementation.LowerBound({dafny_int_seq(values)}, {key});
    expect index == {expected};
    print "AIPBENCH_DAFNY_OK:c02\\n";
  }}
}}
"""
    return DafnyCaseBlueprint(
        title="Boundary-safe lower-bound search",
        challenge_source=CHALLENGE,
        harness_source=harness,
        reference_solution=REFERENCE,
        public_features={"api": "Candidate.LowerBound", "sample_length": len(values)},
    )
