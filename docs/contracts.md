# Contracts and reproducible verification

Both contracts are built from Tolk sources with Acton and deployed independently on TON testnet.

| Contract   | Address                                                                                         | Code hash          |  Fee |
| ---------- | ----------------------------------------------------------------------------------------------- | ------------------ | ---: |
| BankQueue  | [`kQCr…KvX81`](https://testnet.tonviewer.com/kQCrJa3LWrkb7iKbz5aZQw8dWl7zo2McsZah8YB2uPQKvX81)  | `F159981F…96FF15B` |   1% |
| DuelEscrow | [`kQBX…5l212a`](https://testnet.tonviewer.com/kQBXddZVMOteEYD87uSOfIAPL3P4UuI0Vf_fUAyGLS5l212a) | `1D8330B7…252B63D` | 2.5% |

Complete addresses, code/data hashes, deployment transaction, logical time, compiler version, parameters, opcodes and getters are committed in `deployments/testnet/bank.json` and `deployments/testnet/duel.json`.

## Verification

```bash
make contracts-build
make contracts-verify
make contracts-inspect
```

`contracts-verify` fails unless:

- the local build hash equals the manifest;
- the live account is active;
- live code and data hashes equal the manifest;
- the deployment transaction succeeded at the recorded logical time;
- the transaction has masterchain finality.

`contracts-inspect` decodes live storage using the generated Acton wrappers. The API also exposes read-only contract, wallet, transaction and Jetton diagnostics to authenticated users.

## Upgrade policy

V1 contracts are immutable in behavior except for explicit owner administration exposed by source. Pausing blocks new activity but never blocks user recovery paths. A new financial rule requires a new audited contract address and manifest; the backend is not allowed to emulate an on-chain fee or payout rule.
