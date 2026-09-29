Original prompt: Transform LOOP from an incorrect wallet-first implementation into a production-ready social Telegram Mini App built around BANK, DUEL, and a Telegram-native social layer. Credentials supplied separately are deliberately excluded from this file.

> **Archive:** this is a chronological implementation journal. It intentionally preserves old
> testnet plans, intermediate limits and unfinished wording. For current runtime facts use
> [`docs/agents/current-state.md`](docs/agents/current-state.md); for agent work start at
> [`docs/agents/README.md`](docs/agents/README.md).

## 2026-09-29: pixel battle (implementation, not released)

- User approved a free off-chain collaborative canvas, visible behind each main screen, with a separate full-screen drawing mode and a commit after verification.
- Added a separate pixel module: durable 30-second player cooldown, serialized revisions, idempotent moves, weekly archives, area-time team scoring, auditable moderation and frozen share cards. Runtime activation is explicit via `LOOP_PIXEL_BATTLE_ENABLED` after migration.
- Added the full-screen drawing mode, a subdued shared background, pan/pinch/keyboard controls, Telegram BackButton priority, reconnect-safe synchronization and share crops. No production state or contracts have been changed.
- Verified PostgreSQL concurrency and Redis wakeups/leases, the previous-to-head migration and matching ORM schema, authenticated API rules and mobile browser flows. Pixel rules and release instructions are in `docs/pixel-battle.md`.
- Verification: 30 API/PostgreSQL/Redis tests, 43 focused web tests, browser drawing/background/CSS-failure flows in Chromium and WebKit, plus native pinch injection in Chromium. Ruff, mypy, ESLint, TypeScript, production asset verification and changed-file formatting pass. WebKit native pinch injection is skipped; no physical-device or live Telegram share test has been performed.

### Full-screen refinement before the requested production release

- User requested edge-to-edge canvas/background and removal of motivational interface copy, using Sepia. Scope: viewport/layout and pixel copy; the shared 128×128 coordinate space and server rules remain unchanged.
- Sepia refactor stage 1 (UI copy): loaded canonical SKILL, professional-pass, style-pass and model-fingerprints from Nanako0129/sepia. Author: unknown, executor: GPT version unknown; prose layers: none/prior. Venue: existing concise app actions and the user's explicit preference for minimal labels.
- Findings: check 2 density — redundant «ОБЩИЙ ФОН LOOP» above «ПОЛОТНО»; check 3 relevance and check 8 templatedness — «Приближай · выбирай · рисуй»; check 3 — invitation filler «Помоги дорисовать» and empty-ranking prompt «Первый рисунок команды начнёт её счёт». Style scan: repeated imperative template; rhythm: none (short UI labels). Passed: 1, 4, 5, 6, 7, 9, 10. Verdict: refactor these strings, preserve rule facts and actionable error messages.
- Implemented fixed, viewport-wide canvas/background, floating safe-area controls and a shared cover projection for rendering, pan constraints and hit testing. No visual board frame or letterbox region remains. Sepia deletion/reversion checks kept concise actions, connection errors and rule facts; removed motivational copy rather than replacing it with new slogans.
- Verified the updated projection with 14 focused web tests and the full pixel browser file: 11 passed, native-touch WebKit injection skipped. Coverage now asserts edge-to-edge canvas/background at 320/390/430/768/1280 px, safe areas, drawing, cooldown, panning, sharing and return navigation. Inspected Chromium/WebKit screenshots and the prescribed game-client screenshot/state; no new browser errors. ESLint, Ruff and diff checks passed.

### Production release, 29 September 2026 (Moscow)

- User explicitly requested production activation. Published `5cbc449` and refinement `e73dde2` to GitHub, then deployed full runtime/web `e73dde2305685e6b56162af184fb49b5efe52598` through `scripts/deploy-vps.sh deploy` with the standard gates, backup and migration.
- Staged only `LOOP_PIXEL_BATTLE_ENABLED=true`; a comparison verified all other production settings were preserved. The staged file was consumed by the release. No contract broadcast, BANK reopening, bot broadcast or financial operation was performed.
- At 2026-09-28 21:51 UTC all five services were healthy; public assets, `/live`, `/ready`, bot/webhook status and matching runtime/web SHAs passed. The live feature probe verified enabled state, seven tables, migration head, snapshot serialization and JPEG encoding, and rolled back its transaction. Unauthenticated canvas returned 401, missing public card 404.
- The standard gate passed API tests (dedicated PostgreSQL/Redis tests skipped without their isolated URLs), all 189 web tests, type checks, lint, formatting, production build and migration validation. Earlier isolated PostgreSQL/Redis tests remain documented above. Production npm audit returned zero vulnerabilities; GitHub push separately reported 12 dependency alerts, not triaged in this UI release. Physical-device Telegram sharing remains a manual check.

