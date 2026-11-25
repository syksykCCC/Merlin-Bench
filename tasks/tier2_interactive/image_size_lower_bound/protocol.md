# Protocol summary

1. Send `image.begin` at sequence 0 with payload exactly `{}`.
2. Arthur returns `image.challenge` containing exactly 128 affine hashes.
3. Send `image.response` at sequence 1 with exactly 128 entries under
   `preimages`; each entry is `null` or a canonical `gf2-bits/hex-v1` input.
4. Arthur evaluates every non-null input and accepts iff at least 64 entries hit
   their corresponding buckets.

Artifacts, extra payload keys, malformed hexadecimal strings, incorrect padding,
wrong event kinds, or wrong phases terminate the run with rejection.
