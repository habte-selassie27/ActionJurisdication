"""Direct-mode behavioral tests for ActionJurisdication.

The suite proves that semantic consensus only selects jurisdiction while all
actual authority, thresholds, distinct-signer constraints, immutability, and
exact action/context binding remain deterministic.
"""

import json

CONTRACT = "contracts/actionjurisdication.py"
CLASSIFIER = r"You are classifying which independent authority dimensions"
CTX = "11" * 32
ACTION = "22" * 32
ACTION_2 = "33" * 32


def keccak_text(value):
    from Crypto.Hash import keccak
    digest = keccak.new(digest_bits=256)
    digest.update(value.encode())
    return digest.hexdigest()


def commitment(context_hash, action_hash, description_hash):
    payload = json.dumps({
        "domain": "ActionJurisdication.action-commitment.v1",
        "context_hash": context_hash,
        "action_hash": action_hash,
        "description_hash": description_hash,
    }, sort_keys=True, separators=(",", ":"))
    return keccak_text(payload)


def classification(status="IN_SCOPE", dimensions=None, reason="relevant authority dimensions identified"):
    return json.dumps({
        "status": status,
        "dimensions": dimensions if dimensions is not None else ["money"],
        "reason": reason,
    })


def create_matrix(contract, owner, alice, bob, *, min_distinct=1, proposer_may_approve=True):
    matrix_id = contract.actionjurisdication_create_matrix(
        "Treasury authority",
        "Separate financial, security, and data authority for operational actions.",
        min_distinct,
        proposer_may_approve,
    )
    money = contract.actionjurisdication_add_dimension(
        matrix_id,
        "money",
        "Review spending, transfers, amounts, pricing, and financial exposure.",
        1,
    )
    security = contract.actionjurisdication_add_dimension(
        matrix_id,
        "security",
        "Review security-sensitive access, credentials, privileged systems, and attack surface.",
        1,
    )
    data = contract.actionjurisdication_add_dimension(
        matrix_id,
        "data",
        "Review disclosure, processing, movement, or exposure of customer or confidential data.",
        1,
    )
    contract.actionjurisdication_add_approver(matrix_id, money, owner)
    contract.actionjurisdication_add_approver(matrix_id, money, alice)
    contract.actionjurisdication_add_approver(matrix_id, security, bob)
    contract.actionjurisdication_add_approver(matrix_id, data, alice)
    contract.actionjurisdication_seal_matrix(matrix_id)
    return matrix_id, money, security, data


def open_and_classify(contract, direct_vm, matrix_id, dimensions, *, action_hash=ACTION, description=None):
    direct_vm.mock_llm(CLASSIFIER, classification(dimensions=dimensions))
    action_id = contract.actionjurisdication_open_action(
        matrix_id,
        CTX,
        action_hash,
        description or "Pay 40 GEN for a penetration test that uses customer-derived test fixtures.",
    )
    contract.actionjurisdication_classify_action(action_id)
    return action_id


def test_matrix_starts_as_draft(direct_vm, direct_deploy):
    contract = direct_deploy(CONTRACT, sdk_version="v0.2.16")
    matrix_id = contract.actionjurisdication_create_matrix("Ops", "Operational separation of duties.", 1, True)
    matrix = contract.actionjurisdication_get_matrix(matrix_id)
    assert matrix["status"] == 0
    assert matrix["sealed"] is False
    assert matrix["definition_hash"] == ""


def test_only_owner_can_modify_draft(direct_vm, direct_deploy, direct_alice):
    contract = direct_deploy(CONTRACT, sdk_version="v0.2.16")
    matrix_id = contract.actionjurisdication_create_matrix("Ops", "Operational separation of duties.", 1, True)
    with direct_vm.prank(direct_alice):
        with direct_vm.expect_revert("only matrix owner"):
            contract.actionjurisdication_add_dimension(matrix_id, "money", "Review financial exposure.", 1)


