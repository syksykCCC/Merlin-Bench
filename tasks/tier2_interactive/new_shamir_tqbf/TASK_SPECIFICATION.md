# Task Specification: new Shamir-Style TQBF Interactive Proof

This is the complete participant-facing specification for task
`t2.new_shamir_tqbf`, version `0.1.0`. All six cases use the same public relation,
field codec, round schedule, and verifier.

You receive a true quantified Boolean formula as an acyclic Boolean circuit.
You must claim that it is true and then maintain a sequence of exact univariate
polynomial claims over a finite field. Arthur checks each polynomial before
sampling the next public-coin challenge. Acceptance after the last round proves
that every consistency check and the final circuit evaluation succeeded.

The run has one **600-second total wall-clock budget**. All work, network round
trips, and the final response share this budget; an HTTP timeout does not extend
it. This is one
evaluation attempt: a wrong or malformed claim or polynomial terminates the
session, and it cannot be corrected or retried in that run.

## 1. Public instance

The workspace file `instance.json` and `GET /v1/instance` return the same **bare
public object**; neither adds a `public_instance` wrapper. Its exact top-level
shape is:

```json
{
  "format_version": "aip-tqbf/1",
  "field_codec": "field61/hex-v1",
  "quantifiers": ["forall", "exists"],
  "circuit": {
    "num_inputs": 2,
    "gates": [{"op": "const", "value": 1}],
    "output": 2
  }
}
```

If `n = circuit.num_inputs`, then `quantifiers` has exactly `n` entries
and denotes

\[
Q_0x_0\;Q_1x_1\cdots Q_{n-1}x_{n-1}:C(x_0,\ldots,x_{n-1}).
\]

The outermost quantifier is array element 0; ordinary Boolean evaluation
eliminates the rightmost variable first. Input wire IDs are `0 .. n-1`. Gate
number `q` produces wire `n+q`, and every referenced wire ID must be smaller
than the output wire of that gate. A gate is exactly one of:

```json
{"op": "const", "value": 0}
```

```json
{"op": "not", "input": 0}
```

```json
{"op": "and", "left": 0, "right": 1}
```

```json
{"op": "or", "left": 0, "right": 1}
```

```json
{"op": "xor", "left": 0, "right": 1}
```

```json
{"op": "ite", "condition": 0, "zero": 1, "one": 2}
```

`ite` selects `zero` when its condition is 0 and `one` when it is 1. Every
object uses exactly its listed fields. Wire IDs, counts, round indices, stages,
degree bounds, and `remaining_barriers` are strict JSON integers; booleans and
floating-point values are not integers. The generated formula is promised to
be true, but you must still complete the proof protocol.

## 2. Field and canonical encoding

All arithmetic is in

\[
\mathbb F_p,\qquad p=2^{61}-1=2305843009213693951.
\]

One field element is a JSON string of exactly 16 lowercase hexadecimal digits,
interpreted most-significant digit first, whose integer value lies in
`0 .. p-1`. For example:

```text
0 -> "0000000000000000"
1 -> "0000000000000001"
```

JSON numbers, uppercase hexadecimal, `0x`, signs, short strings, and encodings
of `p` or larger are invalid. Using strings is essential because `p` exceeds
the JSON/JavaScript safe-integer range.

The arithmetization of the Boolean gates is:

\[
\begin{aligned}
\operatorname{NOT}(a)&=1-a,\\
\operatorname{AND}(a,b)&=ab,\\
\operatorname{OR}(a,b)&=a+b-ab,\\
\operatorname{XOR}(a,b)&=a+b-2ab,\\
\operatorname{ITE}(c,a,b)&=(1-c)a+cb.
\end{aligned}
\]

All additions, subtractions, multiplications, powers, and equalities in the
remainder of this specification are modulo `p`.

## 3. Event envelope and response envelope

Every participant event is an HTTP `POST /v1/events` JSON object:

```json
{
  "api_version": "aip/1",
  "session_id": "<session-id from GET /v1/session>",
  "sequence": 0,
  "kind": "tqbf.claim",
  "payload": {"value": "0000000000000001"},
  "artifact_refs": []
}
```

`api_version` is always `aip/1`. `sequence` starts at 0 and increases by one
for every participant event. `artifact_refs` must be the empty array on every
round: this task accepts no uploaded artifact. `agent_client.py event` fills in
`api_version` and `session_id`; its payload file contains only `payload`.

Arthur's HTTP response always has these logical fields:

```json
{
  "api_version": "aip/1",
  "public_state": {},
  "reason_code": null,
  "reply": {"kind": "...", "payload": {}},
  "sequence": 0,
  "session_id": "<session-id>",
  "status": "CONTINUE",
  "receipt": {"event_hash": "sha256:<64 lowercase hexadecimal digits>"}
}
```

For a nonterminal response, `status` is `CONTINUE` and `reply` contains the next
round or challenge. A terminal response has `status` equal to `ACCEPT`,
`REJECT`, or `TIMEOUT`; its `reply` is `null`.

