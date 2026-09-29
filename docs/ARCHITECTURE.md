# Architecture

Related documents: [README](../README.md) · [Security model](SECURITY.md) · [Deployment evidence](../DEPLOYMENT.md) · [Submission notes](../SUBMISSION.md)

## Design goal

ActionJurisdication separates semantic jurisdiction from authorization mechanics.

GenLayer consensus answers only:

Which sealed authority dimensions materially govern this exact action description?

All authority is already present on-chain before that question is asked.

## Modules

| File | Contract | Role |
|---|---|---|
| `contracts/actionjurisdication.py` | `ActionJurisdication` | Registry: matrix configuration and sealing, action intake, semantic classification, approval accounting, authorization state |
| `contracts/action_gate.py` | `ActionGate` | Reference consumer: verifies a consumer-bound commitment before recording a one-shot execution |

Every public entry point is prefixed with the file that defines it, so a caller can tell from the method name alone which contract it targets. The complete list is in the [README public API table](../README.md#public-api).

## Matrix

A matrix contains:

- owner during draft configuration;
- human-readable purpose;
- independent authority dimensions;
- one threshold per dimension;
- approver membership per dimension;
- matrix-wide minimum distinct signer count;
- optional maker-checker rule;
- canonical sealed definition hash.

A matrix becomes immutable when sealed.

## Dimension

A dimension is a bounded authority domain such as money, security, data, or legal.

The semantic description explains when that authority should be involved. Thresholds and approvers are deterministic state.

## Action

An action binds:

- sealed matrix ID and definition hash;
- proposer;
- consumer context hash;
- exact executable action hash;
- hash of the frozen natural-language description;
- domain-separated commitment over consumer context, action hash, and description hash;
- consensus-derived required-dimension bitmask;
- deterministic approval state.

## Action state machine

```text
PENDING
    |
actionjurisdication_classify_action
    |
    +-- IN_SCOPE ------> AWAITING_APPROVALS --(thresholds + distinct-signer floor)--> AUTHORIZED
    +-- OUT_OF_SCOPE --> OUT_OF_SCOPE        (never authorizing)
    +-- AMBIGUOUS -----> AMBIGUOUS           (never authorizing)

AWAITING_APPROVALS --actionjurisdication_revoke_approval--> AWAITING_APPROVALS
any state except AUTHORIZED/CANCELLED --actionjurisdication_cancel_action--> CANCELLED
```

Transitions are deterministic. Only the classification step is nondeterministic, and its result is constrained to a bounded status plus a bitmask. AUTHORIZED and CANCELLED are final; revocation is available only while the action is awaiting approvals.

## Consensus boundary

The model cannot:

- add or remove approvers;
- change thresholds;
- authorize an action;
- weaken the global distinct-signer floor;
- change the action hash;
- change the consumer context;
- change the matrix definition.

It returns only a bounded jurisdiction classification.

The custom validator independently repeats that task and requires exact agreement on classification state and bitmask.

## Fail-closed states

OUT_OF_SCOPE is not an authorization shortcut. It means the matrix is not the correct authority system for the action.

AMBIGUOUS never becomes authorizing and cannot advance toward authorization. Callers must create a new exact action commitment with a clearer description rather than asking the contract to guess.

## Consumer binding

The consumer-facing view requires:

    action_id
    context_hash
    action_hash
    description_hash
    action_commitment
    matrix_hash

The view checks the supplied description hash against the frozen classified description and recomputes the domain-separated commitment from the supplied context, action hash, and description hash. This prevents the consumer from substituting a benign description for a different executable payload.

## Why the matrix is immutable

Mutable authority definitions create a policy-substitution problem: an administrator could alter thresholds or approvers after an action was opened.

ActionJurisdication avoids that class of ambiguity entirely. Updates require a new sealed matrix. Consumers decide which exact matrix hash they trust.
