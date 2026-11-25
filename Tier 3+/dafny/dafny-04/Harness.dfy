module ArthurHarness {
  import C = Challenge
  import S = Solution
  method Main() {
    var c: C.Candidate := new S.Candidate();
    var f := {C.Clause({1},{}),C.Clause({2},{1}),C.Clause({3},{2}),
              C.Clause({1,73},{1})};
    var piv := [1,2];
    var h := c.Reduce(f,piv);
    expect |h| == 3 && h[2] == {C.Clause({3},{})};
    assert h[2] == {C.Clause({3},{})} by {
      assert h[1] == C.Next(f,1);
      assert h[1] == {C.Clause({2},{}),C.Clause({3},{2})};
      assert h[2] == C.Next(h[1],2);
    }
    var m := c.Lift(f,piv,h,{3,99});
    expect m == {1,2,3,99};
    var impossible := c.Reduce({C.Clause({6},{}),C.Clause({},{6})},[6]);
    expect impossible[1] == {C.Clause({},{})};
    var repeats := c.Reduce({C.Clause({4},{4})},[4,4]);
    expect repeats[1] == {} && repeats[2] == {};
    print "AIPBENCH_DAFNY_OK:c03\n";
  }
}
