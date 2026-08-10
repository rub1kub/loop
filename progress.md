Original prompt: Transform LOOP from an incorrect wallet-first implementation into a production-ready social Telegram Mini App built around BANK, DUEL, and a Telegram-native social layer. Credentials supplied separately are deliberately excluded from this file.

## Product decisions

- LOOP is not a wallet and has no internal spendable balance. TON Connect is limited to external wallet ownership proofs, transaction confirmation, payouts, and asset checks.
- BANK is a FIFO queue represented by a jar. Later deposits fund the oldest unfinished positions;
  progress comes only from verified contract allocation and can stop indefinitely.
- DUEL starts as an equal 50/50 person-to-person challenge. Once matched, both players get the
  same bounded window to increase their locked stake and chance.
- RATING is a monthly proof-backed reputation layer. Score never uses stake size, profit,
  balance, wins or losses.
- AFK matchmaking and direct Telegram invitations are separate paths. A direct challenge binds to one funded offer and cannot enter the generic pool.
- The contract is authoritative for escrow and outcomes. PostgreSQL stores idempotent social projections; Redis is disposable coordination state.
- Mainnet remains disabled pending an independent audit, legal review, multisig governance, recovery rehearsal, and verified backups.

## Completed

- Replaced wallet-goal domain behavior with BANK FIFO positions, partial progress, history, and
  proof references.
- Restricted the application, API, matcher, and bot to equal 50/50 DUEL terms while preserving the verifiable deployed contract.
- Added AFK matchmaking, exact-offer direct challenges, Telegram inline messages, and invitation acceptance flows.
- Rebuilt the Mini App around the selected monochrome Living Jar direction with functional onboarding, loader, BANK, DUEL, RATING, PROFILE, history, settings, and inline preview states.
- Added reader-facing BANK queue rank, active participants, a transparent monthly LOOP Score,
  SIGNAL/PULSE/ORBIT/LOOP levels, global ranking and a qualified-friend circle.
- Added masterchain-confirmed transaction validation, fail-closed checkpoints, contract/wallet/transaction/Jetton audit tools, and explorer proofs in application responses.
- Audited the existing testnet deployment: active state, bytecode hash match, deployment
  transaction, owner/treasury, current fee, protected owner controls, recovery permissions, and
  locked state.
- Passed frontend lint, unit tests, responsive Playwright flows and production build; strict API
  lint/type checks and proof-derived RATING integration tests; Acton contract coverage remains
  above the configured gate.
- Published commercial open-source documentation, screenshots, design comparison evidence, contribution guidance, security policy, deployment operations, and TON audit details.
- Published the active product line on `main` using Conventional Commits and immutable releases.

## Remaining operational gates

- Resolve the GitHub account billing lock if hosted Actions remain unable to start.
- Keep mainnet disabled until all documented release gates are complete.

## Latest iteration

- Added a fourth onboarding story for PLUSH BRICK with concise fee/buyback context.
- Added direct purchase paths for dTrade, RedoTrade, and STON.fi using Telegram-native link
  bridges with a browser fallback.
- Added a dedicated mock route (`?screen=onboarding-plush`) for repeatable visual QA.
- Targeted tests cover the fourth story, all three market URLs, and Telegram-native navigation;
  the 430 × 720 visual pass fits without overlap or new console errors.

## Active goal: dynamic DUEL and BANK maturity limits

- DUEL v1.3 opens a 60-second boost window after matching. Confirmed top-ups change each
  player's chance in direct proportion to their locked stake, use a 20-second anti-sniping
  extension, stop after 180 seconds, and never exceed a 90/10 split.
- Reveals are rejected until the boost window closes. Boost transactions bind revision,
  minimum acceptable resulting chance, sender, duel, offer, amount, and expiry.
- BANK v1.3 starts with a 5 GRAM principal limit, unlocks 10 GRAM after 25 completed
  positions, 15 GRAM after 100, then grows by 5 GRAM per 250 completions up to 100 GRAM.
- Contract verification passes 13 BANK and 45 DUEL tests. Contract coverage is 99.7% for
  lines and 83.5% for branches; critical/major mutation scores are 88.2% for BANK and 96.7%
  for DUEL.
- A finalized two-wallet testnet canary created a direct pair, confirmed a 0.1 GRAM boost,
  observed the 54.54/45.46 split, waited for the real deadline, revealed both secrets, and
  settled without leaving locked value.
- API (82), web (57), security (13), fresh migration, and four repeated viewport/keyboard
  stress modes pass.

## 2026-08-02: simplified DUEL surface

- Kept the DuelEscrow flow and all recovery actions unchanged; this iteration is frontend-only.
- Reduced the idle screen to stake, equal start, winner payout and one plain-language rule.
- Moved fee, pool math and timeout details behind `КАК ЭТО РАБОТАЕТ`.
- Collapsed the boost form behind one optional `УСИЛИТЬ СВОЮ СТОРОНУ` action.
- Replaced the user-facing reveal terminology with `ОТКРЫТЬ РЕЗУЛЬТАТ` and `ОТКРЫТЬ ДО`.
- Kept every confirmed boost available in the collapsed `ХОД ДУЭЛИ` history.

## 2026-08-02: physical BANK GRAM tokens

- The BANK fill remains a collection of GRAMчики, not sand: every token now owns its engraved
  mark, in-plane rotation, face direction and damped angular motion.
- A shared jar light replaces random checkerboard shades; near-edge and reverse-facing marks
  are deliberately less readable, while live additions fall through the neck one at a time.
- Replaced the blocking 360-frame startup fast-forward with immediate random-drop placement.
  This removes the extra startup long task and prevents equal spheres crystallising into rows.
