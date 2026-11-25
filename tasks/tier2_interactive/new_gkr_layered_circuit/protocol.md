# GKR `aip/1` Protocol Reference

All field values use `field61/hex-v1`: exactly 16 lowercase hexadecimal
characters decoding to an integer below \(2^{61}-1\).

1. `gkr.claim {"value": Field}`. Arthur replies `gkr.ready` without sampling.
2. For layer \(i\), let \(s=\log_2N_{i+1}\). For rounds
   `0 .. 2*s-1`, send
   `gkr.poly {"layer":i,"round":j,"coefficients":[q0,q1,q2]}`.
   Arthur checks `h(0)+h(1)` against the current claim, then returns
   `gkr.challenge {layer,round,point}`.
3. Send
   `gkr.reduce {"layer":i,"left_value":U,"right_value":V,
   "line_coefficients":[d0,...,ds]}`. Arthur checks the public wiring identity
   and `d(0)=U,d(1)=V`, then returns `gkr.line_challenge {layer,point}`.
4. Repeat for all layers. After the final line challenge, Arthur checks the
   resulting claim against the public input MLE and terminates.

The exact participant event count is

\[
1+\sum_i(2\log_2N_{i+1}+1).
\]

Payloads are exact and artifact-free. Any malformed event or failed identity is
terminal. Random points are sampled only after the polynomial that depends on
them has been bound into the transcript.
