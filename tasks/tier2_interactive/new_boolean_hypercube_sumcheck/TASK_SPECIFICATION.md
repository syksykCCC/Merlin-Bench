# Task Specification: new Boolean-Hypercube Polynomial Sum-Check

This document defines task `t2.new_boolean_hypercube_sumcheck`, version `0.1.0`.
The run is a one-shot public-coin interaction with a 600-second total wall-clock budget.
Reading, computation, requests, and Arthur's terminal verification all count toward that same limit.

## 1. Public relation

All arithmetic is in

\[
\mathbb F_p,\qquad p=2^{61}-1.
\]

The public instance contains Boolean variables \(x_0,\ldots,x_{m-1}\) and a nonempty array of
factors. A factor has an ordered scope of distinct variable IDs
\(S_a=(s_{a,0},\ldots,s_{a,k_a-1})\) and a table
\(f_a:\{0,1\}^{k_a}\to\mathbb F_p\). Its array index is little-endian in scope position:

\[
\operatorname{index}(b_0,\ldots,b_{k_a-1})=\sum_{j=0}^{k_a-1}b_j2^j.
\]

The multilinear extension of a table is

\[
\widetilde f_a(y)=\sum_{b\in\{0,1\}^{k_a}}f_a(b)
\prod_{j=0}^{k_a-1}\bigl(b_jy_j+(1-b_j)(1-y_j)\bigr).
\]

Define

\[
g(x)=\prod_a\widetilde f_a(x|_{S_a}),\qquad
Z=\sum_{b\in\{0,1\}^m}g(b)\pmod p.
\]

The task is to claim the exact value \(Z\) and complete the Sum-Check transcript. Arthur does not
compare the claim with a stored answer; it checks the transcript and directly evaluates the public
factors at the final random point.

## 2. Public-instance fields

`instance.json` is one bare JSON object with exactly these fields:

| Path | Type and meaning |
|---|---|
| `format_version` | the string `aip-sumcheck-instance/1` |
| `field.modulus` | the string `1fffffffffffffff` |
| `field.codec` | the string `field61/hex-v1` |
| `num_variables` | strict integer \(m\) |
| `factors` | nonempty array of factor objects |
| `factors[*].scope` | nonempty array of distinct strict integer IDs in `[0,m)` |
| `factors[*].values` | exactly \(2^{|\mathrm{scope}|}\) field strings |

Objects have no fields beyond those listed. Different factors may have identical scopes and are
still separate multiplicative factors.

## 3. Field codec

One field element is a JSON string of exactly 16 lowercase hexadecimal characters whose ordinary
most-significant-digit-first integer value lies in `0 .. p-1`. Uppercase text, prefixes, signs,
short or long strings, JSON numbers, and the encoding of \(p\) or a larger integer are invalid.

## 4. Event order

Participant event sequence numbers start at 0 and increase by one. Every event uses the `aip/1`
envelope supplied by `agent_client.py`; `artifact_refs` must always be empty. An invalid sequence,
kind, phase, field set, type, codec value, or artifact reference is terminal.

Choose a permutation \(\sigma=(\sigma_0,\ldots,\sigma_{m-1})\) of all public variable IDs and write
\(z_i=x_{\sigma_i}\).

### 4.1 Claim

At sequence 0 submit kind `sumcheck.claim` with exactly:

| Payload field | Required value |
|---|---|
| `variable_order` | the array \([\sigma_0,\ldots,\sigma_{m-1}]\) |
| `claimed_sum` | the canonical field encoding of \(Z\) |

Arthur replies with kind `sumcheck.ready`. Its payload contains `num_rounds = m` and
`degree_bound = 5`. No challenge is sampled for the claim.

### 4.2 Polynomial rounds

At zero-based round \(i\), after receiving earlier points \(r_0,\ldots,r_{i-1}\), define

\[
q_i(T)=\sum_{z_{i+1},\ldots,z_{m-1}\in\{0,1\}}
g(r_0,\ldots,r_{i-1},T,z_{i+1},\ldots,z_{m-1}).
\]

At sequence \(i+1\), submit kind `sumcheck.poly` with exactly:

| Payload field | Required value |
|---|---|
| `round_index` | the strict integer \(i\) |
| `coefficients` | exactly six canonical field strings \([c_0,\ldots,c_5]\) |

The coefficient order is increasing power:

\[
q_i(T)=c_0+c_1T+\cdots+c_5T^5.
\]

Include trailing zero coefficients. Before sampling a challenge, Arthur checks

\[
q_i(0)+q_i(1)=C_i,
\]

where \(C_0\) is the claimed sum and \(C_i=q_{i-1}(r_{i-1})\) thereafter. On success it samples
a fresh uniform \(r_i\in\mathbb F_p\) and returns kind `sumcheck.challenge` with payload fields
`round_index = i` and `point`, the canonical field encoding of \(r_i\).

After the last round, Arthur restores the challenge values to their public variable coordinates,
directly computes \(g\) from the public tables, and accepts exactly when

\[
q_{m-1}(r_{m-1})=g(r_0,\ldots,r_{m-1}).
\]

The final challenge is included in the same terminal response. A rejected or timed-out session
cannot be corrected or retried.

## 5. Outcomes and resources

Stable task reason codes are `PROTOCOL_ACCEPT`, `SUMCHECK_MALFORMED_EVENT`,
`SUMCHECK_ANCHOR_FAILED`, and `SUMCHECK_FINAL_CHECK_FAILED`; the runtime can additionally report
`INVALID_SEQUENCE`, `BUDGET_EXCEEDED`, or `SESSION_TERMINAL`.

The total budget is 600 seconds, four CPU cores, 4,096 MiB memory, 4,096 MiB disk, at most 401
participant events, and no participant artifact. An HTTP-client timeout only limits that request;
it does not extend the global deadline.
