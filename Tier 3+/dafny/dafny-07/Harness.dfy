module ArthurHarness {
  import C = Challenge
  import S = Solution
  method Main() {
    var p: C.Candidate := new S.Candidate();
    var a := p.Decompose(C.P);
    var b := p.Decompose(C.Q);
    p.Correct(C.P);
    p.Correct(C.Q);
    if C.Valid(C.P,a) && C.Valid(C.Q,b) {
      print "AIPBENCH_DAFNY_OK:c05\n";
    } else {
      print "Invalid integer matrix certificate.\n";
    }
  }
}
