# Архитектура и данные

## Компоненты времени выполнения

| Компонент       | Код                                   | Ответственность                                                   |
| --------------- | ------------------------------------- | ----------------------------------------------------------------- |
| Mini App        | `apps/web/src`                        | Telegram lifecycle, UI, TON Connect и построение сообщений        |
| Browser control | `apps/web/src/control`                | owner login, intake switches и подготовка admin transactions      |
| API             | `apps/api/app/main.py`, routers       | auth, валидация, quote/intents, read models                       |
| Telegram bot    | `apps/api/app/bot.py`                 | `/start`, menu button, webhook и inline DUEL                      |
| Chain worker    | `apps/api/app/chain_worker.py`        | finalized TON transactions → идемпотентные PostgreSQL projections |
| PostgreSQL      | SQLAlchemy + Alembic                  | продуктовые данные, проекции, checkpoints и audit                 |
| Redis           | `nonce_store.py`, middleware, metrics | одноразовые challenge, rate limits и временная координация        |
| Contracts       | `contracts/bank`, `contracts/duel`    | финансовые правила, escrow, выплаты и recovery                    |
| Reverse proxy   | `deploy/apache`, `deploy/nginx`       | TLS, CSP, rate limits, static assets и API proxy                  |

## Главные потоки

### Запуск Mini App

1. Клиент ставит interaction/viewport guards.
2. Telegram bridge читается сразу или загружается асинхронно.
3. `initData` берётся из `Telegram.WebApp.initData`; desktop fallback читает исходный
   `tgWebAppData` из hash/query.
4. `POST /api/v1/auth/telegram` проверяет HMAC Bot API, duplicate keys, возраст, future skew и
   одноразовый digest.
5. API создаёт/обновляет `User`, записывает допустимый referral start param и выдаёт короткую
   подписанную bearer session.
6. Zustand параллельно загружает profile, BANK, DUEL и rating.
7. `duel_<code>` открывает проверенный invite; неподписанный `start_param` сам по себе не
   является авторитетным.

Bearer token хранится только в памяти модуля `api.ts`. При `401` один общий reauthentication
promise повторяет Telegram auth и повторяет только безопасный запрос.

### Привязка внешнего кошелька

1. Аутентифицированный пользователь запрашивает одноразовый TON proof payload.
2. TON Connect подписывает proof внешним кошельком.
3. API получает публичный ключ кошелька из TON, проверяет signature, origin, payload, timestamp,
   network и canonical address.
4. В PostgreSQL ровно один wallet пользователя становится active; пара `(network,address)`
   уникальна.

Proof не переводит средства и не подтверждает будущую транзакцию.

### Финансовое действие

1. Клиент проверяет ввод и запрашивает preview/quote или action intent.
2. API проверяет intake switch, текущий контракт, verified wallet, лимиты, race constraints и
   создаёт `pending_*` запись.
3. API возвращает ограниченный по времени contract call; для direct DUEL — address-bound permit.
4. Клиент повторно проверяет context quote и сериализует Tolk message body.
5. TON Connect просит внешний кошелёк подписать и отправить.
6. UI остаётся pending: wallet callback не меняет финансовый статус.
7. Worker читает транзакции контракта в порядке logical time и принимает только успешные
   masterchain-finalized события.
8. Одна PostgreSQL transaction/savepoint применяет соответствующую BANK или DUEL projection.
9. Повторная доставка отбрасывается по уникальной event identity.

### Owner control

1. `/control` не инициализирует Telegram.
2. TON proof challenge имеет роль `control`, production origin и network.
3. Для session адрес должен совпасть с `LOOP_CONTROL_ADMIN_WALLET`; подготовка contract
   transaction дополнительно требует совпадения с живым owner выбранного контракта.
4. API выдаёт cookie `HttpOnly; Secure; SameSite=Strict; Path=/api/v1/control` на один час.
5. UI готовит BOC payload, а внешний owner wallet подписывает admin transaction.
6. Контракт повторно проверяет owner и reserve invariants.
7. Worker синхронизирует `ContractControl` и добавляет подтверждённый audit event.

