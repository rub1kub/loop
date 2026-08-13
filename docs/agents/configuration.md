# Конфигурация

Канонические источники:

1. `apps/api/app/config.py` — backend defaults и production validation;
2. `.env.example` — безопасный публичный шаблон;
3. `compose.yaml` — контейнерные переменные и ограничения;
4. `deployments/<network>/*.json` — публичные contract addresses и hashes;
5. защищённый `/opt/loop/shared/.env.production` — фактические production secrets, не Git.

Ни один документ не должен содержать реальные secret values.

## Runtime и данные

| Переменная                | Назначение                             | Production   |
| ------------------------- | -------------------------------------- | ------------ |
| `LOOP_APP_ENV`            | `development`, `test` или `production` | `production` |
| `LOOP_APP_NAME`           | имя приложения                         | optional     |
| `LOOP_LOG_LEVEL`          | уровень структурированных логов        | optional     |
| `LOOP_DATABASE_URL`       | async SQLAlchemy URL PostgreSQL        | secret       |
| `LOOP_REDIS_URL`          | Redis URL с паролем                    | secret       |
| `LOOP_AUTO_CREATE_SCHEMA` | dev-only создание схемы без Alembic    | `false`      |

Production использует только Alembic. `AUTO_CREATE_SCHEMA` не заменяет миграции.

## Telegram и пользовательская сессия

| Переменная                           | Назначение                             |
| ------------------------------------ | -------------------------------------- |
| `LOOP_BOT_TOKEN`                     | Bot API credential                     |
| `LOOP_BOT_USERNAME`                  | ожидаемое имя бота без `@`             |
| `LOOP_PUBLIC_FEED_CHAT_ID`           | чат rich-событий; `0` отключает        |
| `LOOP_SUPPORT_URL`                   | ссылка команды `/support`              |
| `LOOP_TELEGRAM_WEBHOOK_SECRET`       | secret-token header webhook            |
| `LOOP_TELEGRAM_AUTH_MAX_AGE_SECONDS` | допустимый возраст `initData`          |
| `LOOP_TELEGRAM_FUTURE_SKEW_SECONDS`  | допустимое расхождение часов           |
| `LOOP_SESSION_SECRET`                | подпись bearer session                 |
| `LOOP_SESSION_TTL_SECONDS`           | срок пользовательской session          |
| `LOOP_PUBLIC_ORIGIN`                 | canonical HTTPS origin                 |
| `LOOP_CORS_ORIGINS`                  | allowlist Origin                       |
| `LOOP_WEBHOOK_PATH`                  | непредсказуемый internal Telegram path |
| `LOOP_RESULT_EFFECT_ID`              | необязательный эффект результата       |
| `LOOP_MATCH_EFFECT_ID`               | необязательный эффект найденной пары   |
| `LOOP_REFERRAL_EFFECT_ID`            | необязательный эффект приглашения      |

В production `PUBLIC_ORIGIN` обязан быть HTTPS, а `CORS_ORIGINS` — содержать ровно этот origin.
Webhook, session и metrics secrets должны иметь не меньше 32 символов.

## Панель владельца

| Переменная                         | Назначение                                 |
| ---------------------------------- | ------------------------------------------ |
| `LOOP_CONTROL_ADMIN_WALLET`        | единственный wallet, допускаемый в control |
| `LOOP_CONTROL_SESSION_TTL_SECONDS` | срок `HttpOnly` control cookie             |

Control login доказывает владение адресом, но admin transaction всё равно подписывает внешний
owner wallet. Совпадение control wallet и live contract owner проверяется перед подготовкой
сообщения.

## TON и mainnet gate

