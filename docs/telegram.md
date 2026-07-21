# Telegram integration

The Mini App loads Telegram's official bridge before application code, calls `ready()` and `expand()`, adopts theme/safe-area values, requests fullscreen when supported and uses native BackButton, MainButton and HapticFeedback with feature checks.

Only the raw `Telegram.WebApp.initData` string is sent to `/api/v1/auth/telegram`. `initDataUnsafe`, URL query values and `tgWebAppStartParam` are display hints until the server verifies the signed fields. Authentication data is never persisted in browser storage.

The bot supports `/start`, a menu Web App button and inline duel invitations. Invite codes are opaque, expire, and are resolved only after the accepting user has authenticated. The production webhook requires Telegram's secret-token header on an unguessable path.

Primary specification: <https://core.telegram.org/bots/webapps>.

