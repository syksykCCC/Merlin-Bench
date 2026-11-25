# Task Specification

Task ID: `t3.dafny_verified_programs`. Version: `0.2.0`.

The public instance contains two UTF-8 Dafny modules:

- `challenge_source`, which defines the required API and its contracts;
- `harness_source`, which calls the required API on deterministic examples.

Submit exactly one UTF-8 artifact named conceptually `Solution.dfy`.  It must
define exactly one `module Solution`, import only `Challenge`, and define a
concrete `class Candidate extends Challenge.Candidate`.  That class must have
a constructor and implement every abstract method with the inherited public
contracts.  The source must use LF line endings and end in a newline.

Arthur concatenates the public challenge, the submitted module, and the fixed
harness.  The harness constructs the implementation through the public
`Challenge.Candidate` trait, so weakening or omitting a required contract is a
Dafny subtype error.  Arthur accepts only if native Dafny verifies every proof
obligation and the verified program compiles and emits the case's exact success
marker when the harness is executed.

The submitted module may not redefine public modules, declare a `Main` method,
perform I/O, include external files, use `assume`, `expect`, axioms, attributes
that disable or alter verification/compilation, external implementations, or a
wildcard termination exemption.  These restrictions keep the evidence inside
the Dafny verifier's ordinary trusted boundary.

Upload the source artifact, then send the one allowed event:

```json
{
  "sequence": 0,
  "kind": "dafny.program",
  "payload": {"instance_sha256": "<public instance digest>"},
  "artifact_refs": ["<uploaded artifact id>"]
}
```

There is no retry, preflight-verification endpoint, or participant-visible
checker diagnostic in evaluation mode.
