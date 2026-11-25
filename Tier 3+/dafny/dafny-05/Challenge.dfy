module Challenge {
  datatype Expr = Num(k: int) | Peek(addr: Expr) | Add(a: Expr,b: Expr)
  datatype Stmt = Skip | Put(addr: Expr, value: Expr)
    | Then(first: Stmt, second: Stmt) | Choose(test: Expr, yes: Stmt, no: Stmt)

  function Fetch(s: seq<int>, i: int): int {
    if 0 <= i < |s| then s[i] else 0
  }
  function Eval(e: Expr,s: seq<int>): int {
    match e
    case Num(k) => k
    case Peek(k) => Fetch(s,Eval(k,s))
    case Add(a,b) => Eval(a,s)+Eval(b,s)
  }
  function Exec(p: Stmt,s: seq<int>): seq<int>
    ensures |Exec(p,s)| == |s|
  {
    match p
    case Skip => s
    case Put(k,v) =>
      var j := Eval(k,s);
      if 0 <= j < |s| then s[j := Eval(v,s)] else s
    case Then(a,b) => Exec(b,Exec(a,s))
    case Choose(k,a,b) => if Eval(k,s) != 0 then Exec(a,s) else Exec(b,s)
  }

  datatype Term = Imm(k: int) | Read(addr: int) | Sum(a: Term,b: Term)
    | Eq(a: Term,b: Term) | Mux(test: Term,yes: Term,no: Term)
    | Jump(test: Term,yes: Term,no: Term)
  datatype Event = Access(addr: int) | Branch(taken: bool)

  function Value(t: Term,s: seq<int>): int {
    match t
    case Imm(k) => k
    case Read(j) => Fetch(s,j)
    case Sum(a,b) => Value(a,s)+Value(b,s)
    case Eq(a,b) => if Value(a,s)==Value(b,s) then 1 else 0
    case Mux(k,a,b) => if Value(k,s)!=0 then Value(a,s) else Value(b,s)
    case Jump(k,a,b) => if Value(k,s)!=0 then Value(a,s) else Value(b,s)
  }
  function Observe(t: Term,s: seq<int>): seq<Event> {
    match t
    case Imm(k) => []
    case Read(j) => [Access(j)]
    case Sum(a,b) => Observe(a,s)+Observe(b,s)
    case Eq(a,b) => Observe(a,s)+Observe(b,s)
    case Mux(k,a,b) => Observe(k,s)+Observe(a,s)+Observe(b,s)
    case Jump(k,a,b) =>
      var pick := Value(k,s)!=0;
      Observe(k,s)+[Branch(pick)]+(if pick then Observe(a,s) else Observe(b,s))
  }
  function Values(code: seq<Term>,s: seq<int>): seq<int> {
    seq(|code|, i requires 0 <= i < |code| => Value(code[i],s))
  }
  function Log(code: seq<Term>,s: seq<int>): seq<Event>
    decreases |code|
  {
    if |code| == 0 then [] else Observe(code[0],s)+Log(code[1..],s)
  }

  trait {:termination false} Candidate {
    method Compile(p: Stmt, width: nat) returns (code: seq<Term>)
      ensures |code| == width
      ensures forall s :: |s| == width ==> Values(code,s) == Exec(p,s)
      ensures forall s,t :: |s| == width && |t| == width ==> Log(code,s) == Log(code,t)
  }
}