## 4. Initial claim

The only valid sequence-0 event has `kind = "tqbf.claim"`, no artifact, and the
exact one-field payload:

```json
{"value": "0000000000000001"}
```

Arthur rejects any other value. On success Arthur returns a `tqbf.round` reply:

```json
{
  "kind": "tqbf.round",
  "payload": {
    "round": {
      "round_index": 0,
      "stage": 1,
      "operator": "exists",
      "variable": 0,
      "degree_bound": 1,
      "remaining_barriers": 1
    }
  }
}
```

The numbers above are illustrative. Always use the values Arthur actually
returns.

## 5. Polynomial rounds

For the public round with `round_index = q`, send sequence `q+1`, kind
`tqbf.polynomial`, no artifact, and exactly this payload shape:

```json
{
  "round_index": 0,
  "coefficients": [
    "0000000000000000",
    "0000000000000001"
  ]
}
```

If Arthur publishes `degree_bound = d`, the coefficient array must have exactly
`d+1` entries, including trailing zero coefficients. The increasing-power
convention is

\[
h(T)=c_0+c_1T+\cdots+c_dT^d.
\]

Let `v` be the current claim, let `h0 = h(0) = c_0`, and let
`h1 = h(1) = sum(coefficients)`. Arthur checks exactly one anchor equation:

\[
\begin{array}{ll}
\texttt{reduce}:&v=(1-a_j)h0+a_jh1,\\
\texttt{forall}:&v=h0h1,\\
\texttt{exists}:&v=h0+h1-h0h1,
\end{array}
\]

where `j = round.variable` and `a_j` is Arthur's current field coordinate for
that variable. Only after this check succeeds does Arthur sample a fresh random
`r`, replace `a_j` by `r`, and replace the current claim by `h(r)`.

If another round remains, the response reply is:

```json
{
  "kind": "tqbf.challenge",
  "payload": {
    "round_index": 0,
    "point": "0123456789abcdef",
    "next_round": {
      "round_index": 1,
      "stage": 2,
      "operator": "reduce",
      "variable": 0,
      "degree_bound": 2,
      "remaining_barriers": 2
    }
  }
}
```

The point shown is only a shape example. It is unpredictable until Arthur has
accepted the polynomial. On the final round Arthur still samples `r`, evaluates
the public arithmetized circuit at the accumulated coordinates, and requires it
to equal `h(r)`. The final response is terminal and has no challenge reply.

## 6. What polynomial to compute

Let `P_n` be the polynomial obtained by arithmetizing the public circuit. For a
variable `X_j`, define multilinearization

\[
R_j(f)=(1-X_j)f\vert_{X_j=0}+X_jf\vert_{X_j=1}.
\]

Starting with `P_n`, eliminate variables from right to left. At stage `i`, the
quantifier for `X_{i-1}` combines the restrictions by

\[
\begin{aligned}
\forall &: f(0)f(1),\\
\exists &: f(0)+f(1)-f(0)f(1),
\end{aligned}
\]

and then applies `R_j` to each still-outer variable. The interactive schedule
reveals these operations in the reverse dependency order:

```text
stage 1: quantifier variable 0
stage 2: reduce variable 0; quantifier variable 1
stage 3: reduce variables 0,1; quantifier variable 2
...
```

Thus there are exactly `n(n+1)/2` polynomial rounds. For the current round,
fix every coordinate other than `round.variable` to Arthur's accumulated field
coordinates and output the univariate restriction in that variable.

`degree_bound` is a public syntactic upper bound, not necessarily the actual
degree. For stages below `n`, a quantifier round has bound 1 and a reduction
round has bound 2. At stage `n`, let `mu[j]` be the public circuit output's
syntactic individual degree in `X_j`; the quantifier bound is `mu[n-1]` and a
reduction bound for `j` is `2*mu[j]`. Bounds never exceed 64. Even when the
actual polynomial is constant, send all `degree_bound+1` cells.

## 7. Reason codes

The stable task outcomes are:

| Reason code | Meaning |
|---|---|
| `PROTOCOL_ACCEPT` | Every anchor and the final circuit oracle check passed. |
| `TQBF_MALFORMED_EVENT` | Wrong kind, exact fields, round index, coefficient count/codec, phase, or nonempty artifacts. |
| `TQBF_CLAIM_NOT_TRUE` | The sequence-0 field claim was not exactly one. |
| `TQBF_ANCHOR_FAILED` | The polynomial's values at 0 and 1 do not produce the current claim. |
| `TQBF_FINAL_ORACLE_MISMATCH` | The final randomized polynomial value differs from the direct public-circuit evaluation. |
| `INVALID_SEQUENCE` | The outer event sequence was not the expected strict integer. |
| `BUDGET_EXCEEDED` | The total wall time, event count, or another run resource was exhausted. |
| `SESSION_TERMINAL` | A request was made after the run had already terminated. |
