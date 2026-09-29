# ActionJurisdication

[![CI](https://github.com/ometere123/authoritymatrix/actions/workflows/ci.yml/badge.svg)](https://github.com/ometere123/authoritymatrix/actions/workflows/ci.yml)

ActionJurisdication is a reusable GenLayer Intelligent Contract for semantic separation of duties.

A normal multisig answers one question: did enough keys approve? ActionJurisdication answers a harder question first: which independent authority domains does this exact action touch?

The authority matrix is configured deterministically. Each dimension has its own approvers and threshold. A proposed action binds the exact action hash, consumer context hash, and normalized description hash into a domain-separated on-chain action commitment, alongside the immutable sealed matrix hash. GenLayer consensus only classifies semantic jurisdiction. It never chooses approvers, thresholds, or whether missing approvals can be bypassed.

There is **no frontend**. This repository is intentionally a standalone Intelligent Contract primitive.

## Documentation

| Document | Contents |
|---|---|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Data model, consensus boundary, consumer binding |
| [docs/SECURITY.md](docs/SECURITY.md) | Threat model, safety arguments, known limits |
| [DEPLOYMENT.md](DEPLOYMENT.md) | Studionet addresses, transaction hashes, readback evidence |
| [SUBMISSION.md](SUBMISSION.md) | Short-form rationale and verification summary |

## Network lock

ActionJurisdication targets **Studionet only**:

- network alias: `studionet`
- RPC: https://studio.genlayer.com/api
- chain ID: **61999**
- explorer: https://explorer-studio.genlayer.com/

The repository does not target 61997 and does not use the development-preview network.

## Why this primitive exists

An organization may require different people to approve different parts of one action:

- finance approves spending and value at risk;
- security approves privileged access and attack-surface changes;
- data/privacy approves sensitive information handling;
- legal approves contractual or external obligations.

A flat 3-of-5 multisig cannot express that cleanly.

Example action:

```text
Pay 40 GEN for an external penetration test that uses customer-derived test fixtures.
```

A sealed matrix might derive:

```text
MONEY       threshold 1
SECURITY    threshold 1
DATA        threshold 1
```

The action does not become authorized until every required dimension reaches its deterministic threshold and the matrix-wide minimum number of distinct signers is also satisfied.

## Core invariants

1. The matrix is immutable after sealing.
2. Consensus selects jurisdiction, not permission.
3. OUT_OF_SCOPE never means approved.
4. AMBIGUOUS fails closed.
5. Authorization is tied to an exact 32-byte action hash.
6. Consumers also pin a separate 32-byte context hash.
7. Consumers pin the sealed matrix definition hash.
8. Thresholds and approver membership are deterministic.
9. A matrix-wide distinct-signer floor prevents one cross-functional signer from satisfying a configured multi-person control alone.
10. A matrix may forbid the proposer from approving their own action.
11. An exact action hash can only be registered once.
12. Approvals may be revoked while pending, but not after authorization.
13. Consumer authorization verifies the description hash and recomputes the action commitment from the context, executable payload hash, and classified description hash.

## Contract lifecycle

```text
actionjurisdication_create_matrix
    |
actionjurisdication_add_dimension x N
    |
actionjurisdication_add_approver x N
    |
actionjurisdication_seal_matrix
    |
actionjurisdication_open_action(context_hash, action_hash, description)
    |
actionjurisdication_classify_action
    |
    +-- IN_SCOPE ------> collect required approvals ------> AUTHORIZED
    +-- OUT_OF_SCOPE --> never authorized
    +-- AMBIGUOUS -----> never authorized
```

## Public API

Entry points are prefixed with the file that defines them. The names below are the exact callable identifiers.

### `contracts/actionjurisdication.py` — class `ActionJurisdication`

| Kind | Signature |
|---|---|
| write | `actionjurisdication_create_matrix(name, purpose, min_distinct_approvers, proposer_may_approve) -> matrix_id` |
| write | `actionjurisdication_add_dimension(matrix_id, key, description, threshold) -> dimension_id` |
| write | `actionjurisdication_add_approver(matrix_id, dimension_id, approver)` |
| write | `actionjurisdication_seal_matrix(matrix_id)` |
| write | `actionjurisdication_open_action(matrix_id, context_hash, action_hash, description) -> action_id` |
| write | `actionjurisdication_classify_action(action_id)` |
| write | `actionjurisdication_approve(action_id, dimension_id)` |
| write | `actionjurisdication_revoke_approval(action_id, dimension_id)` |
| write | `actionjurisdication_cancel_action(action_id)` |
| read | `actionjurisdication_get_matrix(matrix_id) -> dict` |
| read | `actionjurisdication_get_action(action_id) -> dict` |
| read | `actionjurisdication_has_approved(action_id, dimension_id, approver) -> bool` |
| read | `actionjurisdication_is_authorized_for(action_id, expected_context_hash, expected_action_hash, expected_description_hash, expected_action_commitment, expected_matrix_hash) -> bool` |
| read | `actionjurisdication_get_constants() -> dict` |

### `contracts/action_gate.py` — class `ActionGate`

| Kind | Signature |
|---|---|
| write | `action_gate_execute(action_id, expected_action_hash, expected_description_hash, expected_action_commitment, expected_matrix_hash)` |
| read | `action_gate_was_executed(action_hash) -> bool` |
| read | `action_gate_get_execution(action_hash) -> dict` |

## Consensus design

The leader produces only a bounded semantic result:

```json
{
  "status": "IN_SCOPE",
  "dimensions": ["money", "security", "data"],
  "reason": "..."
}
```

Every validator independently repeats the jurisdiction task over the sealed matrix and frozen action description.

The custom validator accepts only when the validator independently agrees on:

- classification state; and
- the exact dimension bitmask.

Rationale text is diagnostic only and is not consensus-critical.

This is deliberately stricter than a format-only validator. A leader cannot omit a material authority dimension and still be accepted merely because its JSON is valid.

## Consumer interface

Consumers call:

```text
actionjurisdication_is_authorized_for(
    action_id,
    expected_context_hash,
    expected_action_hash,
    expected_description_hash,
    expected_action_commitment,
    expected_matrix_hash,
)
```

The included ActionGate accepts the expected description hash and action commitment and passes both to the registry view. The registry checks that they match stored values and recomputes the commitment from the registered context, action hash, and normalized classified description hash.

The context hash should commit to the intended consumer domain, for example:

```text
chain=61999 | consumer=<address> | version=1 | operation-family=treasury-execute
```

Hash that canonical value off-chain and use the resulting 32-byte digest.

## Repository layout

```text
contracts/
  actionjurisdication.py   # registry: matrices, actions, classification, approvals
  action_gate.py           # reference consumer of the registry view

tests/
  conftest.py
  direct/
    test_actionjurisdication.py

scripts/
  preflight.py
  deploy_studionet.sh

docs/
  ARCHITECTURE.md
  SECURITY.md

.github/workflows/ci.yml
gltest.config.yaml
requirements.txt
requirements-test.txt
LICENSE
README.md
SUBMISSION.md
DEPLOYMENT.md
```

## Local checks

```bash
python scripts/preflight.py
python -m pip install -r requirements-test.txt
pytest tests/direct/ -v -s
```

Optional linter:

```bash
python -m pip install -r requirements.txt
genvm-linter contracts/actionjurisdication.py
genvm-linter contracts/action_gate.py
```

## Deploy to Studionet

Install the pinned project-local CLI on Windows:

```bat
npm ci --prefix .genlayer-stable
.\.genlayer-stable\node_modules\.bin\genlayer.cmd --version
```

Use:

```bat
.\.genlayer-stable\node_modules\.bin\genlayer.cmd deploy --contract contracts/actionjurisdication.py --rpc https://studio.genlayer.com/api
```

or:

```bash
genlayer network set studionet
genlayer network info
genlayer deploy --contract contracts/actionjurisdication.py --rpc https://studio.genlayer.com/api
```

Before signing any transaction, confirm chain ID 61999.

## Live deployment and reviewer evidence

The corrected ActionJurisdication is deployed at [`0xb1748CD74F52A85dcC1c4C57144BC24F44e7a871`](https://explorer-studio.genlayer.com/address/0xb1748CD74F52A85dcC1c4C57144BC24F44e7a871), and the corrected ActionGate is deployed at [`0xE2b921C8db13b9B2BdB7De0de4990Ff3Da6F807e`](https://explorer-studio.genlayer.com/address/0xE2b921C8db13b9B2BdB7De0de4990Ff3Da6F807e). Both deployments finalized successfully. The gate accepted an exact authorized action and rejected an authorized action when its expected description hash was changed.

Earlier addresses and lifecycle evidence remain documented as historical pre-fix deployments. See [DEPLOYMENT.md](DEPLOYMENT.md) for transaction-by-transaction evidence, readbacks, the matrix definition hash, the consumer proof, and the verification record.

## What ActionJurisdication is not

ActionJurisdication is not a DAO frontend, treasury, escrow, generic policy oracle, mandate system, or LLM multisig replacement.

It does one job: map an exact natural-language action to the sealed authority domains that must approve it, then enforce those approvals deterministically.
