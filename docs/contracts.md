# Contracts and reproducible verification

Both contracts are built from Tolk sources with Acton and deployed independently on TON testnet.

| Contract   | Address                                                                                          | Code hash         |  Fee |
| ---------- | ------------------------------------------------------------------------------------------------ | ----------------- | ---: |
| BankQueue  | [`kQAQ…v4FL_y`](https://testnet.tonviewer.com/kQAQRNh3sG80ykjME39tnWnfswnjCDcRtrrCDOQP4jv4FL_y)  | `9BF8EF5B…4A57C2` |   1% |
| DuelEscrow | [`kQD9…02xo6yP`](https://testnet.tonviewer.com/kQD9vsBIFke3V_cxWQaW8ostPE-3ama0D7Hm_YGac02xo6yP) | `F9E55EE5…62C3F6` | 2.5% |

Complete addresses, code/data hashes, deployment transaction, logical time, compiler version,
parameters, opcodes and getters are committed in `deployments/testnet/bank.json` and
`deployments/testnet/duel.json`. Mutable live fields such as balance, locked value and pause state
must be read from the network rather than treated as constants from a deployment manifest.

## Verification

```bash
make contracts-build
make contracts-verify
make contracts-inspect
```

`contracts-verify` fails unless:

- the local build hash equals the manifest;
- the live account is active;
- live code equals the manifest and deployment state produced the recorded initial data hash;
- the deployment transaction succeeded at the recorded logical time;
- the transaction has masterchain finality.
- when a manifest contains `verified_smoke`, the recorded BANK or DUEL smoke has the expected
  sender, value, message body, transfers and masterchain block;
- DUEL v1.2 reports the pinned testnet global ID, self-address and invite signer public key.

The DUEL manifest contains masterchain-finalized open/cancel/refund and two-wallet settlement
proofs. Mutable state is read live and checked against the retained-reserve invariant, so an active
offer does not invalidate the deployment proof.

`contracts-inspect` decodes live storage using the generated Acton wrappers. The API also exposes read-only contract, wallet, transaction and Jetton diagnostics to authenticated users.

## Upgrade policy

Contracts are immutable in behavior except for explicit owner administration exposed by source.
Pausing blocks new activity but never blocks user recovery paths. Current owner messages support:

- pause/resume;
- reserve funding with an explicitly declared amount;
- withdrawal of verified free surplus to the configured treasury;
- fee and treasury changes while paused;
- ownership transfer while paused.

The contracts reserve all locked user value plus at least `0.2 GRAM`; no administrative message can
withdraw through that boundary. DUEL refuses a fee change while any stake is locked. A new financial
rule, invite signer rotation or code change still requires a new audited address and manifest; the
backend is not allowed to emulate a contract payout rule.