| Переменная                         | Назначение                                     |
| ---------------------------------- | ---------------------------------------------- |
| `LOOP_TON_NETWORK_ID`              | `-3` testnet или `-239` mainnet                |
| `LOOP_TONCENTER_URL`               | provider выбранной пользовательской сети       |
| `LOOP_TONCENTER_API_KEY`           | provider credential                            |
| `LOOP_TON_PROOF_TTL_SECONDS`       | срок TON proof challenge                       |
| `LOOP_MAINNET_ENABLED`             | отдельное разрешение транзакций mainnet        |
| `LOOP_MAINNET_RELEASE_COMMIT`      | фактический release commit                     |
| `LOOP_MAINNET_AUDITED_COMMIT`      | reviewed commit из release evidence            |
| `LOOP_MAINNET_AUDIT_REPORT_SHA256` | fingerprint закреплённого evidence/disclosure  |
| `LOOP_REQUIRE_DUEL_CANARY`         | обязательность свежего двухкошелькового canary |
| `LOOP_ALLOW_MAINNET_CANARY`        | операторское разрешение live mainnet canary    |

Mainnet включается только если оба commit равны, report SHA-256 валиден, provider не testnet,
canary обязателен и остальные production validators проходят. Имена переменных исторические:
активный release использует `self_reviewed` evidence, а не независимый внешний аудит.

## BANK

| Переменная                     | Назначение                                 |
| ------------------------------ | ------------------------------------------ |
| `LOOP_BANK_CONTRACT_ADDRESS`   | текущий BankQueue                          |
| `LOOP_BANK_CONTRACT_CODE_HASH` | ожидаемый 32-byte code hash                |
| `LOOP_BANK_FEE_BPS`            | fallback до live control projection        |
| `LOOP_BANK_POSITION_GAS_NANO`  | клиентский gas buffer                      |
| `LOOP_BANK_MIN_PRINCIPAL_NANO` | application lower bound                    |
| `LOOP_BANK_MAX_PRINCIPAL_NANO` | application cap, не выше live contract cap |
| `LOOP_BANK_DOUBLE_LIMIT_NANO`  | application cap для цели ×2                |
| `LOOP_BANK_DEBUG_TELEGRAM_IDS` | Telegram ID для response-only preview      |
| `LOOP_BANK_DEBUG_PROGRESS_BPS` | минимальный показываемый прогресс, bps     |

В testnet шаблон ограничивает BANK `5 GRAM`. Mainnet validator допускает абсолютный initial cap
не выше `10 GRAM`, а audit scope и release example рекомендуют `5 GRAM`. Post-deploy gate требует
точного совпадения application cap с audited `release.json`.
Debug progress меняет только API-представление активной позиции, не БД и не расчёты контракта;
он должен быть привязан к конкретным Telegram ID операторов и не влияет на readiness gates.

### BANK Wave

| Переменная                            | Назначение                                   |
| ------------------------------------- | -------------------------------------------- |
| `LOOP_BANK_WAVE_ENABLED`              | включает расчёт и уведомления Волны          |
| `LOOP_BANK_WAVE_WALLET`               | внешний адрес операторской позиции           |
| `LOOP_BANK_WAVE_WEEKDAY`              | день недели, `6` = воскресенье               |
| `LOOP_BANK_WAVE_HOUR_MOSCOW`          | час старта по Москве                         |
| `LOOP_BANK_WAVE_DURATION_MINUTES`     | длительность окна                            |
| `LOOP_BANK_WAVE_GOAL`                 | число разных подтверждённых участников       |
| `LOOP_BANK_WAVE_BOOST_NANO`           | размер позиции после достижения цели         |
| `LOOP_BANK_WAVE_CAMPAIGN_STARTS_AT`   | начало кампании                              |
| `LOOP_BANK_WAVE_MAX_BOOSTS`           | максимальное число операторских позиций      |
| `LOOP_BANK_WAVE_OPERATOR_TELEGRAM_ID` | пользователь `/control`, который подписывает |

Сервер не хранит ключ Wave-кошелька и не отправляет позицию сам. Он считает только
финализированные входы, готовит payload и ждёт внешней подписи через `/control`.

## DUEL

