# Contracts and reproducible verification

Both contracts are built from Tolk sources with Acton and deployed independently on TON testnet.

| Contract   | Address                                                                                         | Code hash         |  Fee |
| ---------- | ----------------------------------------------------------------------------------------------- | ----------------- | ---: |
| BankQueue  | [`kQCq…50Il3`](https://testnet.tonviewer.com/kQCqjhisqfxDrsPOEMWFE6AI1OWBtIQy_VVfXZU25zD50Il3)  | `BA0A33E5…1FB3E2` |   1% |
| DuelEscrow | [`kQD7…w4lg3M`](https://testnet.tonviewer.com/kQD7JaRbyRrkGFzk9Xk3rfpRqNBSAUF2T-kXxfDlXYw4lg3M) | `5BDAED2F…3C17FB` | 2.5% |

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
  distinct senders, values, message bodies, fees, payouts and masterchain finality;
- BANK v1.3 reports the finalized completion counter and current principal limit;
- DUEL v1.3 reports the pinned network global ID, self-address and invite signer public key.

The BANK manifest now contains a finalized two-wallet deposit → payout proof: both create messages,
both protocol fees, the 1.25 GRAM payout and the remaining second position are independently
checked. For mainnet this cycle must run on a separate shadow contract with identical code, because
a successful FIFO cycle necessarily leaves the last contributor's position in the queue. The final
production BANK is instead activated paused and empty.

The DUEL manifest contains masterchain-finalized open/cancel/refund, boost and two-wallet settlement
proofs. The boost proof binds sender, amount, duel, offer, revision, minimum chance and expiry.
Mutable state is read live and checked against the retained-reserve invariant, so an active offer
does not invalidate the deployment proof.

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
