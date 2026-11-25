# Task Specification: Hamiltonicity Bind--Challenge--Open

This is the complete participant-facing specification for task
`t2.new_hamiltonicity_bind_open`, version `0.1.0`. Every case has the same public
Hamiltonicity problem, 24-lane commitment, challenge distribution, opening format,
and verifier. Solve the graph in the generated `instance.json`.

## 1. Public graph and Hamilton cycle

The public input is an undirected simple graph

\[
G=([n],E),\qquad [n]=\{0,1,\ldots,n-1\}.
\]

Every edge is an unordered pair of distinct vertices. JSON stores it as `[u,v]`
with `u<v`. The edge array is strictly lexicographically sorted, contains no
duplicates, and all endpoints lie in `[0,n)`. Vertex numbers are labels only.

A Hamilton cycle is an array

\[
C=(v_0,v_1,\ldots,v_{n-1})
\]

that contains every vertex exactly once and satisfies

\[
\{v_i,v_{(i+1)\bmod n}\}\in E
\quad\text{for every }0\le i<n.
\]

The starting vertex and orientation are arbitrary. Scored public graphs are
guaranteed to contain at least one Hamilton cycle.

## 2. Public instance JSON

`instance.json` is exactly:

```text
{
  "format_version": "aip-hamiltonicity/1",
  "graph_model": "undirected_simple",
  "num_vertices": n,
  "edges": [[u_0,v_0], [u_1,v_1], ...],
  "challenge_lanes": 24
}
```

## 3. Relabeling convention

For a permutation `pi` of `[n]`, this task always uses the
**source-to-commit** orientation:

```text
pi[u] = the vertex ID in the committed graph assigned to public source vertex u
```

The relabeled graph \(H=\pi(G)\) has edge set

\[
E(H)=\{\{\pi(u),\pi(v)\}:\{u,v\}\in E(G)\}.
\]

Normalize every transformed edge so its smaller endpoint comes first, remove no
edges, and sort the entire array. An inverse permutation is not accepted in place
of the required source-to-commit array unless it happens to equal the same
permutation.

## 4. Exact two-event protocol

The protocol has 24 lanes.

### 4.1 Sequence 0: atomic commitment

Submit:

- `sequence`: exactly `0`;
- `kind`: exactly `hamiltonicity.commit`;
- `payload`: exactly `{"graphs": [H_0, ..., H_23]}`;
- `artifact_refs`: empty.

Every committed graph is a complete object of the form

```text
{"num_vertices": n, "edges": [[u_0,v_0], ...]}
```

with the same strict canonical graph rules as the public graph. The array must have
exactly 24 entries. Arthur fully parses the entire vector and records the event
before deriving any challenge bit. There is no per-lane commit, chunk feedback, or
partial acceptance.

After a valid commit, Arthur samples independent uniform bits

\[
(c_0,\ldots,c_{23})\xleftarrow{\$}\{0,1\}^{24}
\]

and returns `hamiltonicity.challenge` with payload
`{"bits": [c_0, ..., c_23]}`.

### 4.2 Sequence 1: tagged openings

Submit:

- `sequence`: exactly `1`;
- `kind`: exactly `hamiltonicity.open`;
- `payload`: exactly `{"openings": [O_0, ..., O_23]}`;
- `artifact_refs`: empty.

For lane `j`, the opening is determined by `c_j`:

```text
c_j = 0:
  {"kind": "isomorphism", "permutation": [pi[0], ..., pi[n-1]]}

c_j = 1:
  {"kind": "cycle", "vertices": [w_0, ..., w_(n-1)]}
```

For bit 0, `permutation` must be a bijection of `[n]` in source-to-commit
orientation, and relabeling every public edge must reproduce the corresponding
committed edge set exactly. For bit 1, `vertices` must be a Hamilton cycle in the
corresponding committed graph, using committed vertex IDs.

The tagged kind must match the bit. All 24 lanes must pass. A single wrong kind,
inverse orientation, duplicate/missing vertex, non-edge, wrong graph, or changed
commitment rejects the entire run. The response is terminal; there is no retry or
reset.

## 5. Strict parsing and reason codes

JSON booleans are not integer vertex IDs or challenge bits. Floats, strings, nulls,
tuples, short/long arrays, unsorted edges, duplicate edges, `u>=v`, out-of-range
IDs, extra fields, wrong event kinds, and artifact references are invalid.

- Structurally malformed commit/open events return
  `HAMILTONICITY_MALFORMED_EVENT`.
- A structurally valid opening that does not satisfy its challenge returns
  `HAMILTONICITY_INVALID_OPENING`.
- A fully valid transcript returns `ACCEPT` with `PROTOCOL_ACCEPT`.

The runtime also enforces event sequence. Do not send sequence 1 before receiving
the sequence-0 response, and do not retransmit a sequence after a response was
received.

## 6. Using the supplied HTTP client

Inspect the live instance without printing the connection secret:

```text
python agent_client.py --timeout 600 info
```

Write the complete commit payload to `commit.json`, then submit:

```text
python agent_client.py --timeout 600 event --sequence 0 --kind hamiltonicity.commit --payload-file commit.json
```

After reading all 24 bits, write `open.json` and submit once:

```text
python agent_client.py --timeout 600 event --sequence 1 --kind hamiltonicity.open --payload-file open.json
```

If a connection fails with unknown server outcome, query status and diagnose the
connection. Blind retransmission is not promised to be idempotent.

## 7. Budget

The total wall-clock budget is 600 seconds with four CPU cores, 4,096 MiB memory,
4,096 MiB disk, and a 64 MiB event-artifact cap. The clock starts when Arthur loads
the runtime. Both HTTP events, Arthur verification, and terminal response share the
same 10 minutes. An HTTP timeout does not extend the global budget.
