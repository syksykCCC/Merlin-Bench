# Task Specification: New List Graph Homomorphism

Task ID: `t1.new_list_graph_homomorphism`. Version: `0.1.0`. The protocol is
one-shot deterministic verification.

The public instance defines finite simple undirected graphs
(G=(V_G,E_G)) and (H=(V_H,E_H)), with source vertices numbered
`1 .. source_num_vertices`, target vertices numbered
`1 .. target_num_vertices`, and a nonempty allowed set (L(v)\subseteq V_H)
for every source vertex. These are independent vertex spaces. Edge objects are
unordered pairs with opaque `edge_id` values. The `lists` array may be shuffled;
its `source_vertex` field identifies the applicable source vertex.

Submit a function (\varphi:V_G\to V_H) satisfying

\[
 \varphi(v)\in L(v)\quad\text{for all }v,
 \qquad
 \{u,v\}\in E_G\Longrightarrow\{\varphi(u),\varphi(v)\}\in E_H.
\]

`instance.json` has exactly `format_version`, `source_num_vertices`,
`source_edges`, `target_num_vertices`, `target_edges`, and `lists`. Each edge
has `edge_id`, `u`, and `v`. Each list object has `source_vertex` and
`allowed_targets`.

Send one event with sequence `0`, kind `homomorphism.assignment`, empty
`artifact_refs`, and payload exactly:

```json
{"mapping": [a_1, a_2, "...", a_n]}
```

The array must have exactly `source_num_vertices` entries. Entry `v - 1` must
be a JSON integer naming a target vertex in the public list for source vertex
`v`. Strings, booleans, floating-point values, out-of-range IDs, extra payload
fields, and attached artifacts are invalid.

Arthur accepts exactly when every list constraint and every source-edge
constraint holds. A rejection is terminal and cannot be retried. The resource
limits are 600 seconds wall time, four CPU cores, 4096 MiB memory, 4096 MiB disk,
one event, and an 8 MiB artifact limit.
