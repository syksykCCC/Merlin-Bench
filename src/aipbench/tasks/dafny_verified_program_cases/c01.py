"""C01: stable partition implemented with explicit loop invariants."""

from __future__ import annotations

from collections.abc import Mapping

from aipbench.tasks.dafny_verified_program_cases.common import (
    DafnyCaseBlueprint,
    DeterministicStream,
    dafny_int_seq,
)

CHALLENGE = """module Challenge {
  function Negatives(input: seq<int>): seq<int>
    decreases |input|
  {
    if |input| == 0 then []
    else (if input[0] < 0 then [input[0]] else []) + Negatives(input[1..])
  }

  function NonNegatives(input: seq<int>): seq<int>
    decreases |input|
  {
    if |input| == 0 then []
    else (if input[0] >= 0 then [input[0]] else []) + NonNegatives(input[1..])
  }

  predicate StablePartitionPost(input: seq<int>, output: seq<int>) {
    output == Negatives(input) + NonNegatives(input)
  }

  trait {:termination false} Candidate {
    method StablePartition(input: seq<int>) returns (output: seq<int>)
      ensures StablePartitionPost(input, output)
  }
}
"""

REFERENCE = """module Solution {
  import C = Challenge

  class Candidate extends C.Candidate {
    constructor() {}

    method StablePartition(input: seq<int>) returns (output: seq<int>)
      ensures C.StablePartitionPost(input, output)
    {
      output := C.Negatives(input) + C.NonNegatives(input);
    }
  }
}
"""


def build(stream: DeterministicStream, parameters: Mapping[str, int]) -> DafnyCaseBlueprint:
    if parameters:
        raise ValueError("c01 accepts no case parameters")
    sample = [stream.randint(-20, 20) for _ in range(12)]
    expected = [value for value in sample if value < 0] + [value for value in sample if value >= 0]
    harness = f"""module ArthurHarness {{
  import C = Challenge
  import S = Solution
  method Main() {{
    var implementation: C.Candidate := new S.Candidate();
    var result := implementation.StablePartition({dafny_int_seq(sample)});
    expect result == {dafny_int_seq(expected)};
    print "AIPBENCH_DAFNY_OK:c01\\n";
  }}
}}
"""
    return DafnyCaseBlueprint(
        title="Stable partition preservation",
        challenge_source=CHALLENGE,
        harness_source=harness,
        reference_solution=REFERENCE,
        public_features={"api": "Candidate.StablePartition", "sample_length": len(sample)},
    )
