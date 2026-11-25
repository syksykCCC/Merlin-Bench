module Challenge {
  predicate Rising(s: seq<int>, l: int, r: int) {
    0 <= l < r <= |s| &&
    (forall k :: l < k < r ==> s[k-1] < s[k])
  }

  trait {:termination false} Candidate {
    method Longest(s: seq<int>) returns (left: nat, right: nat)
      requires |s| > 0
      ensures Rising(s,left,right)
      ensures forall l,r :: Rising(s,l,r) ==> r-l <= right-left
  }
}
