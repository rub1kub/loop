# Mainnet deployment evidence

This directory intentionally contains no live addresses before deployment.

Copy `release.example.json` to `release.json` only after an independent audit. The audited commit,
report file and SHA-256, mainnet owner, treasury, public invite-signing key and conservative launch
limits are mandatory. `make contracts-mainnet-preflight` fails closed until that evidence is valid.

After deployment, add `bank.json` and `duel.json` with finalized smoke proofs and public source
verification URLs. DUEL additionally requires a finalized settlement from two distinct dedicated
mainnet canary wallets. Then run `make contracts-mainnet-verify`.
