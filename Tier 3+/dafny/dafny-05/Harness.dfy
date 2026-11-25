module ArthurHarness {
  import C = Challenge
  import S = Solution
  method Main() {
    var c: C.Candidate := new S.Candidate();
    var z := C.Peek(C.Num(0));
    var nested := C.Choose(C.Peek(z),
      C.Put(C.Peek(C.Num(1)),C.Num(8)),C.Put(C.Num(1),C.Num(5)));
    var p := C.Then(C.Choose(z,nested,C.Put(C.Num(1),C.Num(3))),
                    C.Put(C.Num(0),C.Peek(C.Num(1))));
    var code := c.Compile(p,2);
    var a := [0,1];
    var b := [1,1];
    expect C.Values(code,a) == [3,3] && C.Values(code,b) == [8,8];
    expect C.Log(code,a) == C.Log(code,b);
    var eager := C.Mux(C.Read(0),C.Read(1),C.Read(0));
    var branch := C.Jump(C.Read(0),C.Read(1),C.Read(0));
    expect C.Value(eager,a) == C.Value(branch,a) && C.Value(eager,b) == C.Value(branch,b);
    expect C.Observe(eager,a) == C.Observe(eager,b);
    expect C.Observe(branch,a) == [C.Access(0),C.Branch(false),C.Access(0)];
    expect C.Observe(branch,b) == [C.Access(0),C.Branch(true),C.Access(1)];
    var empty := c.Compile(p,0);
    expect empty == [];
    print "AIPBENCH_DAFNY_OK:c04\n";
  }
}
