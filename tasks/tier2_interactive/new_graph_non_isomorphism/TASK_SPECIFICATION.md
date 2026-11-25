# Task Specification: new Colored Graph Non-Isomorphism

This is the complete participant-facing specification for task
`t2.new_graph_non_isomorphism`, version `0.1.0`. The generated `instance.json`
is the input to solve.

## 1. Mathematical problem

A public graph is a vertex-colored undirected simple graph

\[
G=([N],E,\chi),\qquad [N]=\{0,1,\ldots,N-1\}.
\]

There are no loops or duplicate edges. Each JSON edge is stored as `[u,v]`
with `u < v`. Colors are equality-class labels. A color-preserving
isomorphism is a bijection \(\varphi:[N]\to[N]\) satisfying

\[
\{u,v\}\in E(G)\iff\{\varphi(u),\varphi(v)\}\in E(H),
\qquad \chi_G(u)=\chi_H(\varphi(u)).
\]

The public instance contains two same-order graphs \(G_0,G_1\) and promises
that they are not color-preserving isomorphic. Arthur independently creates
24 challenge lanes. In lane \(j\), it privately samples a source bit
\(\beta_j\in\{0,1\}\) and a uniformly random vertex permutation, then returns
a relabeled copy of \(G_{\beta_j}\). Submit all 24 source bits in lane order.
Arthur accepts exactly when every submitted bit is correct.

## 2. Public instance

`instance.json` has exactly this shape:

```text
{
  "format_version": "aip-gni-instance/1",
  "graph_model": "undirected_simple_vertex_colored",
  "challenge_lanes": 24,
  "graphs": [G0, G1]
}

Graph {
  "num_vertices": N,
  "colors": [c_0, ..., c_(N-1)],
  "edges": [[u_0, v_0], ...]
}
```

The two graphs have the same positive `num_vertices`. Every color is a
nonnegative integer. Edges are in range, unique, and lexicographically sorted.
Vertex IDs and edge-array positions have no meaning across graphs.

## 3. Exact two-event interaction

### Sequence 0

Submit kind `gni.begin`, exact payload `{}`, and no artifact references. Arthur
returns `status: "CONTINUE"`, reply kind `gni.challenge`, and payload
`{"graphs": [...]}` containing exactly 24 complete graphs.

### Sequence 1

Submit kind `gni.response`, no artifact references, and exact payload

```json
{"source_bits": [0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1]}
```

The displayed vector illustrates JSON shape only. Compute the actual vector
from the returned challenge. It must contain exactly 24 strict JSON integers,
each equal to `0` or `1`. A correct vector receives terminal `ACCEPT`. Any
malformed or incorrect response is terminal; there is no retry or reset.

## 4. Client and budget

The workspace provides `agent_client.py`. Inspect the live session with

```text
python agent_client.py --timeout 600 info
```

Request the challenge with

```text
python agent_client.py --timeout 600 event --sequence 0 --kind gni.begin --payload "{}" > begin-response.json
```

Submit an answer file with

```text
python agent_client.py --timeout 600 event --sequence 1 --kind gni.response --payload-file answer.json
```

The complete run has one shared 600-second wall-clock budget, four CPU cores,
4,096 MiB memory, and 4,096 MiB disk. Reading, computation, interaction,
serialization, and final verification all count. An HTTP timeout does not
extend the global budget. Do not retransmit an accepted sequence after an
uncertain connection outcome.
