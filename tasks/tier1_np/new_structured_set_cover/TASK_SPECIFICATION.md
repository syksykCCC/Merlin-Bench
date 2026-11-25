# Task Specification: New Structured Set Cover

- Task ID: `t1.new_structured_set_cover`
- Version: `0.1.0`
- Mode: deterministic one-shot
- Total wall-clock budget: 600 seconds

The public universe is the integers from 1 through `num_elements`. Each object
in `sets` has a unique positive integer `set_id`, a nonempty `elements` array,
and a positive integer `weight`. Set IDs are opaque and are not array indices.

Submit a selection whose exact total weight is at most the public `budget` and
whose union contains every public universe element. Selected sets may overlap.

Send exactly one event with `sequence` 0, kind `set_cover.selection`, empty
`artifact_refs`, and a payload with exactly this shape:

```json
{"set_ids": [17, 42]}
```

Every entry must be a JSON integer naming a public set, and no ID may occur
twice. The numbers above illustrate only the wire shape and are not an answer
to an evaluation instance. One convenient command is:

```text
python agent_client.py event --sequence 0 --kind set_cover.selection --payload-file selection.json
```

Arthur recomputes the exact weight and union from the public incidence lists.
Malformed payloads, unknown or duplicate IDs, weight above `budget`, or any
uncovered element cause terminal rejection. There is no retry in the same run.