Browser и API не могут выполнить admin действие без owner signature.

## Frontend

### Entrypoints

- `apps/web/src/main.tsx` выбирает surface по pathname.
- Mini App: `bootstrap.tsx` → `App.tsx`.
- Control: `control/bootstrap.tsx` → `control/ControlApp.tsx`.
- `/control/*` обслуживается тем же Vite bundle и SPA fallback, но загружает отдельные CSS и
  React tree.

### Состояние Mini App

`store.ts` хранит:

- `activeTab`: `bank | duel | rating | profile`;
- profile и verified wallet;
- текущую BANK position и историю;
- offers, duels и открытый invite;
- rating;
- onboarding/error/loading.

Активные BANK/DUEL состояния обновляются каждые пять секунд. Рейтинг на активной вкладке —
каждые двадцать секунд. Секрет завершённого DUEL удаляется из SecureStorage.

### Клиентская валидация

- Все основные API responses проверяются Zod-схемами.
- GET/auth запросы повторяются на `408/425/429/502/503/504`; мутации автоматически не
  повторяются.
- Transaction builder требует network `-3`, canonical context и ожидаемые quote fields.
- Browser mock включается только compile-time флагом и не умеет broadcast.

### Важные frontend-файлы

| Зона                      | Файл                                            |
| ------------------------- | ----------------------------------------------- |
| композиция приложения     | `apps/web/src/App.tsx`                          |
| API/session/retry         | `apps/web/src/api.ts`                           |
| глобальное состояние      | `apps/web/src/store.ts`                         |
| типы wire model           | `apps/web/src/types.ts`                         |
| Telegram bridge           | `apps/web/src/telegram.ts`                      |
| safe areas/keyboard       | `apps/web/src/viewport.ts`                      |
| запрет select/zoom/drag   | `apps/web/src/interactionGuards.ts`             |
| TON message builders      | `apps/web/src/ton.ts`                           |
| BANK                      | `apps/web/src/features/bank/BankScreen.tsx`     |
| DUEL                      | `apps/web/src/features/duel/DuelScreen.tsx`     |
| рейтинг                   | `apps/web/src/features/rating/RatingScreen.tsx` |
| профиль                   | `apps/web/src/components/ProfileScreen.tsx`     |
| control                   | `apps/web/src/control/ControlApp.tsx`           |
| глобальные стили Mini App | `apps/web/src/styles.css`                       |
| стили control             | `apps/web/src/control/control.css`              |

## HTTP API

Все пути ниже, кроме health/internal, имеют базу `/api/v1`.

### Identity и social

| Method  | Path                               | Назначение                                 |
| ------- | ---------------------------------- | ------------------------------------------ |
| `POST`  | `/auth/telegram`                   | проверить initData и выдать bearer session |
| `GET`   | `/me`                              | profile, wallet, mode stats, PLUSH status  |
| `PATCH` | `/me/settings`                     | onboarding flags                           |
| `POST`  | `/wallet/challenge`                | одноразовый TON proof payload              |
| `POST`  | `/wallet/verify`                   | проверить и активировать внешний wallet    |
| `GET`   | `/onchain/contracts/{mode}`        | live contract state + hash match           |
| `GET`   | `/onchain/jettons/{jetton_master}` | доказать Jetton wallet и balance           |
| `GET`   | `/referrals`                       | referral link, counts и reward history     |
| `GET`   | `/rating`                          | вычисляемый season score, lists и pulse    |
| `GET`   | `/invites/{code}`                  | preview прямого DUEL                       |
| `POST`  | `/invites/{code}/accept`           | привязать invite к verified user wallet    |

`GET /onchain/contract` — скрытый legacy alias текущего DUEL diagnostics.

### BANK

| Method | Path                      | Назначение                                 |
| ------ | ------------------------- | ------------------------------------------ |
| `POST` | `/bank/positions/preview` | чистая математика суммы/цели/комиссии/газа |
| `POST` | `/bank/positions/quote`   | создать pending intent и contract call     |
| `GET`  | `/bank/positions/current` | текущая активная position                  |
| `GET`  | `/bank/positions`         | история пользователя                       |

