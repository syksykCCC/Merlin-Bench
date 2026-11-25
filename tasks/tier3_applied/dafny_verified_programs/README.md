# Dafny-Verified Programs

This Tier-3 task evaluates proof-carrying software rather than a standalone
answer.  Every case publishes a Dafny module containing the API and formal
contracts plus an Arthur-owned executable harness.  Merlin uploads a standard
`Solution.dfy` module whose concrete `Candidate` class implements the public
contract-bearing `Challenge.Candidate` trait.  Arthur invokes native Dafny
4.11.0 with its bundled Z3, then compiles the verified program to Java and
replays the harness.

The eight cases cover data processing, resource allocation, scheduling,
dependency/policy validation, and mutable-component state invariants.  The
participant artifact is ordinary Dafny source; there is no benchmark-specific
proof language.
