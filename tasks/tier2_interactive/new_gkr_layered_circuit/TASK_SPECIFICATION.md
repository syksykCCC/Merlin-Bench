# Task Specification: new GKR Layered Arithmetic-Circuit Evaluation

This is the complete participant-facing specification for task
`t2.new_gkr_layered_circuit`, version `0.1.0`. Every test case uses the same public
circuit language, field encoding, message sequence, and verifier. The generated
`instance.json` is the circuit to prove.

## 1. Mathematical problem

All arithmetic is in

\[
\mathbb F_p,\qquad p=2^{61}-1.
\]

The public input is a strictly layered fan-in-two arithmetic circuit. Layers are
numbered from the scalar output towards the inputs:

\[
V_0,V_1,\ldots,V_L,
\qquad |V_i|=N_i=2^{s_i},\qquad N_0=1.
\]

`input_values` gives the entire table \(V_L\). For every layer \(i<L\) and
position \(g\in[0,N_i)\), the public gate table gives field elements \(a,b,c\)
and child positions `left`, `right` in layer \(i+1\). Its value is

\[
V_i(g)=aV_{i+1}(\mathrm{left})
      +bV_{i+1}(\mathrm{right})
      +cV_{i+1}(\mathrm{left})V_{i+1}(\mathrm{right})\pmod p.
\tag{1}
\]

The required initial answer is the unique scalar output \(y=V_0(0)\). Merely
sending \(y\) is not sufficient: you must complete the GKR interaction proving
that this value follows from the public gate table.

The public gate table is authoritative.

## 2. Index and field encodings

### 2.1 LSB-first positions

For a width \(N=2^s\), integer position \(j\) represents the Boolean vector

\[
\operatorname{bits}_s(j)=(j_0,\ldots,j_{s-1}),
\qquad j=\sum_{k=0}^{s-1}j_k2^k.
\]

The first MLE coordinate is therefore the least significant bit. This convention
applies to gate positions and both child positions.

### 2.2 `field61/hex-v1`

Every mathematical field value in an instance or protocol message is exactly 16
lowercase hexadecimal characters. The string is ordinary most-significant-digit
first integer text and must decode to a value strictly below (p).

- zero: `0000000000000000`;
- one: `0000000000000001`;
- minus one modulo (p): `1ffffffffffffffe`;
- the modulus metadata: `1fffffffffffffff`, which is **not** a valid field element.

Uppercase, a `0x` prefix, short strings, signed strings, JSON numbers, booleans,
and values at least (p) are invalid. Perform all intermediate arithmetic modulo
(p); never use floating point.

## 3. Public instance JSON

```text
{
  "format_version": "aip-gkr-instance/1",
  "field": {
    "modulus_hex": "1fffffffffffffff",
    "element_codec": "field61/hex-v1"
  },
  "index_bits": "lsb_first",
  "layer_widths": [1, N_1, ..., N_L],
  "layers": [Layer_0, ..., Layer_(L-1)],
  "input_values": [Field; N_L]
}

Layer_i {
  "output_width": N_i,
  "child_width": N_(i+1),
  "gates": [Gate; N_i]
}

Gate {
  "a": Field,
  "b": Field,
  "c": Field,
  "left": integer in [0, N_(i+1)),
  "right": integer in [0, N_(i+1))
}
```

Every width is a positive power of two, all array lengths agree exactly, the
first width is one, and no edge skips a layer.

## 4. Multilinear extensions and the layer identity

For \(z\in\mathbb F^s\) and Boolean position \(b\in\{0,1\}^s\), define

\[
\operatorname{eq}_s(z,b)=
\prod_{k=0}^{s-1}\bigl((1-z_k)(1-b_k)+z_kb_k\bigr).
\]

The multilinear extension of a table \(V_i\) is

\[
\widetilde V_i(z)=
\sum_{g=0}^{N_i-1}
\operatorname{eq}_{s_i}(z,\operatorname{bits}_{s_i}(g))V_i(g).
\tag{2}
\]

For current point \(r\in\mathbb F^{s_i}\), define the three public wiring MLEs

\[
\begin{aligned}
\widetilde A_i(r,u,v)&=\sum_g \operatorname{eq}(r,g)a_i(g)
 \operatorname{eq}(u,\lambda_i(g))\operatorname{eq}(v,\rho_i(g)),\\
\widetilde B_i(r,u,v)&=\sum_g \operatorname{eq}(r,g)b_i(g)
 \operatorname{eq}(u,\lambda_i(g))\operatorname{eq}(v,\rho_i(g)),\\
\widetilde M_i(r,u,v)&=\sum_g \operatorname{eq}(r,g)c_i(g)
 \operatorname{eq}(u,\lambda_i(g))\operatorname{eq}(v,\rho_i(g)).
\end{aligned}
\tag{3}
\]

All gate and child arguments in (3) use the LSB-first Boolean vectors defined
above. If the current claim is \(C_i=\widetilde V_i(r)\), then