### 2026-09-29: Telegram fullscreen safe-area correction

- Reproduced the pixel title/actions overlapping simulated native Telegram controls at 390×844.
  Previous checks only set a single CSS top inset and did not model the separate status-bar and
  Telegram-controls rows. Confirmed additive semantics against Telegram's iOS implementation.
- Changed shared native/CSS safe-area calculation to device + content, with a 56 px controls-row
  fallback while fullscreen events arrive. Browser `env()` and native device values remain
  alternatives, not an extra sum. Preserved keyboard height freezing and protected top boundary.
- Added unit regressions for all edges, delayed/zero native content insets, fullscreen transitions
  and ordinary browsers; the three relevant assertions failed before the fix. Focused web tests:
  48 passed. Chromium/WebKit native-chrome simulation verifies 320/390/430/768 px, launcher and
  header hit targets, late inset events, CSS-first insets and full-viewport canvas. Inspected both
  browser screenshots and the required game-client screenshot/state; no new console errors.
- Existing WebKit pixel suite: 3 passed, native pinch injection skipped. The legacy
  `modes.stress.spec.ts` cases reach tab navigation but time out on an undismissed mock announcement;
  this unrelated fixture issue was not changed. After dismissing that announcement, separate
  Chromium/WebKit checks cover 20 keyboard resize cycles and six tab transitions.
- TypeScript, changed-file ESLint, Prettier and diff checks pass. Browser CLI logs/screenshots stay
  in `output/`. Physical-device Telegram remains a manual check.
- Released web `ea8a18d6f422e41576e290178749f0cd4349cc84` via the standard gated web-only path;
  all 191 web tests, API tests (nine dedicated infrastructure tests skipped), production build,
  lint/type/format and migration checks passed. At 2026-09-29 08:53 UTC the live web SHA,
  12 public dependencies, all five service health states and bot/webhook checks passed. Runtime
  stayed on `e73dde2`; API/workers were not restarted, no DB/config/contracts/funds were changed.

### 2026-09-29: two-second pixel cadence and BANK first-screen layout

- User requested one free pixel every two seconds, the BANK position button visible without
  scrolling, and a visible shared canvas behind BANK. Changed the authoritative server rule,
  snapshot metadata, mock cadence and rules/share copy together. Share-image generation retains
  its independent 30-second limit. No schema, auth, contract, financial rule or production
  dependency changes.
- Client validates a positive server-provided interval instead of hard-coding 30; it accepts
  both previous/current releases. Added exact 1.999/2.000-second boundary and Retry-After checks,
  retained cross-session/week cooldown and old-idempotency-receipt protection.
- BANK's fixed-height jar and repeated bottom safe-area reservation pushed its CTA below the
  tab bar after Telegram header protection. The jar now flexes into available space; compact
  screens combine the two footer labels. Increased canvas background opacity from 13% to 32%
  and masked the two opaque black jar-image backdrops, preserving the glass and ball physics.
- Verified 22 focused API tests, 27 web unit tests, and seven pixel browser scenarios across
  Chromium/WebKit (one WebKit native-pinch injection skipped). Expanded the existing browser
  checks with two successive moves, realistic 115/34 px safe areas and first-screen CTA bounds.
  The five-viewport navigation scenario needed a 60-second budget instead of 30; it passed in
  both browsers. Final mask/background recheck passed separately in both engines.
- Inspected native-chrome simulations at 320×568, 320×640, 390×844, 430×932, 768×1024 and
  desktop, plus the prescribed game-client screenshot/state. No new browser errors. Dedicated
  local PostgreSQL/Redis services are not running, so their unchanged lock tests were not
  repeated; previous isolated verification remains above. Physical Telegram device check remains
  manual. Production release follows the standard full-runtime gate because the API rule changed.

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
- Mainnet was activated on 2026-08-01 through the documented self-reviewed path; no independent
  external audit was completed.

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

