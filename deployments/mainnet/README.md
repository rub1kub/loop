# Mainnet deployment evidence

This directory intentionally contains no live addresses before deployment.

Copy `release.example.json` to `release.json` only after an independent audit. The audited commit,
report file and SHA-256, mainnet owner, treasury, public invite-signing key and conservative launch
limits are mandatory. `make contracts-mainnet-preflight` fails closed until that evidence is valid.

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