- Token radii vary within one recognisable set, initial placement is overlap-free, and the live
  physics still settles without permanent jitter.
- Targeted physics tests and mobile Chromium visual inspection cover orientation, resting,
  overlap, fill count, viewport fit and console errors.

## 2026-08-03: official GRAM token mark

- Replaced the ambiguous filled TON-like triangle on every BANK token with the current official
  GRAM diamond-and-spark geometry from TON's media asset pack.
- Kept the mark as a monochrome material stamp so it follows LOOP's visual system while retaining
  each token's natural in-plane rotation.
- Removed face-on perspective compression: every small token now keeps a complete, recognisable
  mark instead of occasionally collapsing it into a line.

## 2026-08-03: account-scoped BANK preview

- Added an opt-in, Telegram-ID-scoped BANK progress preview for persistent production UI testing.
- The preview is calculated only while serialising API responses: PostgreSQL, the chain worker,
  contract state, queue order and payouts remain authoritative and untouched.
- Real progress above the preview always wins; the override remains safe on either network because
  no transaction builder, chain projection or contract state consumes the displayed value.
- The VPS deploy helper now detects a pending production environment before its same-commit
  shortcut, so configuration-only releases are applied atomically instead of being skipped.

## 2026-08-03: one-decision DUEL interface

- Removed the decorative player diagram, duplicate condition cards and repeated live-state copy.
- Idle DUEL now shows only the editable stake, equal start, one sentence and the primary action.
- Search and matched states use one large value, one timer and only the action available at that
  stage; the reveal action becomes primary after the stake window closes.
- Merged fee math, timeout rules and confirmed additions into one collapsed `ПРАВИЛА` section.
- Raised the client-side minimum to 0.5 GRAM per player so it matches the active 1 GRAM equal-pool
  constraint instead of allowing a transaction that the service would reject.
- Focused component tests and mobile Chromium/WebKit DUEL flows pass; desktop and 390 px visual
  inspections cover idle, rules, searching, matched, add-GRAM, invite and result states.

## 2026-08-03: centred tablet surfaces

- Centred every phone-width Mini App surface inside the full Telegram viewport instead of relying
  on the full-width root container to position its child.
- Added portrait and landscape tablet regression coverage for the prelaunch screen, plus the
  prelaunch state to the narrow-screen overflow suite.
- Browser checks at 800 × 1280 and 1024 × 768 confirm a centred 430 px surface with no horizontal
  page overflow.

## 2026-08-10: BANK neck ejection

- Removed the redundant `До ближайшей выплаты — … GRAM` pulse while preserving actionable
  messages about how many positions the next entry closes.
- Expanded token simulation from the inner chamber to the full visible vessel: glass shoulders
  are solid, only the real central neck is open, and a token crosses the lip continuously.
- Added a restrained powered lift through the empty headroom, followed by ordinary gravity,
  rotation, rim collision and return through the neck; the animation emits at most one idle token.
- Every exterior physics substep clamps the full token radius inside the BANK stage, including
  extreme velocity, device tilt and viewport resize cases. Reduced-motion mode remains static.
- Mock-only deterministic time/state hooks cover visual QA. Focused physics/UI tests pass, and
  Chromium checks at 390 × 844 and 1024 × 768 show no nearest-payout copy, overflow or console errors.

## 2026-08-10: BANK device tilt recovery

- Decoupled direct device tilt from `prefers-reduced-motion`: that preference now suppresses only
  autonomous ejections and pointer disturbance, while the physical solver remains responsive.
- Replaced the fragile version gate with Telegram DeviceOrientation feature detection, corrected
  the requested interval to 20 ms, and re-arms tracking after fullscreen changes and activation.
- Added a W3C `deviceorientation` fallback for Swiftgram and other third-party clients that return
  `UNSUPPORTED`; iOS permission is requested only from a direct tap on the BANK object.
- Unit coverage verifies Telegram start/restart, radians-to-gravity mapping, browser fallback,
  cleanup and one-shot permission. Chromium sensor simulation visibly moves the pile both ways,
  including with reduced motion enabled, without console errors.

## 2026-08-10: BANK full-screen token flight

- Split BANK rendering into an inner jar canvas and a transparent screen-stage flight layer, so
  escaped GRAM tokens can continue below the vessel and pass behind the percentage, copy and CTA.
- Mapped the real neck into screen coordinates and kept the full token radius inside the visible
  application stage during flight, bounce and viewport resize.
- Added an outward impulse at the lip for the restrained idle ejection, preventing the token from
  immediately retracing its path into the same opening.
- A returning token now checks whether the neck is occupied and visibly bounces away instead of
  being inserted into another token; sustained tilt/reversal tests guard pile interpenetration.
- Focused physics/UI tests and a production build pass. Chromium inspection at the BANK mobile
  surface shows tokens below the CTA, behind readable controls and still inside the screen bounds.

## 2026-08-10: solid BANK flight collisions

- Added equal-mass collisions for escaped GRAM tokens, including positional separation and a
  spatial grid so several tokens cannot overlap without turning the animation into an O(n²) loop.
- The complete glass body now blocks exterior tokens at its sides, shoulder and bottom; a bounded
  flight step prevents high-speed tunnelling while the real neck remains the only way back inside.
- Modelled the vessel's rounded lower corners and a subpixel wall clearance so tokens remain fully
  inside the visible glass instead of peeking through the image at its curved edges.
- Regression tests reproduce token-on-token penetration, side tunnelling and bottom tunnelling at
  extreme speed. Focused BANK tests and production build pass.
- Chromium mobile inspection confirms a rounded contained pile, separated exterior tokens, full
  screen bounds and no new console errors.