## Superseded operational gates

The former GitHub Actions billing blocker and «keep mainnet disabled» plan no longer apply.
Production releases go directly to the VPS. Current risks and gates are maintained in the agent
knowledge base rather than this journal.

## Latest iteration

- Added a fourth onboarding story for PLUSH BRICK with concise fee/buyback context.
- Added direct purchase paths for dTrade, RedoTrade, and STON.fi using Telegram-native link
  bridges with a browser fallback.
- Added a dedicated mock route (`?screen=onboarding-plush`) for repeatable visual QA.
- Targeted tests cover the fourth story, all three market URLs, and Telegram-native navigation;
  the 430 × 720 visual pass fits without overlap or new console errors.

## Historical goal: dynamic DUEL and BANK maturity limits

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

## 2026-08-10: stable first keyboard focus in TEAMS

- Removed mount-time autofocus from team creation and search: Telegram now opens the keyboard only
  from a real user tap, after the subpage transition has settled.
- Preserved the pre-keyboard tall/compact layout decision while the visual viewport is reduced, so
  the 720px responsive breakpoint cannot shrink the TEAMS title and pull the form upward.
- Added a no-membership TEAMS mock state plus component and mobile Chromium regression coverage for
  the complete `КОМАНДЫ → СОЗДАТЬ СВОЮ → НАЗВАНИЕ` first-focus flow.
- Mobile validation keeps the app height, subpage header, name field and screen scroll origin fixed
  after the simulated keyboard reduces the viewport from 839px to 520px.

## 2026-08-10: centred BANK on Fold-sized screens

- Made screen gutters symmetric using the larger Telegram safe-area inset, so a one-sided fold,
  hinge or cutout no longer shifts BANK and the surrounding interface off the physical centre.
- Removed the browser's native button padding from the BANK object and anchored the vessel to its
  true 50% axis, including pressed and hover micro-interactions.
- Tightened labels in the five-item tab bar below 351px so long Russian names stay inside their
  columns instead of overflowing on narrow cover screens.
- Added a 360 × 800 Fold-cover regression with a simulated asymmetric 24px inset. Chromium and
  WebKit keep the shell, heading, vessel and state centred with no horizontal page overflow.

## 2026-08-10/13: circular DUEL arena

- Selected the monochrome circular probability direction for the live DUEL surface.
- The ring reads only contract-confirmed shares; the result needle is a reveal animation and never
  calculates, changes or substitutes the settled winner.
- Added live player identities, pool, authoritative countdown, latest confirmed boost and a clear
  solid boost action while preserving the existing transaction and reveal state machine.
- Settled results make three restrained rotations in 1.9 seconds and land inside the already-known
  winner sector; active waiting states have no needle and reduced-motion skips suspense safely.
- Ambiguous wallet callbacks now preserve and reconcile funding instead of discarding it; stale
  quote cleanup atomically releases AFK/direct reservations.
- Focused DUEL component, API and responsive browser coverage passes; production runs the same
  release captured in `docs/agents/current-state.md`.

## 2026-08-12: weekly BANK Wave

- Added one restrained Sunday activation: eight distinct confirmed BANK entrants between 20:00
  and 20:30 Moscow time unlock a real 5 GRAM operator position.
- Kept the BANK surface compact: one teaser opens a separate sheet with the counter and plain
  rules; there is no cash prize, campaign tab or permanent explanatory block.
- Wave completion depends on an indexed on-chain position from the configured public operator
  wallet. The last distinct entrant receives only the closing status and a Telegram share action.
- Added durable, deduplicated opening/result Telegram messages behind the existing notification
  toggle, plus schedule, counting, proof and UI regression coverage.
- Capped the first season at four verified 5 GRAM positions (20 GRAM from the 33.27 GRAM reserve)
  and stop advertising further Waves once the cap is reached.
- Added a guarded control-panel transaction: after eight people enter, only the configured Wave
  wallet can sign the promised position; repeated preparation is blocked while confirmation is
  pending and the public result stays honest until the indexer sees the proof.
- API, migration, notification and frontend regression tests pass. The supplied Playwright game
  client shows a compact teaser and a clean separate rules sheet with no console errors.
