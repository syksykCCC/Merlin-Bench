module ArthurHarness {
  import S = Solution
  import C = Challenge
  method Main() {
    var impl: C.Candidate := new S.Candidate();
    var a,b := impl.Longest([7,7,1,3,5,4,6]);
    expect a == 2 && b == 5;
    var p,q := impl.Longest([-3]);
    expect p == 0 && q == 1;
    var x,y := impl.Longest([4,4,4]);
    expect y-x == 1;
    print "AIPBENCH_DAFNY_OK:c04\n";
  }
}
