# LOOP design QA — DUEL circle and result

## Comparison target

- Source visual truth: `/Users/rub1kub/.codex/generated_images/019f8484-2d0b-7bf1-92e2-dbb541e7eaa8/exec-360f4f18-6779-43ec-9685-a3df04cc2e44.png` (`853 × 1844`).
- Browser implementation, boost: `docs/screenshots/qa-duel-boost-final.png` (`393 × 852`).
- Normalized side-by-side evidence: `docs/screenshots/qa-duel-comparison-final.png` (`802 × 892`). The source was downsampled to `393 × 852`; both compared screens use density 1.
- Additional browser evidence: default `docs/screenshots/qa-duel-default.png` (`393 × 852`), result `docs/screenshots/qa-duel-result.png` (`393 × 852`), low-height default `docs/screenshots/qa-duel-compact.png` (`390 × 664`), and low-height result `docs/screenshots/qa-duel-result-compact.png` (`390 × 664`).
- States: equal 50/50 setup, confirmed 60/40 boost, settled win, closed/open result details, and return to a new setup round.

## Findings

- No actionable P0, P1, or P2 differences remain.
- Typography: LOOP's existing system sans, numeric alignment, compact uppercase labels, weights, wrapping, and muted hierarchy remain consistent with the selected source.
- Spacing and layout: the round is the main object in both setup and live states. The boost composition follows the source's cinematic vertical rhythm while keeping the action above Telegram navigation. The `390 × 664` screen has no horizontal overflow; the primary action ends at `586.9px`, before the tab bar at `594px`.
- Colors and tokens: only black, white, and neutral grays are used. No blue action, gradient, or unrelated status color was introduced.
- Images and icons: real profile photos remain supported, with the existing Phosphor user icon as fallback. The result uses Phosphor's `NavigationArrow`; no handcrafted icon asset was added.
- Copy: a win is expressed once as the amount delivered to the wallet. Accounting rows are hidden under `ПОДРОБНОСТИ` until the user opens them.
- Focused evidence was not needed: the normalized full-view comparison keeps all player labels, ring boundaries, timer, event, and action legible. The result screen was checked separately because it is a different state from the source.

## Comparison history

1. P1: the old result arrow was a long glowing line through the center. It was replaced with a compact navigation pointer that rotates toward the confirmed winner and does not cross the payout text.
2. P1: the final screen repeated `ПОБЕДА`, `БАНК ТВОЙ`, `РЕЗУЛЬТАТ ПОДТВЕРЖДЁН`, net profit, and wallet payout. It now shows one payout fact; the accounting breakdown is collapsed by default.
3. P1: the setup state still used the legacy rectangular probability bar. The same circular DUEL object now appears before matchmaking, during play, and at settlement.
4. P1: a settled offer could still be treated as an active `matched` offer after the result was dismissed. The settled offer is now excluded from active state derivation, so `ИГРАТЬ ЕЩЁ` returns to a clean setup screen.
5. P2: the first browser render compressed the live round against the header and left an oversized empty field below. Boost spacing was rebalanced; the revised side-by-side evidence is `qa-duel-comparison-final.png`.

## Functional and responsive QA

- Default round is present and readable at `393 × 852` and `390 × 664`.
- Result details start closed, open on tap, and reveal the complete accounting.
- After `ИГРАТЬ ЕЩЁ`, the payout and result copy disappear and the setup circle returns.
- Settled result displays the contract payout (`+1,95 GRAM` in the fixture), not net profit (`+0,95 GRAM`).
- Browser console produced no warnings or errors in the checked DUEL states.
- Targeted component tests, ESLint, TypeScript, production Vite build, and packaged asset verification pass.

## Open questions

- None for this iteration.

## Implementation checklist

- [x] Elegant result pointer.
- [x] One payout fact instead of repeated victory copy.
- [x] Actual wallet payout in the orbit.
- [x] Result details collapsed by default.
- [x] Circular DUEL object on the setup screen.
- [x] Short-phone responsive check.

final result: passed
