module Challenge {
  datatype Data = D(n:int, x:int, y:int, z:int)
  datatype Aff = A(n:int, x:int, y:int, z:int, k:int)
  datatype Frame = F(pc:nat, v:Data)
  datatype Path = Path(states:seq<Frame>, edges:seq<nat>)
  datatype Cert = Cert(inv:seq<seq<Aff>>, proof:seq<seq<seq<int>>>)

  function Val(f:Aff, d:Data):int { f.n*d.n+f.x*d.x+f.y*d.y+f.z*d.z+f.k }
  predicate Holds(rows:seq<Aff>, d:Data) { forall f :: f in rows ==> Val(f,d)<=0 }
  function Init(): seq<Aff> {
    [A(-1,0,0,0,0),A(-1,1,0,0,0),A(1,-1,0,0,0),
     A(0,0,1,0,0),A(0,0,-1,0,0),A(0,0,0,1,0),A(0,0,0,-1,0)]
  }
  function Safety(pc:nat): seq<Aff> {
    [A(0,-1,0,0,0),A(0,0,-1,0,0),A(0,0,0,-1,0)] +
    (if pc==2 then [A(-2,0,1,0,0),A(2,0,-1,0,0)] else [])
  }
  function From(e:nat):nat { if e==0 || e==4 then 0 else 1 }
  function To(e:nat):nat { if e<=1 then 1 else if e==4 then 2 else 0 }
  function Guard(e:nat):seq<Aff> {
    if e<=1 then [A(0,-1,0,0,1)]
    else if e==3 then [A(0,0,0,-1,1)]
    else if e==4 then [A(0,1,0,0,0)] else []
  }
  function Move(e:nat,d:Data,faulty:bool):Data {
    if e==0 then D(d.n,d.x-1,d.y,d.z+1)
    else if e==1 then D(d.n,d.x-1,d.y,d.z+2)
    else if e==2 then D(d.n,d.x,d.y+d.z+(if faulty then 0 else 1),0)
    else if e==3 then D(d.n,d.x+1,d.y,d.z-1)
    else D(d.n,d.x,d.y+d.z,0)
  }

  function Pull(e:nat,f:Aff):Aff {
    if e<=1 then A(f.n,f.x,f.y,f.z,f.k-f.x+(if e==0 then f.z else 2*f.z))
    else if e==2 then A(f.n,f.x,f.y,f.y,f.k+f.y)
    else if e==3 then A(f.n,f.x,f.y,f.z,f.k+f.x-f.z)
    else A(f.n,f.x,f.y,f.y,f.k)
  }
  lemma PullValue(e:nat,f:Aff,d:Data)
    requires e<5
    ensures Val(Pull(e,f),d)==Val(f,Move(e,d,false))
  {}
  function Add(a:Aff,b:Aff):Aff { A(a.n+b.n,a.x+b.x,a.y+b.y,a.z+b.z,a.k+b.k) }
  function ValidIndices(n:nat,w:seq<int>):bool
    decreases |w|
  { |w|==0 || (0<=w[0]<n && ValidIndices(n,w[1..])) }
  function Sum(rows:seq<Aff>, w:seq<int>):Aff
    decreases |w|
  {
    if |w|==0 || w[0]<0 || w[0]>=|rows| then A(0,0,0,0,0) else Add(rows[w[0]],Sum(rows,w[1..]))
  }
  // Repeated indices encode nonnegative integer multipliers.
  opaque predicate Entails(rows:seq<Aff>, q:Aff, w:seq<int>) {
    ValidIndices(|rows|,w) &&
    (var t := Sum(rows,w); t.n==q.n && t.x==q.x && t.y==q.y && t.z==q.z && t.k>=q.k)
  }
  lemma SumOK(rows:seq<Aff>,w:seq<int>,d:Data)
    requires Holds(rows,d) && ValidIndices(|rows|,w)
    ensures Val(Sum(rows,w),d)<=0
    decreases |w|
  {
    if |w|>0 {
      assert w==[w[0]]+w[1..];
      SumOK(rows,w[1..],d);
      assert rows[w[0]] in rows;
      var a,b := rows[w[0]],Sum(rows,w[1..]);
      assert Val(Add(a,b),d)==Val(a,d)+Val(b,d);
    }
  }
  lemma Sound(rows:seq<Aff>,q:Aff,w:seq<int>,d:Data)
    requires Holds(rows,d) && Entails(rows,q,w)
    ensures Val(q,d)<=0
  { reveal Entails(); SumOK(rows,w,d); }

