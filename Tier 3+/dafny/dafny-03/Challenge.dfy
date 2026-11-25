module Challenge {
  datatype St = St(a: int, b: int, clock: int)
  datatype Tour = Tour(stem: seq<bool>, there: seq<bool>, back: seq<bool>)
  datatype Cut = Cut(upper: set<St>, lower: set<St>)

  function Step(green: bool, s: St, bit: bool): St {
    var a := if s.a < 3 then
      (if bit then (if s.a == 2 then 2 else s.a+1) else (if s.a == 2 then 3 else 0))
      else (if green && !bit then 0 else 3);
    var b := if s.b < 3 then
      (if bit then (if s.b == 2 then 2 else s.b+1) else (if s.b == 2 then 3 else 0))
      else (if bit then 4 else if s.b == 4 then 5 else 3);
    St(a,b,(s.clock+1)%3)
  }

  function Run(green: bool, s: St, w: seq<bool>): St
    decreases |w|
  {
    if |w| == 0 then s else Run(green,Step(green,s,w[0]),w[1..])
  }
  predicate First(s: St) { s.a == 1 && s.clock == 2 }
  predicate Second(s: St) { s.b == 5 && s.clock == 0 }

  predicate Accepts(green: bool, t: Tour) {
    var a := Run(green,St(0,0,0),t.stem);
    var b := Run(green,a,t.there);
    First(a) && Second(b) && |t.back| > 0 && Run(green,b,t.back) == a
  }

  opaque predicate Closed(c: Cut, s: St, bit: bool) {
    (s in c.upper ==> Step(false,s,bit) in c.upper+c.lower) &&
    (s in c.lower ==> Step(false,s,bit) in c.lower)
  }
  predicate Legal(s: St) { 0 <= s.a <= 3 && 0 <= s.b <= 5 && 0 <= s.clock < 3 }
  opaque predicate Refutes(c: Cut) {
    St(0,0,0) in c.upper+c.lower && c.upper*c.lower == {} &&
    (forall s :: s in c.upper+c.lower ==> Legal(s) && Closed(c,s,false) && Closed(c,s,true)) &&
    (forall s :: s in c.upper ==> !Second(s)) &&
    (forall s :: s in c.lower ==> !First(s))
  }

  lemma Stay(c: Cut, s: St, w: seq<bool>)
    requires Refutes(c) && s in c.upper+c.lower
    ensures Run(false,s,w) in c.upper+c.lower
    ensures s in c.lower ==> Run(false,s,w) in c.lower
    decreases |w|
  {
    if |w| > 0 {
      assert Closed(c,s,w[0]) by { reveal Refutes(); }
      reveal Closed();
      Stay(c,Step(false,s,w[0]),w[1..]);
    }
  }
  lemma Excludes(c: Cut, t: Tour)
    requires Refutes(c)
    ensures !Accepts(false,t)
  {
    reveal Refutes();
    if Accepts(false,t) {
      var a := Run(false,St(0,0,0),t.stem);
      Stay(c,St(0,0,0),t.stem);
      var b := Run(false,a,t.there);
      Stay(c,a,t.there);
      assert b in c.lower;
      Stay(c,b,t.back);
      assert a in c.lower;
    }
  }

  trait {:termination false} Candidate {
    function Green(): Tour
    function Red(): Cut
    ghost method GreenProof()
      ensures Accepts(true,Green())
    ghost method RedProof()
      ensures Refutes(Red())
  }
}
