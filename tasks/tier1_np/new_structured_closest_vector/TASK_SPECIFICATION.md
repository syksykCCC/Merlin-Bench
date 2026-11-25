# Task Specification: New Structured Closest Vector

- Task ID: `t1.new_structured_closest_vector`
- Version: `0.1.0`
- Protocol mode: one-shot deterministic verification

## Public relation

The public instance gives a full-column-rank integer matrix
(B\in\mathbb Z^{d\times n}), an integer vector
(\tau\in\mathbb Z^d), a positive denominator (D), a nonnegative squared
radius numerator (K), and a positive coefficient bound (C). The columns of
(B) are ordered lattice basis vectors and the rational target is
(t=\tau/D).

Submit an ordered vector (z\in\mathbb Z^n). Arthur accepts exactly when every
(|z_j|\le C) and

\[
\lVert DBz-\tau\rVert_2^2\le K.
\]

The check uses arbitrary-precision integer arithmetic with no rounding or
tolerance. An accepted vector exists within the displayed bound.

## Public instance

`instance.json` is one object containing exactly:

| field | meaning |
|---|---|
| `format_version` | `aip-structured-closest-vector-instance/1` |
| `ambient_dimension` | (d), the number of rows and target coordinates |
| `rank` | (n), the number of basis columns and required coefficients |
| `basis` | row-major (d\times n) integer matrix (B) |
| `target_numerator` | length-(d) integer vector (\tau) |
| `denominator` | positive integer (D) |
| `radius_squared_numerator` | nonnegative integer (K) |
| `coefficient_bound` | positive integer (C) |

All stored instance integers and submitted coefficients must lie in the JSON
safe-integer interval from `-9007199254740991` through
`9007199254740991`. Booleans, strings, and floating-point numbers are not
integers for this protocol.

## Submission

Submit exactly one event with sequence `0`, kind
`closest_vector.coefficients`, no artifacts, and a payload containing exactly
one field named `coefficients`. Its value must be an array of exactly `rank`
JSON integers, ordered by the public basis columns and bounded in absolute
value by `coefficient_bound`.

From the prepared workspace, write that payload object to a JSON file and run:

```powershell
python agent_client.py --timeout 60 event --sequence 0 --kind closest_vector.coefficients --payload-file coefficients.json
```

The wall-clock budget is 600 seconds, including reading, solving, validation,
and receiving the terminal response. The request timeout does not extend that
budget. Acceptance or rejection is terminal, so the event cannot be retried.
Read only files inside the prepared workspace and public information returned
by the client.

## Rejections

Arthur rejects a wrong sequence or event kind; artifacts; missing or extra
payload fields; a non-array or incorrectly sized coefficient vector; any
non-integer or out-of-bound coefficient; or an exact squared distance greater
than the public radius. The corresponding stable reason codes are
`INVALID_SEQUENCE`, `INVALID_EVENT_KIND`, `INVALID_PAYLOAD`,
`CLOSEST_VECTOR_COEFFICIENT_COUNT_INVALID`,
`CLOSEST_VECTOR_COEFFICIENT_INVALID`, and
`CLOSEST_VECTOR_DISTANCE_EXCEEDED`. Resource expiry yields
`BUDGET_EXCEEDED`; any later event yields `SESSION_TERMINAL`.
