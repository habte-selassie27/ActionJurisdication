# ActionJurisdication submission notes

Related documents: [README](README.md) · [Architecture](docs/ARCHITECTURE.md) · [Security model](docs/SECURITY.md) · [Deployment evidence](DEPLOYMENT.md)

## One-line purpose

ActionJurisdication is a reusable semantic separation-of-duties primitive that determines which independent authority domains govern an exact action, then enforces each domain's approval threshold deterministically.

## Why GenLayer is necessary

A normal smart contract can count signatures but cannot reliably determine that a natural-language action simultaneously touches finance, security, and data authority when the wording is not reducible to fixed selectors.

ActionJurisdication uses GenLayer only for that semantic jurisdiction boundary. Validators independently derive the exact required-dimension mask. Approval thresholds, signers, immutable matrix definitions, description/action/context commitment, and authorization are deterministic.

## Non-trivial consensus

The validator is not format-only. A leader result is accepted only when an independent validator agrees on both:

1. IN_SCOPE / OUT_OF_SCOPE / AMBIGUOUS
2. the exact authority bitmask

A well-formed leader response that omits security while the validator independently finds money + security is rejected.

## Reusability

Any consumer contract can pin a matrix hash and call `actionjurisdication_is_authorized_for` before performing a protected action. The view requires the expected description hash and verifies a domain-separated commitment over the context hash, executable action hash, and classified description hash.

The included ActionGate demonstrates the consumer surface without turning the submission into a full app. There is no frontend.

## Important design choices

- matrices are immutable after sealing;
- out-of-scope never auto-authorizes;
- ambiguous classification fails closed;
- exact action and consumer context hashes, plus the classified description hash commitment, are mandatory;
- matrix-wide distinct-signer floors prevent one cross-functional approver from satisfying a configured multi-person control alone;
- proposer self-approval can be disabled;
- approvals may be revoked only before authorization.

## Tests

The 28-test Direct Mode suite in `tests/direct/test_actionjurisdication.py` covers configuration ownership, seal invariants, semantic consensus, contradictory classifier output, independent validator disagreement, threshold enforcement, cross-domain distinct-signer rules, maker-checker separation, revocation, exact binding, cancellation, and one-shot classification. The named regression `test_authorized_action_rejects_description_from_different_action_commitment` authorizes a payment action, then proves a benign cosmetic-action description hash cannot authorize the same action hash and frozen commitment.

## Corrected Studionet deployment and verification

Studionet only: chain ID 61999, RPC https://studio.genlayer.com/api, explorer https://explorer-studio.genlayer.com/.

Corrected ActionJurisdication: [`0xb1748CD74F52A85dcC1c4C57144BC24F44e7a871`](https://explorer-studio.genlayer.com/address/0xb1748CD74F52A85dcC1c4C57144BC24F44e7a871), deployment [`0x09c046e163a1bf5cbebe4831928317a30c2ad2d179055a982d9bb356dee5300d`](https://explorer-studio.genlayer.com/tx/0x09c046e163a1bf5cbebe4831928317a30c2ad2d179055a982d9bb356dee5300d), finalized successfully. Corrected ActionGate: [`0xE2b921C8db13b9B2BdB7De0de4990Ff3Da6F807e`](https://explorer-studio.genlayer.com/address/0xE2b921C8db13b9B2BdB7De0de4990Ff3Da6F807e), deployment [`0xdc05bbbfe562cc9c59592f0cb439704e9065888bdc5f594a4afa4c274e4dc75a`](https://explorer-studio.genlayer.com/tx/0xdc05bbbfe562cc9c59592f0cb439704e9065888bdc5f594a4afa4c274e4dc75a), finalized successfully.

The deployed consumer successfully executed an authorized action with matching hashes, then rejected another authorized action when the expected description hash was changed while retaining the original action commitment. The rejection finalized with `EXPECTED: ActionJurisdication authorization is not valid for this consumer`; its execution record remained absent. Full transaction and readback details are in [DEPLOYMENT.md](DEPLOYMENT.md).

The current-main Direct Mode and preflight results are reported by the newest [GitHub Actions run for `main`](https://github.com/ometere123/authoritymatrix/actions/workflows/ci.yml?query=branch%3Amain). This replaces the pre-fix test and CI record.

The old addresses above are superseded pre-fix deployments; see [DEPLOYMENT.md](DEPLOYMENT.md) for their historical record and the complete corrected deployment proof.
