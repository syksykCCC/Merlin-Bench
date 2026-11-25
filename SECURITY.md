# Evaluation trust and data handling

## Trust model

Merlin-Bench treats the participant Agent as Merlin and the runtime as Arthur. A score is valid only
when `official/result.json` has a valid Ed25519 signature and `official/audit.json` reports a full
disk replay. Agent-authored reports, stdout, stderr, and workspace files never affect scoring.

The local directory layout is not an operating-system sandbox. If the Agent can write `official/`
or `private/`, read Arthur memory, or replace the run-directory public key, the local trust model is
broken. Formal evaluation must isolate Arthur with a separate user, container, or host; expose only
`public/` plus an Agent-writable workspace; and pin Arthur's public key outside the run directory.

Use the external trust anchor during audit:

```text
merlin-bench audit <run-dir> --trusted-public-key <evaluation-owned-key-file>
```

## Protected data

- `private/` contains instance answers, generation metadata, the coin seed, bearer token, and local
  ephemeral signing key. It must never be mounted into the Agent workspace.
- `official/` is append/write-only for Arthur and the Auditor. The Agent must not be able to modify it.
- `workspace/` is Agent-writable, untrusted material and never contributes directly to scoring.
- `public/` is the Host's authoritative public input; only the required public files are copied into
  `workspace/` for the Agent.

Eval participant responses intentionally omit true answers, expected coefficients, private seeds,
and detailed numerical differences. Eval sessions are terminal and cannot be reset or resumed.

## External harness credentials

`scripts/run_harness.py` starts external model code with a minimal environment by default. Pass each
required provider credential or configuration variable with a separate `--inherit-env NAME`; do not
put credential values in command arguments. `--inherit-all-env` exists for compatibility but expands
the disclosure surface and should be avoided in formal evaluations.

The launcher does not write or print inherited values. The child harness can still access and expose
them, so treat its stdout, stderr, trajectory, crash dumps, and generated files as potentially
sensitive until they have been scanned. The one-shot `AIP_SESSION_TOKEN` is benchmark connection
material, not a provider key; it is loaded from the prepared connection file and expires with the run.

## Local observer

`arthur serve` provides a browser dashboard for human monitoring and prints its complete location as
`AIP_OBSERVER_URL`. The URL fragment carries a short-lived, read-only observer credential that is
independent from `AIP_SESSION_TOKEN`. The observer credential is accepted only by the summary API;
it cannot call participant endpoints, upload artifacts, or submit events. The page removes the
fragment from the address bar after reading it and keeps the credential only in tab-scoped session
storage.

The observer server summarizes data before returning it. It exposes task identity and a short public
statement, aggregate public-instance statistics, protocol progress, a bounded head-and-tail window
of pre-summarized interactions, the signed terminal decision, and an audit summary if one exists. It
does not return full graph edges, sparse terms, polynomial coefficients, flow assignments, raw event
payloads, private instances, seeds, signing material, or either bearer credential. This bounded view
prevents the dashboard from becoming an alternate bulk-data or secret-disclosure endpoint.

The observer URL is still a temporary secret because it reveals public evaluation activity. Keep
Arthur bound to loopback for the local workflow, do not put the URL in Agent workspaces, reports,
screenshots, issues, or shared shell logs, and close the page and server after the run. The dashboard
does not strengthen the same-user local sandbox and is not a scoring authority. A terminal `ACCEPT`
must be shown as pending until independent replay produces a valid `official/audit.json`; only signed
`ACCEPT` plus audit success is an official `PASS`.
