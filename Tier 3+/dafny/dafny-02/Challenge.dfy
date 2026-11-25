module Challenge {
  datatype Ty = Unit | Arrow(dom: Ty, cod: Ty)
  datatype Term = V(i: nat) | Star | Lam(param: Ty, body: Term) | App(f: Term, x: Term)
  datatype Maybe = Miss | Ok(ty: Ty)

  function TypeOf(t: Term, ctx: seq<Ty>): Maybe {
    match t
    case V(i) => if i < |ctx| then Ok(ctx[i]) else Miss
    case Star => Ok(Unit)
    case Lam(k,b) =>
      var bty := TypeOf(b,[k]+ctx);
      if bty.Ok? then Ok(Arrow(k,bty.ty)) else Miss
    case App(f,x) =>
      var ft := TypeOf(f,ctx);
      var xt := TypeOf(x,ctx);
      if ft.Ok? && ft.ty.Arrow? && xt == Ok(ft.ty.dom) then Ok(ft.ty.cod) else Miss
  }

  ghost function Shift(t: Term, byN: nat, cut: nat): Term {
    match t
    case V(i) => if i < cut then t else V(i+byN)
    case Star => Star
    case Lam(k,b) => Lam(k,Shift(b,byN,cut+1))
    case App(f,x) => App(Shift(f,byN,cut),Shift(x,byN,cut))
  }

  ghost function Plug(t: Term, arg: Term, depth: nat): Term {
    match t
    case V(i) =>
      if i < depth then t else if i == depth then Shift(arg,depth,0) else V(i-1)
    case Star => Star
    case Lam(k,b) => Lam(k,Plug(b,arg,depth+1))
    case App(f,x) => App(Plug(f,arg,depth),Plug(x,arg,depth))
  }

  predicate Reducible(t: Term) {
    match t
    case V(i) => false
    case Star => false
    case Lam(k,b) => Reducible(b)
    case App(f,x) => f.Lam? || Reducible(f) || Reducible(x)
  }

  ghost predicate Step(t: Term, u: Term) {
    match t
    case V(i) => false
    case Star => false
    case Lam(k,b) => u.Lam? && u.param == k && Step(b,u.body)
    case App(f,x) =>
      (f.Lam? && u == Plug(f.body,x,0)) ||
      (u.App? && ((u.x == x && Step(f,u.f)) || (u.f == f && Step(x,u.x))))
  }

  trait {:termination false} Candidate {
    method Reduce(ctx: seq<Ty>, t: Term, fuel: nat) returns (trace: seq<Term>)
      requires TypeOf(t,ctx).Ok?
      ensures 1 <= |trace| <= fuel+1 && trace[0] == t
      ensures forall j :: 0 <= j < |trace|-1 ==> Step(trace[j],trace[j+1])
      ensures forall j :: 0 <= j < |trace| ==> TypeOf(trace[j],ctx) == TypeOf(t,ctx)
      ensures |trace| == fuel+1 || !Reducible(trace[|trace|-1])
  }
}
