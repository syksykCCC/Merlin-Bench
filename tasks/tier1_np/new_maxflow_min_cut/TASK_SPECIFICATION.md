# Task Specification: New Max-Flow / Min-Cut Certificates

- Task ID: `t1.new_maxflow_min_cut`
- Version: `0.1.0`
- Mode: deterministic one-shot
- Total wall-clock budget: 600 seconds

The public object in `instance.json` describes a directed graph with
nonnegative integral capacities. Merlin must submit one feasible flow together
with a source-side cut of equal value. Acceptance is terminal; there is no retry.

## Public instance

`num_vertices` is (n), and vertex IDs are the integers from `0` through
`n - 1`. `source` is (s), `sink` is (t\ne s), and `directed` is `true`.
Every member of `edges` has the exact fields `edge_id`, `tail`, `head`, and
`capacity`. Edge IDs are distinct identities; array positions are not edge IDs.
Parallel directed edges may occur and must remain separate. Self-loops do not
occur. Capacities and their total fit the inclusive JSON safe-integer range.

For each edge (e=(u_e,v_e)), let (c_e) be its capacity. Merlin submits an
integer (f_e) for every edge, a nonnegative integer flow value (F), and a
vertex set (S).

## Acceptance relation

Arthur requires all of the following:

1. every public edge ID occurs exactly once and no other ID occurs;
2. (0\le f_e\le c_e) for every edge;
3. for every (v\notin\{s,t\}), total submitted inflow equals total submitted outflow;
4. net outflow at (s) and net inflow at (t) both equal (F);
5. (s\in S), (t\notin S), and every listed vertex is valid and distinct;
6. the directed cut capacity
   \[
   \sum_{e:u_e\in S,\ v_e\notin S} c_e
   \]
   equals (F).

All submitted numbers must be JSON integers, not booleans, strings, or floating
point values. Equal feasible-flow and cut values certify maximum flow and minimum
cut by weak duality.

## Submission

Send exactly one event with `sequence` 0, kind `maxflow.certificate`, and empty
`artifact_refs`. Its `payload` must contain exactly:

```json
{
  "flow_value": 17,
  "edge_flows": [
    {"edge_id": 91, "flow": 5},
    {"edge_id": 27, "flow": 12}
  ],
  "source_side_cut": [3, 8]
}
```

The example illustrates shape only. Orders of `edge_flows` and
`source_side_cut` are irrelevant. A convenient command is:

```text
python agent_client.py event --sequence 0 --kind maxflow.certificate --payload-file certificate.json
```

Arthur accepts exactly when all checks above pass. Malformed shape, a missing or
duplicate edge, a capacity or conservation error, a mismatched flow value, an
invalid cut, or an unequal cut capacity causes terminal rejection.
