"""Dependency-free reviewer-facing preflight for ActionJurisdication."""

from pathlib import Path
import ast

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "contracts" / "actionjurisdication.py"
CONSUMER = ROOT / "contracts" / "action_gate.py"
TESTS = ROOT / "tests" / "direct" / "test_actionjurisdication.py"
README = ROOT / "README.md"
CONFIG = ROOT / "gltest.config.yaml"
DEPLOY = ROOT / "scripts" / "deploy_studionet.sh"


def require(condition: bool, message: str):
    if not condition:
        raise SystemExit(f"FAIL: {message}")
    print(f"OK: {message}")


def main():
    source = CONTRACT.read_text(encoding="utf-8")
    consumer = CONSUMER.read_text(encoding="utf-8")
    tests = TESTS.read_text(encoding="utf-8")
    readme = README.read_text(encoding="utf-8")
    config = CONFIG.read_text(encoding="utf-8")
    deploy = DEPLOY.read_text(encoding="utf-8")

    for item in (source, consumer, tests):
        ast.parse(item)

    require("class ActionJurisdication(gl.Contract)" in source, "ActionJurisdication contract is present")
    require("class IActionJurisdication" in source, "cross-contract interface is present")
    require("run_nondet_unsafe" in source, "custom leader/validator consensus is present")
    require("_classify_once" in source, "validators independently re-derive jurisdiction")
    require("required_mask" in source, "semantic jurisdiction is stored as a bounded bitmask")
    require("min_distinct_approvers" in source, "matrix-wide distinct-signer floor is enforced")
    require("proposer_may_approve" in source, "maker-checker control is configurable")
    require("definition_hash" in source, "sealed matrix definition is hash-pinned")
    require("actionjurisdication_is_authorized_for" in source, "reusable consumer authorization view exists")
    require("class ActionGate(gl.Contract)" in consumer, "consumer proof contract is present")
    require(tests.count("def test_") >= 24, "substantial direct-mode suite is present")
    require("test_validator_rederives_jurisdiction_not_just_json_shape" in tests, "independent validator regression exists")
    require("test_global_distinct_signer_floor_is_independent_of_dimension_thresholds" in tests, "cross-domain distinct signer regression exists")
    require("test_authorized_action_rejects_description_from_different_action_commitment" in tests, "mismatched description/action commitment attack regression exists")
    require("no frontend" in readme.lower(), "README explains standalone primitive scope")
    require("https://studio.genlayer.com/api" in config, "Studionet RPC is configured")
    require("genlayer network set studionet" in deploy, "deploy helper explicitly selects Studionet")

    network_files = "\n".join((config, deploy))
    require("61997" not in network_files, "deployment/config files contain no 61997 target")
    require("studio-dev" not in network_files.lower(), "deployment/config files contain no studio-dev target")
    require("studio-next" not in network_files.lower(), "deployment/config files contain no studio-next target")

    print("Preflight passed.")


if __name__ == "__main__":
    main()