| Переменная                       | Назначение                                       |
| -------------------------------- | ------------------------------------------------ |
| `LOOP_DUEL_CONTRACT_ADDRESS`     | текущий DuelEscrow                               |
| `LOOP_DUEL_CONTRACT_CODE_HASH`   | ожидаемый 32-byte code hash                      |
| `LOOP_DUEL_FEE_BPS`              | fallback до live control projection              |
| `LOOP_DUEL_INVITE_SIGNING_KEY`   | private Ed25519 seed для address-bound permits   |
| `LOOP_DUEL_INVITE_PUBLIC_KEY`    | публичная половина, должна совпасть с seed       |
| `LOOP_DUEL_HOLDER_FEE_ENABLED`   | выдача holder-permit; только с v1.4 bytecode     |
| `LOOP_OFFER_TTL_SECONDS`         | срок нового offer                                |
| `LOOP_REVEAL_TTL_SECONDS`        | зеркало reveal window                            |
| `LOOP_OFFER_GAS_NANO`            | open-offer gas buffer                            |
| `LOOP_MIN_POOL_NANO`             | application lower bound                          |
| `LOOP_MAX_POOL_NANO`             | application cap                                  |
| `LOOP_FEE_BPS`                   | legacy fallback на время миграции                |
| `LOOP_TON_CONTRACT_ADDRESS/HASH` | legacy DUEL aliases, не использовать в новом env |

В testnet шаблон ограничивает новый pool `2 GRAM`. Mainnet validator имеет жёсткий ceiling
`10 GRAM`; release example фиксирует консервативный `2 GRAM`.

## DUEL canary и monitoring

| Переменная                            | Назначение                              |
| ------------------------------------- | --------------------------------------- |
| `LOOP_METRICS_TOKEN`                  | bearer для `/metrics` и internal canary |
| `LOOP_DUEL_CANARY_MAX_AGE_SECONDS`    | максимально допустимый возраст canary   |
| `LOOP_DUEL_CANARY_MIN_BALANCE_NANO`   | floor для запуска                       |
| `LOOP_DUEL_CANARY_ALERT_BALANCE_NANO` | alert threshold                         |

Canary aliases хранятся в защищённом Acton store и не описываются mnemonic в environment.
Для mainnet этот store находится только на защищённой машине оператора: VPS не получает ключи и
не запускает `loop-duel-canary.timer`. VPS принимает доказательство завершённой транзакции через
internal API, а `loop-duel-monitor.timer` следит за его возрастом и балансами. Текущее рабочее окно
mainnet — `2678400` секунд (31 день); новый canary запускается вручную до истечения окна и после
изменения DUEL-контракта, signer domain или сетевой конфигурации.

## PLUSH BRICK

| Переменная                       | Назначение                                      |
| -------------------------------- | ----------------------------------------------- |
| `LOOP_PLUSH_BRICK_MASTER`        | Jetton master                                   |
| `LOOP_PLUSH_BRICK_NETWORK_ID`    | отдельная сеть проверки, сейчас mainnet `-239`  |
| `LOOP_PLUSH_BRICK_TONCENTER_URL` | отдельный provider                              |
| `LOOP_HOLDER_MIN_BALANCE_NANO`   | порог статуса holder                            |
| `LOOP_PLUSH_BRICK_FEE_BPS`       | legacy/reserved поле; не источник live DUEL fee |

Проверка PLUSH выполняется в mainnet. API выдаёт address-bound holder permit только когда
`LOOP_DUEL_HOLDER_FEE_ENABLED=true`, а startup подтвердил поддержку этой схемы живым DUEL
bytecode. Без обеих проверок скидка закрыта.

## Рефералы, объявления и alerts

