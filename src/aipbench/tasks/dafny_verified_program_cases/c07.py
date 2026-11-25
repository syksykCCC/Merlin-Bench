"""C07: reference-counted handle-table invariant preservation."""

from __future__ import annotations

from collections.abc import Mapping

from aipbench.tasks.dafny_verified_program_cases.common import (
    DafnyCaseBlueprint,
    DeterministicStream,
    dafny_bool_seq,
    dafny_int_seq,
)

CHALLENGE = """module Challenge {
  datatype RefState = RefState(refs: seq<seq<bool>>, counts: seq<nat>)

  predicate Rectangular(refs: seq<seq<bool>>, width: nat) {
    forall client :: 0 <= client < |refs| ==> |refs[client]| == width
  }

  ghost function CountPrefix(
      refs: seq<seq<bool>>, resource: nat, length: nat): nat
    requires length <= |refs|
    requires forall client :: 0 <= client < length ==>
      resource < |refs[client]|
    decreases length
  {
    if length == 0 then 0
    else (CountPrefix(refs, resource, length - 1) +
      (if refs[length - 1][resource] then 1 else 0))
  }

  ghost predicate RefStateValid(state: RefState) {
    Rectangular(state.refs, |state.counts|) &&
    forall resource :: 0 <= resource < |state.counts| ==>
      state.counts[resource] ==
        CountPrefix(state.refs, resource, |state.refs|)
  }

  ghost predicate AcquirePost(
      before: RefState, client: nat, resource: nat,
      accepted: bool, after: RefState) {
    RefStateValid(before) &&
    client < |before.refs| && resource < |before.counts| &&
    accepted == !before.refs[client][resource] &&
    (!accepted ==> after == before) &&
    (accepted ==>
      after.refs == before.refs[
        client := before.refs[client][resource := true]])
  }

  ghost predicate ReleasePost(
      before: RefState, client: nat, resource: nat,
      accepted: bool, after: RefState) {
    RefStateValid(before) &&
    client < |before.refs| && resource < |before.counts| &&
    accepted == before.refs[client][resource] &&
    (!accepted ==> after == before) &&
    (accepted ==>
      after.refs == before.refs[
        client := before.refs[client][resource := false]])
  }

  trait {:termination false} Candidate {
    method Initialize(refs: seq<seq<bool>>, width: nat)
        returns (after: RefState)
      requires Rectangular(refs, width)
      ensures after.refs == refs
      ensures RefStateValid(after)

    method Acquire(before: RefState, client: nat, resource: nat)
        returns (accepted: bool, after: RefState)
      requires RefStateValid(before)
      requires client < |before.refs|
      requires resource < |before.counts|
      ensures AcquirePost(before, client, resource, accepted, after)
      ensures RefStateValid(after)

    method Release(before: RefState, client: nat, resource: nat)
        returns (accepted: bool, after: RefState)
      requires RefStateValid(before)
      requires client < |before.refs|
      requires resource < |before.counts|
      ensures ReleasePost(before, client, resource, accepted, after)
      ensures RefStateValid(after)
  }
}
"""

