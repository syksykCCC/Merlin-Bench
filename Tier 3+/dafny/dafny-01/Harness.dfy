module ArthurHarness {
  import C = Challenge
  import S = Solution
  method Main() {
    var impl: C.Candidate := new S.Candidate();
    var cert := impl.Invariant();
    var bad := impl.Execution();
    impl.InvariantProof();
    impl.ExecutionProof();
    if C.Inductive(cert) && C.Counterexample(bad) {
      print "AIPBENCH_DAFNY_OK:c04\n";
    } else {
      print "Certificates rejected.\n";
    }
  }
}