| Переменная                       | Назначение                                  |
| -------------------------------- | ------------------------------------------- |
| `LOOP_REFERRAL_MIN_PAYOUT_NANO`  | минимальная proof-backed заявка на выплату  |
| `LOOP_REFERRAL_SPECIAL_BPS`      | персональные ставки `telegram_id:bps,...`   |
| `LOOP_ANNOUNCEMENT_TEXT`         | текст временного объявления в Mini App      |
| `LOOP_ANNOUNCEMENT_URL`          | необязательное действие объявления          |
| `LOOP_ANNOUNCEMENT_TELEGRAM_IDS` | аудитория: список ID или явный `*`          |
| `LOOP_ANNOUNCEMENT_UNTIL`        | автоматический срок снятия объявления       |
| `LOOP_ALERT_CHAT_ID`             | чат инцидентов остановившегося chain worker |

Стандартная реферальная ставка задаётся кодом (`500` bps); overrides выигрывают у неё и влияют
только на будущие подтверждённые BANK-входы. Строки Telegram ID, audience и wallet mappings —
чувствительные операционные данные: значения хранятся только в защищённом environment и не
переносятся в документацию или логи.

## Web build

| Переменная                     | Назначение                                     |
| ------------------------------ | ---------------------------------------------- |
| `VITE_API_BASE_URL`            | API prefix, обычно `/api/v1`                   |
| `VITE_TONCONNECT_MANIFEST_URL` | canonical HTTPS manifest                       |
| `VITE_MOCK_TELEGRAM`           | compile-time dev/test mock, production `false` |

Mock не является runtime bypass: он встраивается при сборке и не умеет broadcast.

## Infrastructure

| Переменная          | Назначение                      |
| ------------------- | ------------------------------- |
| `POSTGRES_DB`       | имя базы                        |
| `POSTGRES_USER`     | роль базы                       |
| `POSTGRES_PASSWORD` | credential                      |
| `REDIS_PASSWORD`    | credential                      |
| `DOMAIN`            | canonical host                  |
| `ACME_EMAIL`        | контакт выпуска TLS-сертификата |

Compose публикует API только на `127.0.0.1:8000`; PostgreSQL и Redis доступны только backend
network. API, worker и notifier работают read-only, без Linux capabilities и с
`no-new-privileges`.

## Операторские переменные CLI

Они не являются обычными настройками приложения:

| Переменная                                     | Где используется                    |
| ---------------------------------------------- | ----------------------------------- |
| `LOOP_DEPLOY_HOST`                             | SSH host/alias, default `ton4-prod` |
| `LOOP_DEPLOY_BRANCH`                           | ожидаемая ветка, default `main`     |
| `ALLOW_TESTNET_DEPLOY=1`                       | явное разрешение contract broadcast |
| `ALLOW_MAINNET_DEPLOY=I_UNDERSTAND_REAL_FUNDS` | подтверждение реальных средств      |
| `LOOP_CONTRACT_OWNER_ADDRESS`                  | init owner нового deployment        |
| `LOOP_CONTRACT_TREASURY_ADDRESS`               | init treasury нового deployment     |
| `LOOP_ALLOW_TESTNET_CANARY=1`                  | явный BANK testnet broadcast        |
| `LOOP_ALLOW_MAINNET_CANARY=1`                  | явный mainnet canary broadcast      |
| `TONCENTER_TESTNET_API_KEY`                    | read-only verifier/canary provider  |
| `TONCENTER_MAINNET_API_KEY`                    | mainnet verifier/canary provider    |
| `LOOP_RELEASE_COMMIT`                          | release SHA внутри server preflight |
| `LOOP_DUEL_METRICS_ORIGIN`                     | локальный origin health checker     |

Mainnet и testnet gates намеренно различаются. Не ослабляй их универсальным `--force`.

## Правила изменения

1. Не добавляй secret в `.env.example`; оставляй пустое значение или безопасный placeholder.
2. Если параметр влияет на wire format или контракт, обновляй backend, frontend, tests и
   deployment manifest вместе.
3. Не полагайся на fallback fee после появления live `ContractControl`.
4. Изменение network/address/code hash требует preflight и полного runtime release.
5. Изменение DUEL signer требует нового deployment: текущий signer immutable on-chain.
6. Mainnet audit evidence нельзя генерировать фиктивно или заменять локальным тестом.