  function Prem(inv:seq<seq<Aff>>,k:nat):seq<Aff>
    requires |inv|==3 && k<9
  { if k==0 then Init() else if k<=5 then inv[From(k-1)]+Guard(k-1) else inv[k-6] }
  function Goals(inv:seq<seq<Aff>>,k:nat):seq<Aff>
    requires |inv|==3 && k<9
  {
    if k==0 then inv[0] else if k>=6 then Safety(k-6) else
      var dest:=inv[To(k-1)];
      seq(|dest|, j requires 0<=j<|dest| => Pull(k-1,dest[j]))
  }
  opaque predicate Block(inv:seq<seq<Aff>>, k:nat, proofs:seq<seq<int>>) {
    |inv|==3 && k<9 && |proofs|==|Goals(inv,k)| &&
    (forall j :: 0<=j<|proofs| ==> Entails(Prem(inv,k),Goals(inv,k)[j],proofs[j]))
  }
  opaque predicate Inductive(c:Cert) {
    |c.inv|==3 && |c.proof|==9 && (forall k :: 0<=k<9 ==> Block(c.inv,k,c.proof[k]))
  }
  predicate Edge(p:Frame,e:nat,q:Frame,faulty:bool) {
    e<5 && p.pc==From(e) && q.pc==To(e) && Holds(Guard(e),p.v) &&
    q.v==Move(e,p.v,faulty)
  }
  lemma ApplyBlock(c:Cert,k:nat,d:Data)
    requires Inductive(c) && |c.inv|==3 && k<9 && Holds(Prem(c.inv,k),d)
    ensures Holds(Goals(c.inv,k),d)
  {
    reveal Inductive();
    reveal Block();
    var targets := Goals(c.inv,k);
    forall j | 0<=j<|targets| ensures Val(targets[j],d)<=0 {
      Sound(Prem(c.inv,k),targets[j],c.proof[k][j],d);
    }
    forall f | f in targets ensures Val(f,d)<=0 {
      assert exists j :: 0<=j<|targets| && targets[j]==f;
    }
  }
  lemma Initial(c:Cert,d:Data)
    requires Inductive(c) && |c.inv|==3 && Holds(Init(),d)
    ensures Holds(c.inv[0],d)
  { reveal Inductive(); ApplyBlock(c,0,d); }
  lemma Preserve(c:Cert,p:Frame,e:nat,q:Frame)
    requires Inductive(c) && |c.inv|==3 && Edge(p,e,q,false) && Holds(c.inv[p.pc],p.v)
    ensures Holds(c.inv[q.pc],q.v)
  {
    reveal Inductive();
    var k := e+1;
    assert Holds(Prem(c.inv,k),p.v);
    ApplyBlock(c,k,p.v);
    var dest:=c.inv[q.pc];
    forall j | 0<=j<|dest| ensures Val(dest[j],q.v)<=0 {
      assert Goals(c.inv,k)[j]==Pull(e,dest[j]) && Pull(e,dest[j]) in Goals(c.inv,k);
      PullValue(e,dest[j],p.v);
    }
    forall f | f in dest ensures Val(f,q.v)<=0 {
      assert exists j :: 0<=j<|dest| && dest[j]==f;
    }
  }
  lemma SiteSafe(c:Cert,p:Frame)
    requires Inductive(c) && |c.inv|==3 && p.pc<3 && Holds(c.inv[p.pc],p.v)
    ensures Holds(Safety(p.pc),p.v)
  { ApplyBlock(c,6+p.pc,p.v); }
  opaque predicate Counterexample(p:Path) {
    |p.states|==|p.edges|+1 && p.states[0].pc==0 && Holds(Init(),p.states[0].v) &&
    (forall i :: 0<=i<|p.edges| ==> Edge(p.states[i],p.edges[i],p.states[i+1],true)) &&
    !Holds(Safety(p.states[|p.edges|].pc),p.states[|p.edges|].v)
  }
  opaque ghost predicate SafeInvariant(inv:seq<seq<Aff>>) {
    |inv|==3 &&
    (forall d :: Holds(Init(),d) ==> Holds(inv[0],d)) &&
    (forall p,e:nat,q :: Edge(p,e,q,false) && Holds(inv[p.pc],p.v) ==> Holds(inv[q.pc],q.v)) &&
    (forall pc:nat,d :: pc<3 && Holds(inv[pc],d) ==> Holds(Safety(pc),d))
  }

  trait {:termination false} Candidate {
    function Invariant():Cert
    function Execution():Path
    ghost method InvariantProof() ensures SafeInvariant(Invariant().inv)
    ghost method ExecutionProof() ensures Counterexample(Execution())
  }
}
