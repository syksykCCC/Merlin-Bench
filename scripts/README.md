# Script index

- `prepare_evaluation.py` creates a host run and participant workspace for a selected task, case, and seed.
- `run_harness.py` launches an external model harness against a prepared workspace.
- `check_documentation.py` validates local links, task documentation, catalog consistency, case YAML, and manifests.
- `reference_new_list_homomorphism_c03.py`, `c04.py`, and `c05.py` provide public-instance reference solvers used by the benchmark's example agent.
- `reference_new_shamir_blocked.py` provides a public-instance reference for blocked-tail Shamir cases.

- `prepare_tier3_plus.py --list` lists the 24 extension fixtures; `--fixture lean-01` prepares one using the standard workspace contract.
- `check_release.py` validates the complete 124-point inventory, fixture integrity, English text, and release contents.
