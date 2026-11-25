module ArthurHarness {
  import C = Challenge
  import S = Solution
  method Main() {
    var c: C.Candidate := new S.Candidate();
    var id := C.Lam(C.Unit,C.V(0));
    var open := C.App(C.Lam(C.Unit,C.Lam(C.Unit,C.V(1))),C.V(0));
    var a := c.Reduce([C.Unit],open,4);
    expect a == [open,C.Lam(C.Unit,C.V(1))];
    expect C.TypeOf(C.Lam(C.Unit,C.V(0)),[C.Unit]) == C.TypeOf(a[1],[C.Unit]) &&
      a[1] != C.Lam(C.Unit,C.V(0));
    var dec := C.App(C.Lam(C.Unit,C.V(1)),C.Star);
    var b := c.Reduce([C.Unit],dec,4);
    expect b == [dec,C.V(0)];
    var scoped := C.Lam(C.Unit,open);
    assert [C.Unit]+[] == [C.Unit];
    assert C.TypeOf(open,[C.Unit]).Ok?;
    var d := c.Reduce([],scoped,4);
    expect d == [scoped,C.Lam(C.Unit,C.Lam(C.Unit,C.V(1)))];
    var chain := C.App(id,C.App(id,C.Star));
    var z := c.Reduce([],chain,0);
    expect z == [chain];
    var partial := c.Reduce([],chain,1);
    expect partial == [chain,C.App(id,C.Star)];
    var done := c.Reduce([],chain,5);
    expect done == [chain,C.App(id,C.Star),C.Star];
    print "AIPBENCH_DAFNY_OK:c02\n";
  }
}
