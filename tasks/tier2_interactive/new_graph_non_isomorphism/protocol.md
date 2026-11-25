# Protocol

The task uses the same two-event, 24-lane private-coin hidden-source protocol
as `t2.new_graph_non_isomorphism`: `gni.begin` at sequence 0, followed by one
`gni.response` containing 24 source bits at sequence 1. The new task has an
independent task ID, generation domain, seven replacement distributions, and
a 600-second total wall-clock budget.