\[
C_i=\sum_{u,v\in\{0,1\}^{s_{i+1}}}F_i(r,u,v),
\tag{4}
\]

where

\[
F_i=\widetilde A_i\widetilde V_{i+1}(u)
   +\widetilde B_i\widetilde V_{i+1}(v)
   +\widetilde M_i\widetilde V_{i+1}(u)\widetilde V_{i+1}(v).
\]

Each coordinate of \(F_i\) has degree at most two.

## 5. Exact protocol

The `sequence` number counts only your events. Every payload has an exact field
set; extra fields, artifacts, wrong labels, wrong lengths, or wrong phases are
terminal errors. The session has no retry.

### 5.1 Initial claim

At sequence 0 submit

```json
{"value": "0000000000000000"}
```

with kind `gkr.claim`, replacing the displayed zero with the encoded circuit
output. Arthur sets \(r_0\) to the empty vector and \(C_0=y\), and replies

```json
{"kind":"gkr.ready","payload":{"layer":0,"round":0}}
```

No random field element is sampled at this step.

### 5.2 Sum-Check for layer \(i\)

Let \(s=s_{i+1}=\log_2N_{i+1}\). Variables are processed in this exact order:

\[
u_0,u_1,\ldots,u_{s-1},v_0,v_1,\ldots,v_{s-1}.
\]

For round \(j=0,\ldots,2s-1\), compute the honest univariate polynomial

\[
h_j(X)=\sum_{\text{remaining Boolean suffix}}F_i
\]

after substituting all earlier Arthur challenges and \(X\) for the current
variable. Send kind `gkr.poly`:

```json
{
  "layer": 0,
  "round": 0,
  "coefficients": ["q0", "q1", "q2"]
}
```

The coefficient vector is increasing-power order:
\(h_j(X)=q_0+q_1X+q_2X^2\). Always send exactly three canonical field strings,
including high zero coefficients. Arthur first checks

\[
h_j(0)+h_j(1)=C.
\]

Only after your polynomial is recorded does Arthur sample a fresh point and
reply with

```json
{
  "kind":"gkr.challenge",
  "payload":{"layer":0,"round":0,"point":"0000000000000002"}
}
```

Update \(C\leftarrow h_j(\text{point})\). The displayed point is only an
example; use the actual reply.

If a child layer has width one, then \(s=0\): that layer has zero `gkr.poly`
events. Its left and right points are both the empty vector, and you proceed
directly from `gkr.ready` or the previous `gkr.line_challenge` to
`gkr.reduce`, whose `line_coefficients` array has exactly one entry.

### 5.3 Line reduction

After all \(2s\) rounds, their challenges form
\(u^*,v^*\in\mathbb F^s\). Compute

\[
U=\widetilde V_{i+1}(u^*),\qquad
V=\widetilde V_{i+1}(v^*),
\]

and the degree-at-most-(s) polynomial

\[
d(T)=\widetilde V_{i+1}(u^*+T(v^*-u^*)).
\]

Send kind `gkr.reduce`:

```json
{
  "layer": 0,
  "left_value": "U",
  "right_value": "V",
  "line_coefficients": ["d0", "d1", "...", "ds"]
}
```

Send exactly (s+1) increasing-power coefficients, retaining high zeroes.
Arthur independently evaluates the public wiring table and checks

\[
C=\widetilde A_iU+\widetilde B_iV+\widetilde M_iUV,
\qquad d(0)=U,\qquad d(1)=V.
\]

After recording this message, Arthur samples a fresh \(t_i\) and replies

```json
{"kind":"gkr.line_challenge","payload":{"layer":0,"point":"..."}}
```

Set

\[
r_{i+1}=u^*+t_i(v^*-u^*),\qquad C_{i+1}=d(t_i),
\]

then continue with layer (i+1). The final layer also returns its line
challenge. Arthur directly evaluates the public input MLE at \(r_L\), and
accepts exactly when it equals \(C_L\).

The total number of your events is

\[
1+\sum_{i=0}^{L-1}(2s_{i+1}+1).
\]

`GET /v1/protocol` reports `total_merlin_events` and `total_barriers` for the
actual circuit.

## 6. Rejection reasons

- `GKR_MALFORMED_EVENT`: wrong phase/kind/label, extra or missing fields,
  artifact references, noncanonical field strings, or wrong array lengths.
- `GKR_CHECK_FAILED`: a Sum-Check endpoint identity, wiring identity, line
  endpoint, or final input-MLE check failed.

Both are terminal and intentionally do not identify the first algebraic field
that differed during evaluation mode.

## 7. Resource budget and operational rules

The complete run has one shared 600-second wall-clock budget, four CPU cores,
4,096 MiB RAM, 4,096 MiB disk, at most 513 participant events, and no protocol
artifacts. The clock includes reading the instance, circuit evaluation, all
interaction, final verification, and receiving terminal status.

An HTTP timeout changes only how long one request waits; it does not extend the
global budget.