def test_dimension_keys_are_unique_and_slug_like(direct_vm, direct_deploy):
    contract = direct_deploy(CONTRACT, sdk_version="v0.2.16")
    matrix_id = contract.actionjurisdication_create_matrix("Ops", "Operational separation of duties.", 1, True)
    contract.actionjurisdication_add_dimension(matrix_id, "money", "Review financial exposure.", 1)
    with direct_vm.expect_revert("already exists"):
        contract.actionjurisdication_add_dimension(matrix_id, "money", "Duplicate.", 1)
    with direct_vm.expect_revert("slug-like"):
        contract.actionjurisdication_add_dimension(matrix_id, "bad key", "Invalid key.", 1)


def test_matrix_cannot_seal_with_unsatisfied_threshold(direct_vm, direct_deploy):
    contract = direct_deploy(CONTRACT, sdk_version="v0.2.16")
    matrix_id = contract.actionjurisdication_create_matrix("Ops", "Operational separation of duties.", 1, True)
    contract.actionjurisdication_add_dimension(matrix_id, "money", "Review financial exposure.", 2)
    with direct_vm.expect_revert("threshold must be satisfiable"):
        contract.actionjurisdication_seal_matrix(matrix_id)


def test_matrix_cannot_seal_if_global_distinct_requirement_is_impossible(
    direct_vm, direct_deploy, direct_alice
):
    contract = direct_deploy(CONTRACT, sdk_version="v0.2.16")
    matrix_id = contract.actionjurisdication_create_matrix("Ops", "Operational separation of duties.", 2, True)
    d = contract.actionjurisdication_add_dimension(matrix_id, "money", "Review financial exposure.", 1)
    contract.actionjurisdication_add_approver(matrix_id, d, direct_alice)
    with direct_vm.expect_revert("distinct approver requirement is unsatisfiable"):
        contract.actionjurisdication_seal_matrix(matrix_id)


def test_sealed_matrix_is_immutable(direct_vm, direct_deploy, direct_alice, direct_bob):
    contract = direct_deploy(CONTRACT, sdk_version="v0.2.16")
    owner = direct_vm.sender
    matrix_id, _, _, _ = create_matrix(contract, owner, direct_alice, direct_bob)
    with direct_vm.expect_revert("sealed and immutable"):
        contract.actionjurisdication_add_dimension(matrix_id, "legal", "Review legal exposure.", 1)


def test_seal_creates_definition_hash(direct_vm, direct_deploy, direct_alice, direct_bob):
    contract = direct_deploy(CONTRACT, sdk_version="v0.2.16")
    owner = direct_vm.sender
    matrix_id, _, _, _ = create_matrix(contract, owner, direct_alice, direct_bob)
    matrix = contract.actionjurisdication_get_matrix(matrix_id)
    assert matrix["sealed"] is True
    assert len(matrix["definition_hash"]) == 64
    assert len(matrix["dimensions"]) == 3


def test_action_rejects_non_hex_commitments(direct_vm, direct_deploy, direct_alice, direct_bob):
    contract = direct_deploy(CONTRACT, sdk_version="v0.2.16")
    owner = direct_vm.sender
    matrix_id, _, _, _ = create_matrix(contract, owner, direct_alice, direct_bob)
    with direct_vm.expect_revert("context_hash"):
        contract.actionjurisdication_open_action(matrix_id, "bad", ACTION, "Pay 10 GEN.")
    with direct_vm.expect_revert("action_hash"):
        contract.actionjurisdication_open_action(matrix_id, CTX, "XYZ", "Pay 10 GEN.")


def test_action_hash_is_single_registration_key(direct_vm, direct_deploy, direct_alice, direct_bob):
    contract = direct_deploy(CONTRACT, sdk_version="v0.2.16")
    owner = direct_vm.sender
    matrix_id, _, _, _ = create_matrix(contract, owner, direct_alice, direct_bob)
    contract.actionjurisdication_open_action(matrix_id, CTX, ACTION, "Pay 10 GEN.")
    with direct_vm.expect_revert("already been registered"):
        contract.actionjurisdication_open_action(matrix_id, CTX, ACTION, "Try to register the same exact payload again.")


