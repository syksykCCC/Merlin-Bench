# Task Specification: New Weighted Partial MaxSAT Assignment

- Task ID: `t1.new_weighted_partial_maxsat`
- Version: `0.1.0`
- Mode: deterministic one-shot
- Total wall-clock budget: 600 seconds

The public object in `instance.json` is a weighted partial Boolean CNF instance.
Merlin must submit one complete assignment. The run terminates after that event,
whether Arthur accepts or rejects it.

## Public instance

`num_variables` is (n). Variables are numbered from 1 through (n), while
the submitted assignment array is zero-based: array entry `assignment[i - 1]`
is the value of variable (i).

Each member of `hard_clauses` has a distinct integer `clause_id` and a nonempty
`literals` array. Each member of `soft_clauses` additionally has a positive
integer `weight`. A positive literal (i) is true exactly when variable (i)
has value 1; a negative literal (-i) is true exactly when it has value 0. A
clause is satisfied when at least one literal is true.

For assignment (a), define its soft cost by

\[
\operatorname{cost}(a)=
\sum_{C\text{ in soft_clauses}:a\not\models C}\operatorname{weight}(C).
\]

Arthur accepts exactly when every hard clause is satisfied and
`cost(assignment) <= threshold`. All arithmetic is exact integer arithmetic.

## Submission

Send exactly one event with `sequence` 0, kind `maxsat.assignment`, and empty
`artifact_refs`. Its payload has exactly one field:

```json
{"assignment": [0, 1, 0, 1]}
```

The array must contain exactly `num_variables` JSON integers, each either 0 or
1. The example illustrates only the wire shape and is not an answer to an
evaluation instance. One convenient command is:

```text
python agent_client.py event --sequence 0 --kind maxsat.assignment --payload-file assignment.json
```

Malformed payloads, invalid Boolean values, wrong length, any violated hard
clause, or soft cost above the public threshold cause terminal rejection. There
is no retry in the same run.
