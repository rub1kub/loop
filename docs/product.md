# Product model

LOOP is a social Telegram Mini App with transparent TON mechanics. Its core emotion is: **“I am taking part in a living cycle.”** It must never feel like a balance screen, a portfolio, or a wrapped wallet.

## Product boundaries

- LOOP never creates a wallet, imports a seed phrase, or stores spendable funds.
- The connected wallet remains external and is shown only when proof or signing is relevant.
- TON Connect is used for wallet ownership, transaction confirmation, payouts, and asset checks.
- On-chain activity becomes social evidence inside BANK; raw protocol detail remains available through proof links.
- The public release is testnet-only.

## BANK

BANK is the home screen and the primary product object. The object is a glass jar, not a numerical balance.

An empty jar asks the user to **start a cycle**. An active jar shows the cycle number, current day, progress, event count, the latest social event, and a history sheet. A cycle lasts seven days and completes when its configured event goal is reached.

Events include:

- cycle started;
- duel funded and finalized;
- opponent found;
- duel settled;
- contribution refunded;
- invitation accepted;
- other explicitly defined social milestones.

System events carry an application proof identifier. Blockchain-derived events carry the transaction hash and a network-specific explorer URL.

## DUEL

DUEL is a person-to-person challenge on equal terms. The interface uses the language of contribution, challenge, opponent, and confirmation. It does not expose probability controls or casino language.

The current product supports one protocol shape:

- both people choose the same contribution;
- the resulting on-chain terms are fixed at 50/50;
- funds move directly from external wallets into contract escrow;
- the client stores the local reveal secret needed by its owner;
- the contract settles or refunds according to the audited timeout paths.

AFK matchmaking lets a user confirm once and leave the Mini App. A direct invitation binds to a specific funded offer and never enters the generic AFK pool.

## Social layer

Telegram is part of the product, not only an authentication provider.

- Inline invitations say who issued the challenge, the contribution, and the terms.
- The **ПРИНЯТЬ** button opens the Mini App with an opaque, expiring invite code.
- An authenticated accepter resolves the server-side offer before any transaction is proposed.
- BANK turns matches, acceptances, results, and refunds into a chronological living cycle.

## Experience principles

- **Object first:** the jar is visually dominant; balances and wallet chrome are absent.
- **Visible state:** preparing, wallet confirmation, chain finalization, searching, matched, revealing, settled, and refundable are distinct.
- **Progressive disclosure:** the primary action is clear; transaction proofs and history are one interaction away.
- **Recovery first:** every funded path has an owner cancellation, settlement, or permissionless timeout path.
- **Telegram-native:** safe areas, BackButton, MainButton, haptics, start parameters, and inline mode are feature-checked and treated as first-class behavior.
- **Monochrome restraint:** black, white, and gray; one strong action per state; no crypto gradients or decorative Web3 chrome.

## Non-goals

LOOP is not a wallet, exchange, portfolio tracker, yield product, custodial account, Jetton issuer, or arbitrary betting interface. PROFILE describes identity, verified external wallet ownership, cycle activity, and settings; it is not an asset dashboard.
