# Mainnet deployment evidence

This directory intentionally contains no live addresses before deployment.

Create `release.json` only through one explicit assurance path: `external_audit` with its report,
or `self_reviewed` with the pinned disclosure, adversarial review and bounty evidence. The reviewed
commit, SHA-256 evidence, mainnet owner, treasury, public invite-signing key and conservative
launch limits are mandatory. `make contracts-mainnet-preflight` fails closed until that evidence
is valid. The active release uses `self_reviewed`; it must never be described as independently
audited.

Before the production BANK deployment, deploy the audited BANK bytecode to a separate low-value
shadow address and complete a two-wallet deposit → payout cycle there. BANK cannot complete a real
cycle and return to an empty queue, so the final production address must never be used for this
test. Its manifest must instead bind the finalized shadow transactions and matching code hash.

After both production contracts are deployed paused and empty, add `bank.json` and `duel.json`
with finalized proofs and public source-verification URLs. DUEL additionally requires a finalized
settlement from two distinct dedicated mainnet canary wallets. Then run
`make contracts-mainnet-verify`. The gate rejects a BANK smoke that points at the production
address, live obligations, runtime limits that differ from audited limits, or an application
configuration that does not repeat the audited commit and report hash.

## Wallet addresses are network-specific — never read them from `acton wallet list`

A W5 (v5r1) wallet's address depends on `walletId`, which is `2^31 + network
global id`: `-3` on testnet, `-239` on mainnet. The same key therefore has two
different addresses, and `acton wallet list` prints the **testnet** one, because
Acton's wallet subsystem defaults to a testnet context.

Converting that address from `kQ…` to `UQ…` changes only the display flags, not
the account. Funding the converted address on mainnet sends real funds to an
account no mainnet wallet app will offer to control, and `acton run
deploy-*-mainnet` then fails with "wallet has no active state on mainnet",
because it correctly looks at the `-239` address, which is empty.

Get mainnet addresses from Acton itself under the target network:

```bash
acton script --net mainnet scripts/print-mainnet-wallets.tolk
```

Cross-check them against what the wallet app shows for the same seed before
sending anything. If the two disagree, stop: one of them is not the account you
think it is.