def test_in_scope_classification_selects_exact_required_dimensions(
    direct_vm, direct_deploy, direct_alice, direct_bob
):
    contract = direct_deploy(CONTRACT, sdk_version="v0.2.16")
    owner = direct_vm.sender
    matrix_id, _, _, _ = create_matrix(contract, owner, direct_alice, direct_bob)
    action_id = open_and_classify(contract, direct_vm, matrix_id, ["money", "security", "data"])
    action = contract.actionjurisdication_get_action(action_id)
    assert action["status_name"] == "AWAITING_APPROVALS"
    assert action["required_mask"] == 7
    assert [x["key"] for x in action["requirements"]] == ["money", "security", "data"]
    assert direct_vm.run_validator() is True


def test_validator_rederives_jurisdiction_not_just_json_shape(
    direct_vm, direct_deploy, direct_alice, direct_bob
):
    contract = direct_deploy(CONTRACT, sdk_version="v0.2.16")
    owner = direct_vm.sender
    matrix_id, _, _, _ = create_matrix(contract, owner, direct_alice, direct_bob)

    direct_vm.mock_llm(CLASSIFIER, classification(dimensions=["money"]))
    action_id = contract.actionjurisdication_open_action(matrix_id, CTX, ACTION, "Pay 40 GEN for a security review.")
    contract.actionjurisdication_classify_action(action_id)
    assert contract.actionjurisdication_get_action(action_id)["required_mask"] == 1

    direct_vm.clear_mocks()
    direct_vm.mock_llm(CLASSIFIER, classification(dimensions=["money", "security"]))
    assert direct_vm.run_validator() is False


def test_unknown_dimension_from_model_fails_closed_to_ambiguous(
    direct_vm, direct_deploy, direct_alice, direct_bob
):
    contract = direct_deploy(CONTRACT, sdk_version="v0.2.16")
    owner = direct_vm.sender
    matrix_id, _, _, _ = create_matrix(contract, owner, direct_alice, direct_bob)
    direct_vm.mock_llm(CLASSIFIER, classification(dimensions=["money", "invented_power"]))
    action_id = contract.actionjurisdication_open_action(matrix_id, CTX, ACTION, "Pay 40 GEN.")
    contract.actionjurisdication_classify_action(action_id)
    assert contract.actionjurisdication_get_action(action_id)["status_name"] == "AMBIGUOUS"


def test_contradictory_model_shape_fails_closed(direct_vm, direct_deploy, direct_alice, direct_bob):
    contract = direct_deploy(CONTRACT, sdk_version="v0.2.16")
    owner = direct_vm.sender
    matrix_id, _, _, _ = create_matrix(contract, owner, direct_alice, direct_bob)
    direct_vm.mock_llm(
        CLASSIFIER,
        json.dumps({"status": "OUT_OF_SCOPE", "dimensions": ["money"], "reason": "contradiction"}),
    )
    action_id = contract.actionjurisdication_open_action(matrix_id, CTX, ACTION, "Pay 40 GEN.")
    contract.actionjurisdication_classify_action(action_id)
    assert contract.actionjurisdication_get_action(action_id)["status_name"] == "AMBIGUOUS"


def test_out_of_scope_action_is_never_auto_authorized(
    direct_vm, direct_deploy, direct_alice, direct_bob
):
    contract = direct_deploy(CONTRACT, sdk_version="v0.2.16")
    owner = direct_vm.sender
    matrix_id, _, _, _ = create_matrix(contract, owner, direct_alice, direct_bob)
    direct_vm.mock_llm(CLASSIFIER, classification(status="OUT_OF_SCOPE", dimensions=[]))
    action_id = contract.actionjurisdication_open_action(matrix_id, CTX, ACTION, "Change the UI background colour.")
    contract.actionjurisdication_classify_action(action_id)
    action = contract.actionjurisdication_get_action(action_id)
    assert action["status_name"] == "OUT_OF_SCOPE"
    assert contract.actionjurisdication_is_authorized_for(action_id, CTX, ACTION, action["description_hash"], action["action_commitment"], action["matrix_hash"]) is False


