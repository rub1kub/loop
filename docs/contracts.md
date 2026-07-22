# Contracts and reproducible verification

Both contracts are built from Tolk sources with Acton and deployed independently on TON testnet.

| Contract   | Address                                                                                         | Code hash          |  Fee |
| ---------- | ----------------------------------------------------------------------------------------------- | ------------------ | ---: |
| BankQueue  | [`kQC1…Hrmc4l`](https://testnet.tonviewer.com/kQC1zcM8cxIDn3mFR0RV_PS_y2PzNkFttJ8NfAPHTyHrmc4l) | `330930F4…6924A7A` |   1% |
| DuelEscrow | [`kQDV…Ydu3Tw`](https://testnet.tonviewer.com/kQDVeChmpyLsgjLZRLW-gtwSS4s5depJWpBhuYkfhgYdu3Tw) | `7BD5BCB2…36756DF` | 2.5% |

Complete addresses, code/data hashes, deployment transaction, logical time, compiler version, parameters, opcodes and getters are committed in `deployments/testnet/bank.json` and `deployments/testnet/duel.json`. The BANK manifest additionally records its first finalized funding proof.

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
- the BANK smoke transaction has the recorded sender, value, message body, fee transfer and masterchain block.
- the DUEL smoke opened escrow, returned the principal and restored `locked` to zero.
- DUEL v1.1 reports the pinned testnet global ID, self-address and invite signer public key.

`contracts-inspect` decodes live storage using the generated Acton wrappers. The API also exposes read-only contract, wallet, transaction and Jetton diagnostics to authenticated users.

## Upgrade policy

Contracts are immutable in behavior except for explicit owner administration exposed by source. Pausing blocks new activity but never blocks user recovery paths. A new financial rule or signer rotation requires a new audited contract address and manifest; the backend is not allowed to emulate an on-chain fee or payout rule.
