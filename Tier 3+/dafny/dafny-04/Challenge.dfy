module Challenge {
  datatype Clause = Clause(pos: set<int>, neg: set<int>)
  type Formula = set<Clause>

  predicate Holds(c: Clause, m: set<int>) {
    c.pos * m != {} || c.neg - m != {}
  }

  predicate Sat(f: Formula, m: set<int>) {
    forall c :: c in f ==> Holds(c,m)
  }

  predicate Free(c: Clause, v: int) { v !in c.pos && v !in c.neg }
  predicate Plus(c: Clause, v: int) { v in c.pos && v !in c.neg }
  predicate Minus(c: Clause, v: int) { v !in c.pos && v in c.neg }

  function Drop(c: Clause, v: int): Clause {
    Clause(c.pos-{v},c.neg-{v})
  }

  function Resolve(p: Clause, n: Clause, v: int): Clause {
    Clause((p.pos+n.pos)-{v},(p.neg+n.neg)-{v})
  }

  ghost function Next(f: Formula, v: int): Formula {
    (set c | c in f && Free(c,v)) +
    (set p,n | p in f && n in f && Plus(p,v) && Minus(n,v) :: Resolve(p,n,v))
  }

  ghost predicate Trace(f: Formula, piv: seq<int>, h: seq<Formula>) {
    |h| == |piv|+1 && h[0] == f &&
    (forall i :: 0 <= i < |piv| ==> h[i+1] == Next(h[i],piv[i]))
  }

  trait {:termination false} Candidate {
    method Reduce(f: Formula, piv: seq<int>) returns (h: seq<Formula>)
      ensures Trace(f,piv,h)
      ensures forall m :: Sat(f,m) ==> Sat(h[|h|-1],m)
      ensures forall c,v :: c in h[|h|-1] && v in piv ==> Free(c,v)

    method Lift(f: Formula, piv: seq<int>, h: seq<Formula>, partial: set<int>)
      returns (full: set<int>)
      requires Trace(f,piv,h) && Sat(h[|h|-1],partial)
      ensures Sat(f,full)
      ensures forall v :: v !in piv ==> (v in full) == (v in partial)
  }
}