def test_ambiguous_action_is_never_auto_authorized(
    direct_vm, direct_deploy, direct_alice, direct_bob
):
    contract = direct_deploy(CONTRACT, sdk_version="v0.2.16")
    owner = direct_vm.sender
    matrix_id, _, _, _ = create_matrix(contract, owner, direct_alice, direct_bob)
    direct_vm.mock_llm(CLASSIFIER, classification(status="AMBIGUOUS", dimensions=[]))
    action_id = contract.actionjurisdication_open_action(matrix_id, CTX, ACTION, "Do the thing we discussed.")
    contract.actionjurisdication_classify_action(action_id)
    action = contract.actionjurisdication_get_action(action_id)
    assert action["status_name"] == "AMBIGUOUS"
    assert contract.actionjurisdication_is_authorized_for(action_id, CTX, ACTION, action["description_hash"], action["action_commitment"], action["matrix_hash"]) is False


def test_unrequired_dimension_cannot_approve(direct_vm, direct_deploy, direct_alice, direct_bob):
    contract = direct_deploy(CONTRACT, sdk_version="v0.2.16")
    owner = direct_vm.sender
    matrix_id, _, security, _ = create_matrix(contract, owner, direct_alice, direct_bob)
    action_id = open_and_classify(contract, direct_vm, matrix_id, ["money"])
    with direct_vm.prank(direct_bob):
        with direct_vm.expect_revert("dimension is not required"):
            contract.actionjurisdication_approve(action_id, security)


def test_non_approver_cannot_approve_required_dimension(
    direct_vm, direct_deploy, direct_alice, direct_bob
):
    contract = direct_deploy(CONTRACT, sdk_version="v0.2.16")
    owner = direct_vm.sender
    matrix_id, _, security, _ = create_matrix(contract, owner, direct_alice, direct_bob)
    action_id = open_and_classify(contract, direct_vm, matrix_id, ["security"])
    with direct_vm.prank(direct_alice):
        with direct_vm.expect_revert("not an approver"):
            contract.actionjurisdication_approve(action_id, security)


def test_duplicate_approval_is_rejected(direct_vm, direct_deploy, direct_alice, direct_bob):
    contract = direct_deploy(CONTRACT, sdk_version="v0.2.16")
    owner = direct_vm.sender
    matrix_id, money, _, _ = create_matrix(contract, owner, direct_alice, direct_bob, min_distinct=2)
    action_id = open_and_classify(contract, direct_vm, matrix_id, ["money"])
    with direct_vm.prank(direct_alice):
        contract.actionjurisdication_approve(action_id, money)
        with direct_vm.expect_revert("already recorded"):
            contract.actionjurisdication_approve(action_id, money)


def test_all_dimension_thresholds_are_required(direct_vm, direct_deploy, direct_alice, direct_bob):
    contract = direct_deploy(CONTRACT, sdk_version="v0.2.16")
    owner = direct_vm.sender
    matrix_id, money, security, _ = create_matrix(
        contract, owner, direct_alice, direct_bob, min_distinct=2
    )
    action_id = open_and_classify(contract, direct_vm, matrix_id, ["money", "security"])

    with direct_vm.prank(direct_alice):
        contract.actionjurisdication_approve(action_id, money)
    assert contract.actionjurisdication_get_action(action_id)["status_name"] == "AWAITING_APPROVALS"

    with direct_vm.prank(direct_bob):
        contract.actionjurisdication_approve(action_id, security)
    assert contract.actionjurisdication_get_action(action_id)["status_name"] == "AUTHORIZED"


