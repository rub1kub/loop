# Contracts and reproducible verification

Both contracts are built from Tolk sources with Acton and deployed independently on TON mainnet.

| Contract   | Address                                                                                | Code hash         | Fee |
| ---------- | -------------------------------------------------------------------------------------- | ----------------- | --: |
| BankQueue  | [`EQDn…Ht8Mn`](https://tonviewer.com/EQDnfQuYXg2V-IyQ39L9qmkiCYKgNra7s3QZhADvaLQHt8Mn) | `5F6E4DD8…EF834`  | 10% |
| DuelEscrow | [`EQBN…YogMv`](https://tonviewer.com/EQBN4TO22cyYn15CHhwwbp6zazZaAGYWMG5f_Jr8yotYogMv) | `E934E407…2F4B3A` | 10% |

Complete addresses, code/data hashes, deployment transaction, logical time, compiler version,
parameters, opcodes and getters are committed in `deployments/mainnet/bank.json` and
`deployments/mainnet/duel.json`. Mutable live fields such as balance, locked value and pause state
must be read from the network rather than treated as constants from a deployment manifest.

## Verification

```bash
make contracts-build
make contracts-mainnet-verify
acton script --net mainnet scripts/verify-mainnet-state.tolk \
  "$(jq -r .address deployments/mainnet/bank.json)" \
  "$(jq -r .address deployments/mainnet/duel.json)"
```

`contracts-mainnet-verify` fails unless:

- the local build hash equals the manifest;
- the live account is active;
- live code equals the manifest and deployment state produced the recorded initial data hash;
- the deployment transaction succeeded at the recorded logical time;
- the transaction has masterchain finality.
- when a manifest contains `verified_smoke`, the recorded BANK or DUEL smoke has the expected
  distinct senders, values, message bodies, fees, payouts and masterchain finality;
- BANK reports the finalized completion counter and current principal limit;
- DUEL reports the pinned network global ID, self-address and invite signer public key.

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

DUEL reserves all locked user value plus at least `0.2 GRAM` and refuses a fee change while a stake
is locked. BANK intentionally permits the owner to withdraw everything above `0.2 GRAM`, including
funding expected by open positions; the risk is disclosed in `docs/no-audit-disclosure.md`. A new
financial rule, invite signer rotation or code change still requires a new address and manifest;
the backend is not allowed to emulate a contract payout rule.
