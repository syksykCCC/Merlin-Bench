# Task Specification: New Rooted Group Steiner Tree

- Task ID: `t1.new_rooted_group_steiner_tree`
- Version: `0.1.0`
- Mode: deterministic one-shot
- Total wall-clock budget: 600 seconds

The public instance gives a connected simple undirected graph with positive
integer edge weights, a distinguished `root`, nonempty vertex groups, and a
positive integer `budget`. Edge IDs are opaque and are not array indices.

Submit distinct public edge IDs whose exact total weight is at most `budget`.
Using only those edges, every selected endpoint must be reachable from `root`,
and at least one vertex from every public group must be reachable. Groups may
overlap and one vertex may satisfy more than one group.

Send exactly one event with `sequence` 0, kind `group_steiner.edge_set`, empty
`artifact_refs`, and a payload with exactly this shape:

```json
{"edge_ids": [17, 42]}
```

Every entry must be a JSON integer naming an edge in the public `edges` array,
and no ID may occur twice. The numbers above illustrate only the wire format.
One convenient command is:

```text
python agent_client.py event --sequence 0 --kind group_steiner.edge_set --payload-file edge_set.json
```

Arthur recomputes the exact weight, connectivity, and group coverage from the
public instance. A malformed payload, an unknown or repeated ID, excessive
weight, a disconnected selected endpoint, or an unhit group causes terminal
rejection. There is no retry in the same run.