def test_global_distinct_signer_floor_is_independent_of_dimension_thresholds(
    direct_vm, direct_deploy, direct_alice, direct_bob
):
    contract = direct_deploy(CONTRACT, sdk_version="v0.2.16")
    matrix_id = contract.actionjurisdication_create_matrix(
        "Cross-check",
        "Require two distinct people even when one person spans authority dimensions.",
        2,
        True,
    )
    money = contract.actionjurisdication_add_dimension(matrix_id, "money", "Review financial exposure.", 1)
    security = contract.actionjurisdication_add_dimension(matrix_id, "security", "Review security exposure.", 1)
    contract.actionjurisdication_add_approver(matrix_id, money, direct_alice)
    contract.actionjurisdication_add_approver(matrix_id, money, direct_bob)
    contract.actionjurisdication_add_approver(matrix_id, security, direct_alice)
    contract.actionjurisdication_add_approver(matrix_id, security, direct_bob)
    contract.actionjurisdication_seal_matrix(matrix_id)

    action_id = open_and_classify(contract, direct_vm, matrix_id, ["money", "security"])
    with direct_vm.prank(direct_alice):
        contract.actionjurisdication_approve(action_id, money)
        contract.actionjurisdication_approve(action_id, security)
    assert contract.actionjurisdication_get_action(action_id)["status_name"] == "AWAITING_APPROVALS"

    with direct_vm.prank(direct_bob):
        contract.actionjurisdication_approve(action_id, money)
    assert contract.actionjurisdication_get_action(action_id)["status_name"] == "AUTHORIZED"


def test_maker_checker_rule_can_forbid_proposer_approval(
    direct_vm, direct_deploy, direct_alice, direct_bob
):
    contract = direct_deploy(CONTRACT, sdk_version="v0.2.16")
    owner = direct_vm.sender
    matrix_id, money, _, _ = create_matrix(
        contract, owner, direct_alice, direct_bob, proposer_may_approve=False
    )
    with direct_vm.prank(direct_alice):
        action_id = contract.actionjurisdication_open_action(matrix_id, CTX, ACTION, "Pay 40 GEN.")
    direct_vm.mock_llm(CLASSIFIER, classification(dimensions=["money"]))
    contract.actionjurisdication_classify_action(action_id)

    with direct_vm.prank(direct_alice):
        with direct_vm.expect_revert("proposer may not approve"):
            contract.actionjurisdication_approve(action_id, money)


def test_approval_can_be_revoked_before_authorization(
    direct_vm, direct_deploy, direct_alice, direct_bob
):
    contract = direct_deploy(CONTRACT, sdk_version="v0.2.16")
    owner = direct_vm.sender
    matrix_id, money, _, _ = create_matrix(contract, owner, direct_alice, direct_bob, min_distinct=2)
    action_id = open_and_classify(contract, direct_vm, matrix_id, ["money"])
    with direct_vm.prank(direct_alice):
        contract.actionjurisdication_approve(action_id, money)
        assert contract.actionjurisdication_has_approved(action_id, money, direct_alice) is True
        contract.actionjurisdication_revoke_approval(action_id, money)
        assert contract.actionjurisdication_has_approved(action_id, money, direct_alice) is False
    assert contract.actionjurisdication_get_action(action_id)["requirements"][0]["approval_count"] == 0


def test_authorized_action_rejects_description_from_different_action_commitment(
    direct_vm, direct_deploy, direct_alice, direct_bob
):
    contract = direct_deploy(CONTRACT, sdk_version="v0.2.16")
    owner = direct_vm.sender
    matrix_id, money, _, _ = create_matrix(contract, owner, direct_alice, direct_bob)
    action_id = open_and_classify(contract, direct_vm, matrix_id, ["money"])
    with direct_vm.prank(direct_alice):
        contract.actionjurisdication_approve(action_id, money)

    action = contract.actionjurisdication_get_action(action_id)
    assert action["status_name"] == "AUTHORIZED"
    expected_commitment = commitment(CTX, ACTION, action["description_hash"])
    assert action["action_commitment"] == expected_commitment
    # Attack regression: substitute a benign cosmetic-action description after
    # the payment action was classified and authorized. The frozen commitment
    # must not authorize that different description for the payment hash.
    benign_description_hash = keccak_text("Change the dashboard banner to blue.")
    assert benign_description_hash != action["description_hash"]
    assert contract.actionjurisdication_is_authorized_for(action_id, CTX, ACTION, action["description_hash"], expected_commitment, action["matrix_hash"]) is True
    assert contract.actionjurisdication_is_authorized_for(action_id, "44" * 32, ACTION, action["description_hash"], expected_commitment, action["matrix_hash"]) is False
    assert contract.actionjurisdication_is_authorized_for(action_id, CTX, ACTION_2, action["description_hash"], expected_commitment, action["matrix_hash"]) is False
    assert contract.actionjurisdication_is_authorized_for(action_id, CTX, ACTION, benign_description_hash, expected_commitment, action["matrix_hash"]) is False
    assert contract.actionjurisdication_is_authorized_for(action_id, CTX, ACTION, action["description_hash"], "77" * 32, action["matrix_hash"]) is False
    assert contract.actionjurisdication_is_authorized_for(action_id, CTX, ACTION, action["description_hash"], expected_commitment, "55" * 32) is False


