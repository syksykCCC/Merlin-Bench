# Protocol summary

The participant first submits `sumcheck.claim`. Arthur then accepts exactly one `sumcheck.poly`
message per public variable, sampling a fresh field challenge only after each anchor succeeds. The
last challenge is checked against a direct evaluation of the public factor multilinear extensions.

`TASK_SPECIFICATION.md` is the authoritative participant-facing definition.
