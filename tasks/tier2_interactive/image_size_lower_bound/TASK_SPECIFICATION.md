# Task Specification: Boolean-Circuit Image-Size Lower Bound

This is the complete participant-facing specification for task
`t2.image_size_lower_bound`, version `0.1.0`. Every case uses the same Boolean
circuit problem, 128-lane affine-hash challenge, message sequence, and acceptance
rule. Solve the generated `instance.json`.

## 1. Mathematical problem

The public input describes a Boolean circuit

\[
F:\{0,1\}^m\longrightarrow\{0,1\}^n
\]

and a nonnegative integer `threshold_exponent` \(t\). Let
\(S=\operatorname{Im}F=\{F(x):x\in\{0,1\}^m\}\) and \(T=2^t\). The instance
is promised to satisfy exactly one side of the gap:

\[
|S|\ge 16T \quad\text{(YES)},
\qquad\text{or}\qquad
|S|\le T \quad\text{(NO)}.
\]

Scored instances are YES instances. You do not submit \(|S|\). Instead, Arthur
chooses 128 random affine buckets, and you find a circuit input whose output lies
in each bucket whenever possible.

All vector arithmetic below is over \(\mathbb F_2\): addition is XOR and matrix
multiplication uses XOR for addition and AND for multiplication.

## 2. Public circuit JSON

The public instance has exactly this shape:

```text
{
  "format_version": "aip-image-size/1",
  "circuit": {
    "num_inputs": m,
    "num_outputs": n,
    "gates": [Gate, ...],
    "outputs": [wire_id_0, ..., wire_id_(n-1)]
  },
  "threshold_exponent": t,
  "hash_lanes": 128
}

Gate =
  {"op": "const", "value": 0 or 1}
  {"op": "not", "input": wire_id}
  {"op": "xor", "left": wire_id, "right": wire_id}
  {"op": "and", "left": wire_id, "right": wire_id}
```

Input wires are numbered `0` through `m-1`. Gate array entry `q` produces wire
`m+q`. Every operand refers to a strictly earlier wire. The `outputs` array has
exactly `n` entries; entry `i` is output coordinate \(i\), and repeated wire
references are allowed. `not` maps 0 to 1 and 1 to 0. JSON booleans are never
integer bits.

## 3. Canonical `gf2-bits/hex-v1` codec

A length-\(q\) bit vector is packed into `ceil(q/8)` bytes. Coordinate `i` is bit
`i mod 8` (least-significant bit first) of byte `floor(i/8)`. Bytes then appear in
increasing byte-index order as exactly `2*ceil(q/8)` lowercase hexadecimal
characters. Unused high bits of the last byte must be zero.

Examples:

- length 4 vector `(1,0,1,0)` is word 5 and encodes as `"05"`;
- length 9 vector with only coordinates 0 and 8 set encodes as `"0101"`;
- for length 9, `"0103"` is invalid because the last byte has nonzero padding;
- uppercase, a `0x` prefix, whitespace, odd length, or a JSON bit array is invalid.

## 4. Affine buckets

Put \(k=t+2\). Lane \(j\) contains a uniformly random matrix
\(A_j\in\mathbb F_2^{k\times n}\) and target \(b_j\in\mathbb F_2^k\). It is
serialized as

```text
{
  "matrix_rows": [row_0, ..., row_(k-1)],
  "target": target
}
```

Every row uses `gf2-bits/hex-v1(n)` and `target` uses
`gf2-bits/hex-v1(k)`. A lane answer is an input \(x_j\in\{0,1\}^m\) satisfying

\[
A_jF(x_j)=b_j.
\]

The lane order is significant. You may use any preimage in a nonempty bucket;
there is no canonical-answer requirement.

## 5. Exact two-event protocol

The current `aip/1` transport is Merlin-request/Arthur-response. A logically
Arthur-first challenge is activated by an information-free begin event.

### 5.1 Sequence 0: begin

Submit kind `image.begin`, payload exactly `{}`, and no artifact references. Arthur
records the begin event before deriving randomness, then returns kind
`image.challenge` with payload `{"hashes": [...]}` containing exactly 128 hashes.

Any other event kind, any begin payload field, or any artifact is terminal malformed
input. Challenge randomness is public once returned; the committed PRG seed is
revealed only after terminal status for strict audit replay.

### 5.2 Sequence 1: response

Submit kind `image.response`, no artifacts, and payload exactly

```text
{"preimages": [entry_0, ..., entry_127]}
```

Every entry is either JSON `null`, meaning no preimage is claimed for that lane, or
a canonical `gf2-bits/hex-v1(m)` string. Arthur independently parses each non-null
input, evaluates every gate of \(F\), and checks its corresponding hash equation.
Arthur accepts if and only if at least 64 lanes are valid.

Fewer than 64 non-null entries is valid JSON syntax but returns terminal rejection
`IMAGE_SIZE_INSUFFICIENT_VALID_PREIMAGES`. Wrong preimages simply do not count.
Wrong length, invalid hex or padding, an extra field, a non-string/non-null entry,
an artifact, or a wrong event kind returns terminal rejection
`IMAGE_SIZE_MALFORMED_EVENT`. Acceptance uses reason `PROTOCOL_ACCEPT`. There is no
retry, replacement, or reset after sequence 1.

## 6. Using the supplied client

Inspect the live session without printing the connection secret:

```text
python agent_client.py --timeout 600 info
```

Request all hashes:

```text
python agent_client.py --timeout 600 event --sequence 0 --kind image.begin --payload "{}" > begin-response.json
```

Write the computed 128-entry payload to `answer.json`, then submit once:

```text
python agent_client.py --timeout 600 event --sequence 1 --kind image.response --payload-file answer.json
```

For a solver, keeping the large challenge in-process is safer:

```python
from agent_client import AgentClient

client = AgentClient.from_environment(timeout_seconds=600)
instance = client.get("instance")
reply = client.submit_event(
    sequence=0, kind="image.begin", payload={}, artifact_refs=[]
)
hashes = reply["reply"]["payload"]["hashes"]

# Implement this from the public circuit and all returned hashes.
preimages = solve(instance, hashes)
assert len(preimages) == 128

terminal = client.submit_event(
    sequence=1,
    kind="image.response",
    payload={"preimages": preimages},
    artifact_refs=[],
)
print(terminal["status"], terminal["reason_code"])
```

Do not advance your local sequence after a connection failure with unknown server
outcome. The current runtime does not promise that retransmitting an already
accepted participant event is idempotent.

## 7. Resource budget

The total wall-clock budget is 600 seconds with four CPU cores, 4,096 MiB memory,
and 4,096 MiB disk. The clock starts when Arthur loads the runtime. Reading files,
requesting the challenge, solving all lanes, serializing, final verification, and
receiving terminal status all share the same 10 minutes. A client HTTP timeout does
not extend that budget.
