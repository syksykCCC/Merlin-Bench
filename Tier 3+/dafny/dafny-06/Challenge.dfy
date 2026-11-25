module Challenge {
  datatype Vertex = Vertex(goal: bool, controller: bool, left: int, right: int)

  predicate Arena(g: seq<Vertex>) {
    forall v :: 0 <= v < |g| ==> 0 <= g[v].left < |g| && 0 <= g[v].right < |g|
  }

  predicate Wins(g: seq<Vertex>, rank: seq<int>, move: seq<bool>, v: int)
    requires Arena(g) && |g| == |rank| == |move| && 0 <= v < |g|
  {
    var n := g[v];
    var a,b := rank[n.left],rank[n.right];
    var picked := if move[v] then b else a;
    if n.goal then rank[v] == 0
    else (rank[v] > 0 &&
      (if n.controller then 0 <= picked < rank[v]
       else 0 <= a < rank[v] && 0 <= b < rank[v]))
  }

  predicate Safe(g: seq<Vertex>, rank: seq<int>, move: seq<bool>, v: int)
    requires Arena(g) && |g| == |rank| == |move| && 0 <= v < |g|
  {
    var n := g[v];
    var a,b := rank[n.left],rank[n.right];
    !n.goal && rank[v] == -1 &&
      (if n.controller then a == -1 && b == -1
       else (if move[v] then b else a) == -1)
  }

  ghost predicate Certificate(g: seq<Vertex>, rank: seq<int>, move: seq<bool>) {
    Arena(g) && |g| == |rank| == |move| &&
    (forall v :: 0 <= v < |g| ==>
      Wins(g,rank,move,v) || Safe(g,rank,move,v))
  }

  ghost predicate Play(g: seq<Vertex>, rank: seq<int>, move: seq<bool>, path: seq<int>) {
    Certificate(g,rank,move) && |path| > 0 &&
    (forall j :: 0 <= j < |path| ==> 0 <= path[j] < |g|) &&
    (forall j :: 0 <= j < |path|-1 ==>
      var v := path[j];
      var n := g[v];
      !n.goal &&
      (if n.controller == (rank[v] >= 0)
       then path[j+1] == (if move[v] then n.right else n.left)
       else path[j+1] == n.left || path[j+1] == n.right))
  }

  trait {:termination false} Candidate {
    method Solve(g: seq<Vertex>) returns (rank: seq<int>, move: seq<bool>)
      requires Arena(g)
      ensures Certificate(g,rank,move)

    lemma Follow(g: seq<Vertex>, rank: seq<int>, move: seq<bool>, path: seq<int>)
      requires Play(g,rank,move,path)
      ensures rank[path[0]] < 0 ==> rank[path[|path|-1]] < 0 && !g[path[|path|-1]].goal
      ensures rank[path[0]] >= 0 ==>
        0 <= rank[path[|path|-1]] <= rank[path[0]]-(|path|-1)
  }
}