REFERENCE = """module Solution {
  import C = Challenge

  class Candidate extends C.Candidate {
    constructor() {}

    method Recount(refs: seq<seq<bool>>, width: nat)
        returns (counts: seq<nat>)
      requires C.Rectangular(refs, width)
      ensures |counts| == width
      ensures forall resource :: 0 <= resource < width ==>
        counts[resource] == C.CountPrefix(refs, resource, |refs|)
    {
      counts := [];
      var resource := 0;
      while resource < width
        invariant 0 <= resource <= width
        invariant |counts| == resource
        invariant forall r :: 0 <= r < resource ==>
          counts[r] == C.CountPrefix(refs, r, |refs|)
        decreases width - resource
      {
        var seen: nat := 0;
        var client := 0;
        while client < |refs|
          invariant 0 <= client <= |refs|
          invariant seen == C.CountPrefix(refs, resource, client)
          decreases |refs| - client
        {
          if refs[client][resource] {
            seen := seen + 1;
          }
          client := client + 1;
        }
        counts := counts + [seen];
        resource := resource + 1;
      }
    }

    method Initialize(refs: seq<seq<bool>>, width: nat)
        returns (after: C.RefState)
      requires C.Rectangular(refs, width)
      ensures after.refs == refs
      ensures C.RefStateValid(after)
    {
      var counts := Recount(refs, width);
      after := C.RefState(refs, counts);
    }

    method Acquire(before: C.RefState, client: nat, resource: nat)
        returns (accepted: bool, after: C.RefState)
      requires C.RefStateValid(before)
      requires client < |before.refs|
      requires resource < |before.counts|
      ensures C.AcquirePost(before, client, resource, accepted, after)
      ensures C.RefStateValid(after)
    {
      if before.refs[client][resource] {
        accepted := false;
        after := before;
      } else {
        accepted := true;
        var refs := before.refs[
          client := before.refs[client][resource := true]];
        assert C.Rectangular(refs, |before.counts|);
        var counts := Recount(refs, |before.counts|);
        after := C.RefState(refs, counts);
      }
    }

    method Release(before: C.RefState, client: nat, resource: nat)
        returns (accepted: bool, after: C.RefState)
      requires C.RefStateValid(before)
      requires client < |before.refs|
      requires resource < |before.counts|
      ensures C.ReleasePost(before, client, resource, accepted, after)
      ensures C.RefStateValid(after)
    {
      if !before.refs[client][resource] {
        accepted := false;
        after := before;
      } else {
        accepted := true;
        var refs := before.refs[
          client := before.refs[client][resource := false]];
        assert C.Rectangular(refs, |before.counts|);
        var counts := Recount(refs, |before.counts|);
        after := C.RefState(refs, counts);
      }
    }
  }
}
"""


def _matrix_text(rows: list[list[bool]]) -> str:
    return "[" + ", ".join(dafny_bool_seq(row) for row in rows) + "]"


def build(stream: DeterministicStream, parameters: Mapping[str, int]) -> DafnyCaseBlueprint:
    if parameters:
        raise ValueError("c07 accepts no case parameters")
    clients = 8
    resources = 10
    refs = [[stream.randbelow(4) == 0 for _ in range(resources)] for _ in range(clients)]
    counts = [sum(1 for row in refs if row[resource]) for resource in range(resources)]
    acquire_client = stream.randbelow(clients)
    acquire_resource = stream.randbelow(resources)
    refs[acquire_client][acquire_resource] = False
    counts = [sum(1 for row in refs if row[resource]) for resource in range(resources)]
    after_acquire = [row[:] for row in refs]
    after_acquire[acquire_client][acquire_resource] = True
    counts_after_acquire = counts[:]
    counts_after_acquire[acquire_resource] += 1
    release_client = next(client for client in range(clients) if any(after_acquire[client]))
    release_resource = after_acquire[release_client].index(True)
    after_release = [row[:] for row in after_acquire]
    after_release[release_client][release_resource] = False
    counts_after_release = counts_after_acquire[:]
    counts_after_release[release_resource] -= 1
    harness = f"""module ArthurHarness {{
  import C = Challenge
  import S = Solution
  method Main() {{
    var implementation: C.Candidate := new S.Candidate();
    var s0 := implementation.Initialize({_matrix_text(refs)}, {resources});
    expect s0.refs == {_matrix_text(refs)};
    expect s0.counts == {dafny_int_seq(counts)};
    var ok1, s1 := implementation.Acquire(
      s0, {acquire_client}, {acquire_resource});
    expect ok1 && s1.refs == {_matrix_text(after_acquire)};
    expect s1.counts == {dafny_int_seq(counts_after_acquire)};
    var ok2, s2 := implementation.Release(
      s1, {release_client}, {release_resource});
    expect ok2 && s2.refs == {_matrix_text(after_release)};
    expect s2.counts == {dafny_int_seq(counts_after_release)};
    print "AIPBENCH_DAFNY_OK:c07\\n";
  }}
}}
"""
    return DafnyCaseBlueprint(
        title="Reference-counted handle-table invariant preservation",
        challenge_source=CHALLENGE,
        harness_source=harness,
        reference_solution=REFERENCE,
        public_features={"api": "Candidate.Acquire/Release", "sample_clients": clients},
    )