### DUEL

| Method | Path                                     | Назначение                              |
| ------ | ---------------------------------------- | --------------------------------------- |
| `POST` | `/duels/offers/quote`                    | создать AFK/direct/accept intent        |
| `GET`  | `/duels/offers`                          | offers пользователя                     |
| `GET`  | `/duels`                                 | duels пользователя                      |
| `POST` | `/duels/{duel_id}/reveal-intent`         | BOC context для reveal                  |
| `POST` | `/duels/offers/{offer_id}/cancel-intent` | отмена открытого offer                  |
| `POST` | `/duels/offers/{offer_id}/expire-intent` | permissionless expiry offer             |
| `POST` | `/duels/{duel_id}/expire-intent`         | settlement/refund после reveal deadline |

`POST /duels/quote` — скрытый legacy alias quote.

### Control

| Method   | Path                    | Назначение                                 |
| -------- | ----------------------- | ------------------------------------------ |
| `POST`   | `/control/challenge`    | owner TON proof payload                    |
| `POST`   | `/control/session`      | создать owner cookie                       |
| `GET`    | `/control/session`      | проверить session                          |
| `DELETE` | `/control/session`      | logout                                     |
| `GET`    | `/control/overview`     | intake, metrics, live contracts и audit    |
| `PATCH`  | `/control/application`  | maintenance/BANK/DUEL intake               |
| `POST`   | `/control/transactions` | подготовить owner-signed admin transaction |

### Operational

- `GET /live` — процесс отвечает.
- `GET /ready` — PostgreSQL и Redis доступны.
- `GET /metrics` — bearer-protected Prometheus metrics; публичный nginx возвращает `404`.
- `POST /api/internal/duel-canary` — bearer-protected отчёт, который сервер перепроверяет в TON.
- Telegram webhook path конфигурируется и защищён secret-token header.

## PostgreSQL

Текущая Alembic head: `20260723_0007`.

### Shared

| Таблица                 | Назначение                                           |
| ----------------------- | ---------------------------------------------------- |
| `users`                 | Telegram identity и onboarding                       |
| `auth_exchanges`        | одноразовый digest принятого initData                |
| `wallets`               | доказанные адреса, один active wallet на user        |
| `referral_codes`        | один код на owner user                               |
| `referral_attributions` | один inviter edge на invitee и qualification         |
| `referral_rewards`      | legacy/product reward history                        |
| `chain_checkpoints`     | per-contract last LT и heartbeat                     |
| `application_control`   | durable intake switches                              |
| `contract_control`      | последняя проверенная admin-конфигурация контракта   |
| `admin_audit_events`    | prepared/applied/confirmed административные действия |

### BANK bounded context

| Таблица             | Назначение                               |
| ------------------- | ---------------------------------------- |
| `bank_positions`    | intent + проверенная очередь/прогресс/tx |
| `bank_payouts`      | одна подтверждённая выплата на position  |
| `bank_chain_events` | идемпотентные декодированные события     |

Один wallet может иметь только одну position в активных состояниях. `(network, contract,
position_id)`, `(network, contract, query_id)` и event identity уникальны.

### DUEL bounded context

| Таблица             | Назначение                                                 |
| ------------------- | ---------------------------------------------------------- |
| `duel_offers`       | intent, ставка, commitment, mode, reservation и funding tx |
| `duels`             | matched pair и terminal state                              |
| `duel_players`      | связь duel ↔ offer/user/wallet                             |
| `duel_commits`      | подтверждённый commitment tx                               |
| `duel_reveals`      | подтверждённый reveal tx                                   |
| `duel_settlements`  | одна terminal settlement на duel                           |
| `duel_chain_events` | идемпотентные события                                      |
| `duel_invitations`  | Telegram code, invite ID и bound accepted wallet           |

