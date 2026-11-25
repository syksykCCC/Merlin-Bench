module ArthurHarness {
  import C = Challenge
  import S = Solution
  method Main() {
    var c: C.Candidate := new S.Candidate();
    var g := [C.Vertex(true,false,4,4), C.Vertex(false,true,4,0),
              C.Vertex(false,false,1,0), C.Vertex(false,false,2,4),
              C.Vertex(false,true,4,3), C.Vertex(false,true,3,2)];
    var r,m := c.Solve(g);
    expect r[0] == 0 && r[1] > 0 && r[2] > r[1] && r[3] == -1 && r[4] == -1 && r[5] > r[2];
    expect m[1] && m[3] && m[5];
    var rr,mm := c.Solve([C.Vertex(false,true,0,0)]);
    expect rr == [-1];
    var empty,none := c.Solve([]);
    expect empty == [] && none == [];
    print "AIPBENCH_DAFNY_OK:c08\n";
  }
}
