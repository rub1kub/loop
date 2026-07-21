# LOOP design QA

## Scope

- Direction: **Living Jar** (selected option 1).
- Reference: [`docs/design/living-jar-reference.png`](docs/design/living-jar-reference.png).
- Implementation: [`docs/screenshots/bank.png`](docs/screenshots/bank.png).
- Comparison viewport and state: `390 × 844`, active BANK cycle, day 3 of 7.
- Full comparison: [`docs/qa/comparison-final.png`](docs/qa/comparison-final.png).
- Focus comparisons: [`typography`](docs/qa/comparison-focus-typography.png), [`controls`](docs/qa/comparison-focus-controls.png).

## Iteration history

### Iteration 1

- P1: intrinsic page width shifted the application shell and clipped the right edge.
- P2: jar was undersized, the event row was too wide, and the CTA/navigation sat too high.
- Fix: constrained the shell with `minmax(0, 1fr)`, corrected jar slot geometry, and rebuilt vertical rhythm against the reference.

### Iteration 2

- P2: small residual differences remained in jar alignment, event timestamp treatment, headline scale, and bottom controls.
- Fix: aligned the raster asset, made event/time treatment match the selected direction, and tightened typography and control spacing.

### Final comparison

- No actionable P0, P1, or P2 differences remain.
- P3 accepted: generated glass reflections and browser font antialiasing are not pixel-identical to the concept render.

## Functional QA

- Onboarding primary action advances to the next state.
- BANK history opens and exposes proof links.
- DUEL AFK action enters the searching state.
- PROFILE settings open as a bottom sheet.
- 320 × 720 BANK and DUEL states have no horizontal overflow and keep actions above navigation.
- 390 × 844 screenshots cover onboarding, loader, BANK, DUEL, PROFILE, and Telegram inline DUEL.
- Browser console: no errors or warnings in the validated flow.

final result: passed