Один wallet может иметь только один активный offer. Matchmaking использует row lock и
`SKIP LOCKED`; reservation deadline повторно проверяется при funding.

Миграция `20260721_0004_split_bank_duel.py` архивирует старые универсальные cycle-таблицы как
`legacy_*`; эти строки нельзя интерпретировать как текущую финансовую историю.

## Рейтинг как read model

`rating.py` на каждый запрос:

1. строит UTC-окно текущего календарного месяца;
2. считает `BankPayout`, `DuelSettlement`, своевременные `DuelReveal`, misses и qualified
   referrals;
3. вычисляет score с нулевым floor и reliability;
4. загружает только затронутых users;
5. сортирует leaderboard и строит referral circle;
6. отдельно вычисляет live pulse.

Нет таблицы `scores`, фонового начисления или клиентских points.

## Конкурентность и идемпотентность

- Partial unique indexes заранее ограничивают активную BANK position и DUEL offer.
- Quote path блокирует invitation/counter rows и освобождает истёкшие reservations.
- Chain event identity: `(network, account, lt, tx_hash, event_index)`.
- Worker начинает с `checkpoint.last_lt - 1`, поэтому безопасно перечитывает границу.
- Каждый event применяется под nested savepoint; исключение не продвигает checkpoint.
- Неполные authoritative данные дают `RETRY` и блокируют продвижение данного контракта.
- Неуспешные или посторонние транзакции дают `IGNORED`.
- Permissionless on-chain entity без app user должна индексироваться безопасно.

## Failure model

| Сбой                             | Поведение                                                    |
| -------------------------------- | ------------------------------------------------------------ |
| Telegram SDK медленный           | bridge загружается асинхронно, есть URL fallback             |
| Toncenter недоступен             | intent остаётся pending, worker retry с backoff              |
| wallet callback без блока        | финансовый state не меняется                                 |
| malformed/failed tx              | событие не применяется                                       |
| masterchain finality отсутствует | checkpoint останавливается до повторной проверки             |
| projection exception             | savepoint rollback, повтор безопасен                         |
| worker restart                   | продолжение с durable checkpoint                             |
| stale BANK intent                | через 15 минут → `failed`                                    |
| stale DUEL funding               | после expiry → `expired`                                     |
| stale AFK reservation            | возвращается в `open`                                        |
| stale direct invitation          | invitation → `expired`; on-chain offer требует `ExpireOffer` |
| Redis недоступен при rate limit  | production mutation fail-closed с `503`                      |
| contract code hash mismatch      | API/worker production startup fail                           |

## Configuration

Все ключи описаны без значений в `.env.example`.

| Категория      | Примеры                                          |
| -------------- | ------------------------------------------------ |
| runtime        | app env, log level, database, Redis              |
| Telegram       | bot identity, webhook secret, auth age           |
| sessions       | user/control TTL, owner wallet, public origin    |
| TON            | network, provider URL/key, addresses/code hashes |
| BANK           | fee fallback, gas, principal limits              |
| DUEL           | fee fallback, signer pair, TTL, gas, pool limits |
| PLUSH          | mainnet Jetton master/provider/min balance       |
| monitoring     | metrics token, canary age/balance thresholds     |
| infrastructure | PostgreSQL, Redis, domain, ACME                  |
| web build      | API base, manifest URL, compile-time mock flag   |

Production validator требует HTTPS, сильные secrets, два адреса/хеша контрактов, owner wallet,
совпадающую Ed25519 key pair и network `-3`.

## Security boundaries

- CORS allowlist и exact Origin для API mutations.
- Production rate limit: auth `20/min`, остальные mutations `120/min`; nginx имеет дополнительный
  внешний rate limit.
- User sessions подписаны и ограничены TTL.
- Control cookie недоступна JavaScript и не отправляется вне control API path.
- TON Connect telemetry выключена; CSP содержит release-pinned allowlist wallet bridges.
- Контейнеры API/worker read-only, без capabilities и с `no-new-privileges`.
- API docs отключены в production.
- Логи не должны содержать secrets, initData, proofs или персональные платёжные данные.
