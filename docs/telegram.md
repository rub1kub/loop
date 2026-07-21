# Telegram integration

Telegram is LOOP's identity and social transport. It does not define financial state and is never trusted to supply duel terms.

## Mini App lifecycle

The document loads Telegram's official bridge before application code. The client feature-checks and uses:

- `ready()` and `expand()`;
- viewport and safe-area variables;
- BackButton and MainButton;
- HapticFeedback for primary actions, success, warning, and error;
- fullscreen requests where supported;
- theme parameters while retaining LOOP's monochrome product palette.

Only the raw `Telegram.WebApp.initData` string is sent to `/api/v1/auth/telegram`. The API validates the Bot API HMAC construction, duplicate keys, age, and future skew before issuing a short-lived session. `initDataUnsafe`, URL values, and `tgWebAppStartParam` are display hints until the server verifies them. Raw authentication data is not persisted in browser storage.

## Inline DUEL

After a creator's offer is finalized on TON, **Пригласить в игру** invokes `switchInlineQuery` with the exact on-chain offer id. The bot resolves that offer under the authenticated application model and returns a message containing:

```text
LOOP DUEL

Игрок вызывает тебя.

Вклад:
2 GRAM

Условия:
Равные · 50/50

[ПРИНЯТЬ]
```

The button opens the Mini App with an opaque, expiring challenge code. After Telegram authentication, the API resolves the code to the creator user, creator offer, fixed contribution, total pool, 50/50 condition, state, and expiry. A direct offer names that exact counter-offer and never enters generic AFK matchmaking.

Inline messages cannot override an amount, wallet, contract, probability, expiry, or offer state. Deleted, expired, funded by the accepter, non-50/50, or already-consumed challenges are rejected server-side.

## Bot surface

The bot supports:

- `/start` with a Mini App button;
- a persistent menu Web App button;
- inline duel invitations;
- start parameters for direct challenges and referrals;
- outbox-backed notifications for important social and on-chain states.

The production webhook uses an unguessable path and validates Telegram's secret-token header. Bot API configuration may set the webhook and menu, but inline capability itself must be enabled once through BotFather `/setinline`. Deployment acceptance checks `getMe.supports_inline_queries`.

The application configures the public bot name, description, short description, `/start` command, and **Открыть LOOP** menu button at API startup so a container restart cannot restore obsolete wallet-first copy.

BotFather-only presentation settings cannot be changed through Bot API:

- `/setinline` → `@getloopbot` → placeholder `Брось вызов в LOOP`;
- `/setuserpic` → `@getloopbot` → upload [`docs/brand/loop-avatar.png`](brand/loop-avatar.png);
- group membership may remain disabled unless a future product flow explicitly requires the bot to join chats; inline sharing works without membership.

Primary specifications:

- <https://core.telegram.org/bots/webapps>
- <https://core.telegram.org/bots/webapps#initializing-mini-apps>
- <https://core.telegram.org/bots/inline>
- <https://core.telegram.org/bots/api>
