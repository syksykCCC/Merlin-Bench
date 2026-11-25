"""C03: capacity-constrained reservation update."""

from __future__ import annotations

from collections.abc import Mapping

from aipbench.tasks.dafny_verified_program_cases.common import (
    DafnyCaseBlueprint,
    DeterministicStream,
    dafny_int_seq,
)

CHALLENGE = """module Challenge {
  predicate WellFormed(used: seq<int>, capacity: int) {
    0 <= capacity && forall i :: 0 <= i < |used| ==> 0 <= used[i] <= capacity
  }

  predicate CanReserve(used: seq<int>, demand: int, capacity: int) {
    0 <= demand && forall i :: 0 <= i < |used| ==> used[i] + demand <= capacity
  }

  predicate ReservationPost(
      used: seq<int>, demand: int, capacity: int,
      accepted: bool, updated: seq<int>) {
    accepted == CanReserve(used, demand, capacity) &&
    |updated| == |used| &&
    (accepted ==>
      (forall i :: 0 <= i < |used| ==> updated[i] == used[i] + demand)) &&
    (!accepted ==> updated == used)
  }

  trait {:termination false} Candidate {
    method Reserve(used: seq<int>, demand: int, capacity: int)
        returns (accepted: bool, updated: seq<int>)
      requires WellFormed(used, capacity)
      requires 0 <= demand
      ensures ReservationPost(used, demand, capacity, accepted, updated)
  }
}
"""

REFERENCE = """module Solution {
  import C = Challenge

  class Candidate extends C.Candidate {
    constructor() {}

    method Reserve(used: seq<int>, demand: int, capacity: int)
        returns (accepted: bool, updated: seq<int>)
      requires C.WellFormed(used, capacity)
      requires 0 <= demand
      ensures C.ReservationPost(used, demand, capacity, accepted, updated)
    {
      accepted := true;
      var i := 0;
      while i < |used| && accepted
        invariant 0 <= i <= |used|
        invariant accepted ==> (forall j :: 0 <= j < i ==> used[j] + demand <= capacity)
        invariant !accepted ==> (exists j :: 0 <= j < i && used[j] + demand > capacity)
        decreases |used| - i
      {
        if used[i] + demand > capacity {
          accepted := false;
        }
        i := i + 1;
      }
      if !accepted {
        updated := used;
        return;
      }
      assert i == |used|;
      updated := [];
      i := 0;
      while i < |used|
        invariant 0 <= i <= |used|
        invariant |updated| == i
        invariant forall j :: 0 <= j < i ==> updated[j] == used[j] + demand
        decreases |used| - i
      {
        updated := updated + [used[i] + demand];
        i := i + 1;
      }
    }
  }
}
"""


def build(stream: DeterministicStream, parameters: Mapping[str, int]) -> DafnyCaseBlueprint:
    if parameters:
        raise ValueError("c03 accepts no case parameters")
    capacity = stream.randint(12, 24)
    used = [stream.randint(0, capacity - 3) for _ in range(10)]
    demand = stream.randint(1, 5)
    accepted = all(value + demand <= capacity for value in used)
    expected = [value + demand for value in used] if accepted else used
    accepted_text = "true" if accepted else "false"
    harness = f"""module ArthurHarness {{
  import C = Challenge
  import S = Solution
  method Main() {{
    var implementation: C.Candidate := new S.Candidate();
    var accepted, updated := implementation.Reserve(
      {dafny_int_seq(used)}, {demand}, {capacity});
    expect accepted == {accepted_text};
    expect updated == {dafny_int_seq(expected)};
    print "AIPBENCH_DAFNY_OK:c03\\n";
  }}
}}
"""
    return DafnyCaseBlueprint(
        title="Capacity-constrained reservation update",
        challenge_source=CHALLENGE,
        harness_source=harness,
        reference_solution=REFERENCE,
        public_features={"api": "Candidate.Reserve", "sample_slots": len(used)},
    )
