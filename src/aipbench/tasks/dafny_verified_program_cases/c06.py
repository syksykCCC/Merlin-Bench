"""C06: audited batch firewall evaluation through a contract-bearing trait."""

from __future__ import annotations

from collections.abc import Mapping

from aipbench.tasks.dafny_verified_program_cases.common import (
    DafnyCaseBlueprint,
    DeterministicStream,
    dafny_bool_seq,
    dafny_int_seq,
)

CHALLENGE = """module Challenge {
  datatype Decision = Decision(index: int, allow: bool)

  predicate WellFormed(packets: seq<seq<bool>>, actions: seq<bool>) {
    forall p :: 0 <= p < |packets| ==> |packets[p]| == |actions|
  }

  predicate FirstMatch(
      matches: seq<bool>, actions: seq<bool>, decision: Decision) {
    |matches| == |actions| && -1 <= decision.index < |matches| &&
    (decision.index == -1 ==>
      !decision.allow && forall i :: 0 <= i < |matches| ==> !matches[i]) &&
    (0 <= decision.index ==>
      matches[decision.index] &&
      (forall i :: 0 <= i < decision.index ==> !matches[i]) &&
      decision.allow == actions[decision.index])
  }

  ghost function CountPrefix(
      decisions: seq<Decision>, rule: nat, length: nat): nat
    requires length <= |decisions|
    decreases length
  {
    if length == 0 then 0
    else (CountPrefix(decisions, rule, length - 1) +
      (if decisions[length - 1].index == rule then 1 else 0))
  }

  ghost predicate AuditedBatchPost(
      packets: seq<seq<bool>>, actions: seq<bool>,
      decisions: seq<Decision>, counts: seq<nat>) {
    WellFormed(packets, actions) &&
    |decisions| == |packets| && |counts| == |actions| &&
    (forall p :: 0 <= p < |packets| ==>
      FirstMatch(packets[p], actions, decisions[p])) &&
    (forall rule :: 0 <= rule < |actions| ==>
      counts[rule] == CountPrefix(decisions, rule, |decisions|))
  }

  trait {:termination false} Candidate {
    method EvaluateBatch(packets: seq<seq<bool>>, actions: seq<bool>)
        returns (decisions: seq<Decision>, counts: seq<nat>)
      requires WellFormed(packets, actions)
      ensures AuditedBatchPost(packets, actions, decisions, counts)
  }
}
"""

REFERENCE = """module Solution {
  import C = Challenge

  class Candidate extends C.Candidate {
    constructor() {}

    method EvaluateOne(matches: seq<bool>, actions: seq<bool>)
        returns (decision: C.Decision)
      requires |matches| == |actions|
      ensures C.FirstMatch(matches, actions, decision)
    {
      var i := 0;
      while i < |matches| && !matches[i]
        invariant 0 <= i <= |matches|
        invariant forall j :: 0 <= j < i ==> !matches[j]
        decreases |matches| - i
      {
        i := i + 1;
      }
      if i == |matches| {
        decision := C.Decision(-1, false);
      } else {
        decision := C.Decision(i, actions[i]);
      }
    }

    method EvaluateBatch(packets: seq<seq<bool>>, actions: seq<bool>)
        returns (decisions: seq<C.Decision>, counts: seq<nat>)
      requires C.WellFormed(packets, actions)
      ensures C.AuditedBatchPost(packets, actions, decisions, counts)
    {
      decisions := [];
      var p := 0;
      while p < |packets|
        invariant 0 <= p <= |packets|
        invariant |decisions| == p
        invariant forall k :: 0 <= k < p ==>
          C.FirstMatch(packets[k], actions, decisions[k])
        decreases |packets| - p
      {
        var decision := EvaluateOne(packets[p], actions);
        decisions := decisions + [decision];
        p := p + 1;
      }

      counts := [];
      var rule := 0;
      while rule < |actions|
        invariant 0 <= rule <= |actions|
        invariant |counts| == rule
        invariant forall r :: 0 <= r < rule ==>
          counts[r] == C.CountPrefix(decisions, r, |decisions|)
        decreases |actions| - rule
      {
        var seen: nat := 0;
        var q := 0;
        while q < |decisions|
          invariant 0 <= q <= |decisions|
          invariant seen == C.CountPrefix(decisions, rule, q)
          decreases |decisions| - q
        {
          if decisions[q].index == rule {
            seen := seen + 1;
          }
          q := q + 1;
        }
        counts := counts + [seen];
        rule := rule + 1;
      }
    }
  }
}
"""


def build(stream: DeterministicStream, parameters: Mapping[str, int]) -> DafnyCaseBlueprint:
    if parameters:
        raise ValueError("c06 accepts no case parameters")
    actions = [stream.randbelow(2) == 1 for _ in range(16)]
    packets: list[list[bool]] = []
    expected: list[tuple[int, bool]] = []
    counts = [0 for _ in actions]
    for packet_index in range(11):
        row = [stream.randbelow(7) == 0 for _ in actions]
        if packet_index == 0:
            row = [False for _ in actions]
        elif not any(row):
            row[stream.randbelow(len(row))] = True
        packets.append(row)
        if any(row):
            index = row.index(True)
            counts[index] += 1
            expected.append((index, actions[index]))
        else:
            expected.append((-1, False))
    packet_text = "[" + ", ".join(dafny_bool_seq(row) for row in packets) + "]"
    expected_text = (
        "["
        + ", ".join(
            f"C.Decision({index}, {'true' if allow else 'false'})" for index, allow in expected
        )
        + "]"
    )
    harness = f"""module ArthurHarness {{
  import C = Challenge
  import S = Solution
  method Main() {{
    var implementation: C.Candidate := new S.Candidate();
    var decisions, counts := implementation.EvaluateBatch(
      {packet_text}, {dafny_bool_seq(actions)});
    expect decisions == {expected_text};
    expect counts == {dafny_int_seq(counts)};
    print "AIPBENCH_DAFNY_OK:c06\\n";
  }}
}}
"""
    return DafnyCaseBlueprint(
        title="Audited priority firewall batch evaluation",
        challenge_source=CHALLENGE,
        harness_source=harness,
        reference_solution=REFERENCE,
        public_features={"api": "Candidate.EvaluateBatch", "sample_packets": len(packets)},
    )
