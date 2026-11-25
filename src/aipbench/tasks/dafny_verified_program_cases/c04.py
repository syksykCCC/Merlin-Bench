"""C04: earliest schedule for a predecessor-ordered task graph."""

from __future__ import annotations

from collections.abc import Mapping

from aipbench.tasks.dafny_verified_program_cases.common import (
    DafnyCaseBlueprint,
    DeterministicStream,
    dafny_int_seq,
)

CHALLENGE = """module Challenge {
  predicate PredecessorsWellFormed(durations: seq<int>, predecessor: seq<int>) {
    |durations| == |predecessor| &&
    (forall i :: 0 <= i < |durations| ==> 0 < durations[i]) &&
    (forall i :: 0 <= i < |predecessor| ==> -1 <= predecessor[i] < i)
  }

  predicate EarliestSchedule(
      durations: seq<int>, predecessor: seq<int>, start: seq<int>) {
    PredecessorsWellFormed(durations, predecessor) &&
    |start| == |durations| &&
    (forall i :: 0 <= i < |start| ==>
      start[i] == (if predecessor[i] == -1 then 0
                   else start[predecessor[i]] + durations[predecessor[i]]))
  }

  trait {:termination false} Candidate {
    method Schedule(durations: seq<int>, predecessor: seq<int>)
        returns (start: seq<int>)
      requires PredecessorsWellFormed(durations, predecessor)
      ensures EarliestSchedule(durations, predecessor, start)
  }
}
"""

REFERENCE = """module Solution {
  import C = Challenge

  class Candidate extends C.Candidate {
    constructor() {}

    method Schedule(durations: seq<int>, predecessor: seq<int>)
        returns (start: seq<int>)
      requires C.PredecessorsWellFormed(durations, predecessor)
      ensures C.EarliestSchedule(durations, predecessor, start)
    {
      start := [];
      var i := 0;
      while i < |durations|
        invariant 0 <= i <= |durations|
        invariant |start| == i
        invariant forall j :: 0 <= j < i ==>
          start[j] == (if predecessor[j] == -1 then 0
                       else start[predecessor[j]] + durations[predecessor[j]])
        decreases |durations| - i
      {
        if predecessor[i] == -1 {
          start := start + [0];
        } else {
          var parent := predecessor[i];
          assert 0 <= parent < i;
          start := start + [start[parent] + durations[parent]];
        }
        i := i + 1;
      }
    }
  }
}
"""


def build(stream: DeterministicStream, parameters: Mapping[str, int]) -> DafnyCaseBlueprint:
    if parameters:
        raise ValueError("c04 accepts no case parameters")
    durations = [stream.randint(1, 9) for _ in range(14)]
    predecessor = [-1]
    for index in range(1, len(durations)):
        predecessor.append(-1 if stream.randbelow(4) == 0 else stream.randbelow(index))
    start: list[int] = []
    for _index, parent in enumerate(predecessor):
        start.append(0 if parent == -1 else start[parent] + durations[parent])
    harness = f"""module ArthurHarness {{
  import C = Challenge
  import S = Solution
  method Main() {{
    var implementation: C.Candidate := new S.Candidate();
    var start := implementation.Schedule(
      {dafny_int_seq(durations)}, {dafny_int_seq(predecessor)});
    expect start == {dafny_int_seq(start)};
    print "AIPBENCH_DAFNY_OK:c04\\n";
  }}
}}
"""
    return DafnyCaseBlueprint(
        title="Precedence-constrained earliest schedule",
        challenge_source=CHALLENGE,
        harness_source=harness,
        reference_solution=REFERENCE,
        public_features={"api": "Candidate.Schedule", "sample_tasks": len(durations)},
    )
