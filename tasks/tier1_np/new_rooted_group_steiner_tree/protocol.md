# Protocol

Arthur publishes the weighted graph, root, vertex groups, and budget. The
participant sends exactly one event with `sequence` 0, kind
`group_steiner.edge_set`, no artifacts, and payload
`{"edge_ids": [e_1, ..., e_k]}`. IDs must be distinct public edge IDs.

Arthur accepts exactly when the selected total weight is within budget, every
selected endpoint is connected to the root through selected edges, and every
public group contains a reached vertex. Every response is terminal.
