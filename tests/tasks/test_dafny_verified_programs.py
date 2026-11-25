from __future__ import annotations

import hashlib

import pytest

from aipbench.tasks.dafny_verified_programs import (
    CASE_IDS,
    DAFNY_TOOLCHAIN,
    TASK_VERSION,
    DafnyVerifiedProgramsGenerator,
    _java_bin,
    find_dafny_executable,
    verify_dafny_solution,
)

REQUIRES_DAFNY = pytest.mark.skipif(
    find_dafny_executable() is None or _java_bin() is None,
    reason="Dafny 4.11 and Java are optional native test dependencies",
)


def _case(case_id: str, seed: bytes = b"d" * 32):
    return DafnyVerifiedProgramsGenerator().generate(
        instance_seed=seed, case_id=case_id, case_parameters={}
    )


def test_all_eight_dafny_cases_are_deterministic_and_publicly_bound() -> None:
    assert TASK_VERSION == "0.2.0"
    assert tuple(f"c{index:02d}" for index in range(1, 9)) == CASE_IDS
    digests: set[str] = set()
    for case_id in CASE_IDS:
        first = _case(case_id)
        second = _case(case_id)
        assert first.public_instance == second.public_instance
        assert first.private_instance == second.private_instance
        assert first.public_instance["toolchain"] == DAFNY_TOOLCHAIN
        assert first.public_instance["solution_module"] == "Solution"
        assert first.public_instance["challenge_source"].startswith("module Challenge")
        assert first.public_instance["harness_source"].startswith("module ArthurHarness")
        digests.add(str(first.public_instance["instance_sha256"]))
    assert len(digests) == 8


def test_seed_changes_dafny_executable_harness() -> None:
    first = _case("c04", hashlib.sha256(b"first").digest())
    second = _case("c04", hashlib.sha256(b"second").digest())
    assert first.public_instance["harness_sha256"] != second.public_instance["harness_sha256"]
    assert first.public_instance["instance_sha256"] != second.public_instance["instance_sha256"]


@REQUIRES_DAFNY
def test_native_dafny_accepts_reference_and_rejects_escape_source() -> None:
    generated = _case("c01")
    reference = str(generated.private_instance["reference_solution"]).encode("utf-8")
    result = verify_dafny_solution(
        public_instance=generated.public_instance,
        solution_content=reference,
        timeout_seconds=90,
    )
    assert "0 errors" in result.verify_stdout_tail
    forbidden = b"""module Solution {
  import opened Challenge
  method StablePartition(input: seq<int>) returns (output: seq<int>)
    ensures StablePartitionPost(input, output)
  { assume false; }
}
"""
    with pytest.raises(Exception, match="DAFNY_SOURCE_FORBIDDEN"):
        verify_dafny_solution(
            public_instance=generated.public_instance,
            solution_content=forbidden,
            timeout_seconds=30,
        )


@pytest.mark.parametrize("case_id", tuple(f"c{index:02d}" for index in range(2, 9)))
@REQUIRES_DAFNY
def test_contract_bearing_state_cases_accept_native_references(case_id: str) -> None:
    generated = _case(case_id)
    result = verify_dafny_solution(
        public_instance=generated.public_instance,
        solution_content=str(generated.private_instance["reference_solution"]).encode("utf-8"),
        timeout_seconds=90,
    )
    assert "0 errors" in result.verify_stdout_tail
    assert f"AIPBENCH_DAFNY_OK:{case_id}" in result.run_stdout_tail


@REQUIRES_DAFNY
def test_c06_harness_rejects_a_candidate_that_does_not_implement_the_trait() -> None:
    generated = _case("c06")
    bypass = b"""module Solution {
  import C = Challenge
  class Candidate {
    constructor() {}
  }
}
"""
    with pytest.raises(Exception, match="DAFNY_VERIFICATION_FAILED"):
        verify_dafny_solution(
            public_instance=generated.public_instance,
            solution_content=bypass,
            timeout_seconds=30,
        )
