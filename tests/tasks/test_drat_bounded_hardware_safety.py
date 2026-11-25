from __future__ import annotations

import hashlib

import pytest

from aipbench.tasks.drat_bounded_hardware_safety import (
    CASE_IDS,
    DratBoundedHardwareGenerator,
    find_cadical_executable,
    find_drat_trim_executable,
    solve_public_instance,
    verify_drat_proof,
)

REQUIRES_DRAT = pytest.mark.skipif(
    find_drat_trim_executable() is None,
    reason="drat-trim is an optional native test dependency",
)
REQUIRES_DRAT_TOOLCHAIN = pytest.mark.skipif(
    find_drat_trim_executable() is None or find_cadical_executable() is None,
    reason="CaDiCaL and drat-trim are optional native test dependencies",
)


def _case(case_id: str, seed: bytes = b"h" * 32):
    return DratBoundedHardwareGenerator().generate(
        instance_seed=seed, case_id=case_id, case_parameters={}
    )


def test_all_eight_hardware_cases_publish_standard_aiger_and_dimacs() -> None:
    assert tuple(f"c{index:02d}" for index in range(1, 9)) == CASE_IDS
    for case_id in CASE_IDS:
        generated = _case(case_id)
        public = generated.public_instance
        assert str(public["aiger_aag"]).startswith("aag ")
        assert "\np cnf " in str(public["bound_cnf"])
        assert int(public["bound"]) >= 20
        assert int(public["num_cnf_variables"]) > 0
        assert int(public["num_cnf_clauses"]) > 0


def test_hardware_seed_changes_bounded_instance() -> None:
    first = _case("c08", hashlib.sha256(b"first").digest())
    second = _case("c08", hashlib.sha256(b"second").digest())
    assert first.public_instance["instance_sha256"] != second.public_instance["instance_sha256"]


@pytest.mark.parametrize("case_id", CASE_IDS)
@REQUIRES_DRAT_TOOLCHAIN
def test_cadical_reference_is_accepted_by_native_drat_trim(case_id: str) -> None:
    generated = _case(case_id)
    proof = solve_public_instance(generated.public_instance)
    assert 0 < len(proof) <= 16_777_216
    result = verify_drat_proof(
        public_instance=generated.public_instance,
        proof_content=proof,
        timeout_seconds=90,
    )
    assert "s VERIFIED" in result.stdout_tail


@REQUIRES_DRAT
def test_invalid_drat_is_rejected() -> None:
    generated = _case("c01")
    with pytest.raises(Exception, match="DRAT_PROOF_INVALID"):
        verify_drat_proof(
            public_instance=generated.public_instance,
            proof_content=b"1 0\n",
            timeout_seconds=30,
        )


@REQUIRES_DRAT
def test_c04_requires_a_nonempty_proof_for_nondeterministic_advance() -> None:
    generated = _case("c04", bytes.fromhex("c4" * 32))
    public = generated.public_instance
    assert public["public_features"] == {
        "component": "arbiter",
        "agents": 8,
        "horizon": 22,
    }
    assert "advance" in str(public["aiger_aag"])
    with pytest.raises(Exception, match="DRAT_PROOF_INVALID"):
        verify_drat_proof(
            public_instance=public,
            proof_content=b"0\n",
            timeout_seconds=30,
        )


@REQUIRES_DRAT
def test_c06_uses_independent_actual_and_shadow_credit_trackers() -> None:
    generated = _case("c06", bytes.fromhex("c6" * 32))
    public = generated.public_instance
    aiger = str(public["aiger_aag"])
    assert "actual_credit_0" in aiger
    assert "shadow_credit_0" in aiger
    assert int(public["num_cnf_variables"]) == 14_883
    assert int(public["num_cnf_clauses"]) == 42_220
    with pytest.raises(Exception, match="DRAT_PROOF_INVALID"):
        verify_drat_proof(
            public_instance=public,
            proof_content=b"0\n",
            timeout_seconds=30,
        )


@REQUIRES_DRAT
def test_c07_flush_drain_monitor_is_not_unit_propagation_trivial() -> None:
    generated = _case("c07", bytes.fromhex("c7" * 32))
    public = generated.public_instance
    aiger = str(public["aiger_aag"])
    assert "flush_progress_10" in aiger
    assert int(public["num_cnf_variables"]) == 4_488
    assert int(public["num_cnf_clauses"]) == 12_354
    with pytest.raises(Exception, match="DRAT_PROOF_INVALID"):
        verify_drat_proof(
            public_instance=public,
            proof_content=b"0\n",
            timeout_seconds=30,
        )
