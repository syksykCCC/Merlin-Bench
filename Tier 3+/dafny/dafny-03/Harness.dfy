module ArthurHarness {
  import C = Challenge
  import S = Solution
  method Main() {
    var implementation: C.Candidate := new S.Candidate();
    var green := implementation.Green();
    var red := implementation.Red();
    implementation.GreenProof();
    implementation.RedProof();
    if C.Accepts(true,green) && C.Refutes(red) {
      print "AIPBENCH_DAFNY_OK:c06\n";
    } else {
      print "Certificates rejected.\n";
    }
  }
}
