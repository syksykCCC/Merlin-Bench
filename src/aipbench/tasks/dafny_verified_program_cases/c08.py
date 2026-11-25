"""C08: free-list memory-pool invariant preservation."""

from __future__ import annotations

from collections.abc import Mapping

from aipbench.tasks.dafny_verified_program_cases.common import (
    DafnyCaseBlueprint,
    DeterministicStream,
)

CHALLENGE = """module Challenge {
  datatype PoolState = PoolState(
    capacity: nat, free: seq<nat>, owned: set<nat>)

  predicate NoDuplicates(values: seq<int>) {
    forall i, j :: 0 <= i < j < |values| ==> values[i] != values[j]
  }

  predicate PoolValid(state: PoolState) {
    NoDuplicates(state.free) &&
    (forall i :: 0 <= i < |state.free| ==> state.free[i] < state.capacity) &&
    (forall block :: block in state.owned ==> block < state.capacity) &&
    (forall block :: 0 <= block < state.capacity ==>
      (block in state.owned) != (block in state.free))
  }

  predicate AllocatePost(
      before: PoolState, accepted: bool, block: int, nextState: PoolState) {
    PoolValid(before) && accepted == (0 < |before.free|) &&
    (!accepted ==> nextState == before) &&
    (accepted ==>
      block == before.free[0] &&
      nextState == PoolState(
        before.capacity, before.free[1..], before.owned + {block}))
  }

  predicate ReleasePost(before: PoolState, block: nat, nextState: PoolState) {
    PoolValid(before) && block in before.owned &&
    nextState == PoolState(
      before.capacity,
      [block] + before.free,
      before.owned - {block})
  }

  trait {:termination false} Candidate {
    method Allocate(before: PoolState)
        returns (accepted: bool, block: int, nextState: PoolState)
      requires PoolValid(before)
      ensures AllocatePost(before, accepted, block, nextState)
      ensures PoolValid(nextState)

    method Release(before: PoolState, block: nat) returns (nextState: PoolState)
      requires PoolValid(before)
      requires block in before.owned
      ensures ReleasePost(before, block, nextState)
      ensures PoolValid(nextState)
  }
}
"""

REFERENCE = """module Solution {
  import C = Challenge

  class Candidate extends C.Candidate {
    constructor() {}

    method Allocate(before: C.PoolState)
        returns (accepted: bool, block: int, nextState: C.PoolState)
      requires C.PoolValid(before)
      ensures C.AllocatePost(before, accepted, block, nextState)
      ensures C.PoolValid(nextState)
    {
      if |before.free| == 0 {
        accepted := false;
        block := -1;
        nextState := before;
      } else {
        accepted := true;
        block := before.free[0];
        nextState := C.PoolState(
          before.capacity, before.free[1..], before.owned + {block});
      }
    }

    method Release(before: C.PoolState, block: nat) returns (nextState: C.PoolState)
      requires C.PoolValid(before)
      requires block in before.owned
      ensures C.ReleasePost(before, block, nextState)
      ensures C.PoolValid(nextState)
    {
      nextState := C.PoolState(
        before.capacity,
        [block] + before.free,
        before.owned - {block});
    }
  }
}
"""


def build(stream: DeterministicStream, parameters: Mapping[str, int]) -> DafnyCaseBlueprint:
    if parameters:
        raise ValueError("c08 accepts no case parameters")
    released = stream.randbelow(3) + 3
    harness = f"""module ArthurHarness {{
  import S = Solution
  import C = Challenge
  method Main() {{
    var implementation: C.Candidate := new S.Candidate();
    var p0 := C.PoolState(6, [0, 1, 2], {{3, 4, 5}});
    var ok, block, p1 := implementation.Allocate(p0);
    expect ok && block == 0 && p1.free == [1, 2];
    var p2 := implementation.Release(p1, {released});
    expect p2.free == [{released}, 1, 2];
    expect C.PoolValid(p2);
    print "AIPBENCH_DAFNY_OK:c08\\n";
  }}
}}
"""
    return DafnyCaseBlueprint(
        title="Free-list memory-pool invariant preservation",
        challenge_source=CHALLENGE,
        harness_source=harness,
        reference_solution=REFERENCE,
        public_features={"api": "Candidate.Allocate/Release", "sample_blocks": 6},
    )