def test_approvals_cannot_be_revoked_after_authorization(
    direct_vm, direct_deploy, direct_alice, direct_bob
):
    contract = direct_deploy(CONTRACT, sdk_version="v0.2.16")
    owner = direct_vm.sender
    matrix_id, money, _, _ = create_matrix(contract, owner, direct_alice, direct_bob)
    action_id = open_and_classify(contract, direct_vm, matrix_id, ["money"])
    with direct_vm.prank(direct_alice):
        contract.actionjurisdication_approve(action_id, money)
        with direct_vm.expect_revert("only be revoked before authorization"):
            contract.actionjurisdication_revoke_approval(action_id, money)


def test_only_proposer_or_owner_can_cancel(direct_vm, direct_deploy, direct_alice, direct_bob):
    contract = direct_deploy(CONTRACT, sdk_version="v0.2.16")
    owner = direct_vm.sender
    matrix_id, _, _, _ = create_matrix(contract, owner, direct_alice, direct_bob)
    with direct_vm.prank(direct_alice):
        action_id = contract.actionjurisdication_open_action(matrix_id, CTX, ACTION, "Pay 40 GEN.")
    with direct_vm.prank(direct_bob):
        with direct_vm.expect_revert("only proposer or matrix owner"):
            contract.actionjurisdication_cancel_action(action_id)
    with direct_vm.prank(direct_alice):
        contract.actionjurisdication_cancel_action(action_id)
    assert contract.actionjurisdication_get_action(action_id)["status_name"] == "CANCELLED"


def test_action_can_only_be_classified_once(direct_vm, direct_deploy, direct_alice, direct_bob):
    contract = direct_deploy(CONTRACT, sdk_version="v0.2.16")
    owner = direct_vm.sender
    matrix_id, _, _, _ = create_matrix(contract, owner, direct_alice, direct_bob)
    action_id = open_and_classify(contract, direct_vm, matrix_id, ["money"])
    with direct_vm.expect_revert("not pending classification"):
        contract.actionjurisdication_classify_action(action_id)


def test_owner_can_cancel_pending_action(direct_vm, direct_deploy, direct_alice, direct_bob):
    contract = direct_deploy(CONTRACT, sdk_version="v0.2.16")
    owner = direct_vm.sender
    matrix_id, _, _, _ = create_matrix(contract, owner, direct_alice, direct_bob)
    with direct_vm.prank(direct_alice):
        action_id = contract.actionjurisdication_open_action(matrix_id, CTX, ACTION, "Pay 40 GEN.")
    contract.actionjurisdication_cancel_action(action_id)
    assert contract.actionjurisdication_get_action(action_id)["status_name"] == "CANCELLED"


def test_constants_are_stable(direct_vm, direct_deploy):
    contract = direct_deploy(CONTRACT, sdk_version="v0.2.16")
    constants = contract.actionjurisdication_get_constants()
    assert constants["MATRIX_DRAFT"] == 0
    assert constants["MATRIX_SEALED"] == 1
    assert constants["ACTION_AUTHORIZED"] == 2
    assert constants["MAX_DIMENSIONS"] == 16
