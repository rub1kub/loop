# Разработка, тестирование и эксплуатация

## Production topology

```text
Internet
  → Apache :80/:443 (TLS, canonical domain, legacy redirect)
  → nginx 127.0.0.1:18791 (static, CSP, rate limits, proxy)
  → FastAPI 127.0.0.1:8000
       ↘ PostgreSQL 17
       ↘ Redis 8
  → independent chain worker
```

Публичные поверхности:

- Mini App: <https://app.tonsuite.org>
- owner control: <https://app.tonsuite.org/control>
- health: <https://app.tonsuite.org/live>, <https://app.tonsuite.org/ready>
- Telegram: [@getloopbot](https://t.me/getloopbot)

Legacy sslip hostname на Apache только перенаправляет на canonical domain. Его нельзя использовать
в Telegram/BotFather/TON Connect configuration.

## Требования

- Node.js `22+`, npm с lockfile;
- Python `3.12+` (CI использует `3.13`);
- PostgreSQL `17`, Redis `8`;
- Docker + Compose;
- Acton `1.0.0`, Tolk `1.4.0`.

## Локальный запуск

```bash
cp .env.example .env
make setup
```

UI без Telegram и без транзакций:

```bash
VITE_MOCK_TELEGRAM=true make dev
```

API вручную:

```bash
.venv/bin/uvicorn app.main:app --app-dir apps/api --reload
```

Production-like stack требует заполненный `.env.production`:

```bash
make docker-up
make docker-down
```

Не копируй production secrets в локальный репозиторий. `.env*`, кроме `.env.example`, и
`wallets.toml` игнорируются Git.

## Конфигурация без секретов

`.env.example` — единственный шаблон. Значения production находятся только в защищённом
операторском environment.

Никогда не помещай в документацию, issue, PR, вывод теста или commit:

- bot token, webhook/session/metrics secrets;
- Toncenter API key;
- SSH password/private key;
- mnemonic/seed, wallet private key, Acton secure-store export;
- DUEL invite signing private seed;
- Telegram initData, TON proof signature или персональные адресные связи.

Публичные contract addresses, code hashes, transaction hashes и owner/treasury addresses допустимы.

## Матрица проверок

| Изменение                 | Минимальные проверки                                                                |
| ------------------------- | ----------------------------------------------------------------------------------- |
| Markdown/docs             | Prettier, links, `git diff --check`, secret scan                                    |
| React/component/copy      | `npm run lint:web`, целевой Vitest, `npm run build:web`                             |
| layout/keyboard/safe area | выше + Playwright desktop/mobile Chromium/mobile WebKit                             |
| API route/schema          | Ruff, mypy, целевые pytest, migration check при схеме                               |
| auth/security             | целевые security tests + `make test-security`                                       |
| DB model/migration        | clean `alembic upgrade head`, `alembic check`, PostgreSQL path                      |
| chain worker              | worker pytest, replay/idempotency/failed/finality cases                             |
| BANK contract             | Acton BANK tests, coverage, build, fork smoke, manifest verification                |
| DUEL contract             | Acton DUEL tests, coverage/mutation, two-wallet fork; live canary только оператором |
| deployment                | все затронутые suites, backup/rollback rehearsal, public smoke                      |

Основные команды:

```bash
make lint
make typecheck
make test-unit
make test-integration
make contracts-test
make test-e2e
make test-security
```

Read-only network:

```bash
make contracts-inspect
make contracts-verify
make chain-smoke-test
```

Смотри известное ограничение `contracts-verify` в
[blockchain.md](blockchain.md#проверка-deployment).

## Browser tests

Playwright имеет три проекта:

- `desktop-chromium`;
- `mobile-chromium` на Pixel 7;
- `mobile-webkit` на iPhone 13.

Набор покрывает onboarding, BANK wizard, DUEL, рейтинг, профиль, control, keyboard/navigation
transitions и safe area. Для видимого изменения обновляй production screenshots только после
реального сравнения:

```bash
make screenshots
```

## Contract tests

```bash
acton check
acton build
acton test --coverage --coverage-format text
```

Для критичного DUEL:

```bash
acton test tests/duel_contract.test.tolk --coverage --coverage-format text
acton test tests/duel_contract.test.tolk --mutate --mutate-contract DuelEscrow \
  --mutation-diff branch --mutation-levels critical,major
```

Не запускать live broadcast из обычного теста или CI.

## CI

`.github/workflows/ci.yml` запускает:

1. web lint/test/build/format + Chromium/WebKit E2E;
2. API Ruff/mypy/pytest с coverage `>=60%` + PostgreSQL migrations;
3. Acton build/check/test с coverage `>=75%` + live read-only verifier;
4. deploy-testnet только после трёх успешных jobs на push в `main`.

Actions и setup actions закреплены commit SHA, checkout не сохраняет credentials.

### Текущий CI blocker

Run `30042589425` для commit `3760e77` завершён красным до выполнения шагов:
GitHub сообщил, что jobs не запущены из-за billing lock аккаунта. Следовательно:

- красный badge сейчас не доказывает падение кода;
- автоматический deploy не выполняется;
- локальные проверки и manual immutable deployment не заменяют восстановленный CI навсегда.

Проверка:

```bash
gh run view 30042589425 --repo rub1kub/loop
```

## Release model

Каждый release — полное дерево конкретного 40-character Git SHA:

```text
/opt/loop/releases/<sha>
/opt/loop/shared/.env.production
/opt/loop/current -> /opt/loop/releases/<sha>
```

`deploy/activate-release.sh`:

1. берёт exclusive deploy lock;
2. валидирует release и built web entrypoint;
3. собирает immutable API image;
4. поднимает PostgreSQL/Redis;
5. останавливает writers;
6. при наличии staged env активирует его атомарно;
7. при DUEL address switch запускает migration preflight;
8. делает PostgreSQL backup;
9. запускает Alembic head;
10. поднимает API/worker и проверяет health;
11. атомарно переключает `/opt/loop/current`;
12. проверяет nginx и public smoke;
13. при ошибке возвращает env, DB dump и предыдущий release.

Релиз:

```bash
make deploy RELEASE=<40-character-git-sha>
make smoke-test
```

Обычный release не deploy-ит contracts. Contract broadcast имеет отдельный явный
`ALLOW_TESTNET_DEPLOY=1` gate.

## Health и monitoring

```bash
curl --fail https://app.tonsuite.org/live
curl --fail https://app.tonsuite.org/ready
```

`/ready` проверяет PostgreSQL и Redis. API и worker отдельно аттестуют code hashes при startup.

DUEL metrics:

- active/revealing offers;
- worker heartbeat и age;
- stale funding intents;
- overdue reveals;
- unbound direct matches;
- last verified two-wallet canary и age;
- minimum canary wallet balance.

Public nginx всегда скрывает `/metrics`; локальный scraper использует bearer token на
`127.0.0.1:8000`. Prometheus rules находятся в `deploy/monitoring/duel-alerts.yml`.
На хосте без Prometheus ту же fail-closed проверку запускает systemd timer через
`scripts/check-duel-health.py`.

## Telegram/BotFather

API startup идемпотентно синхронизирует:

- webhook URL и allowed updates;
- bot name/description/short description;
- `/start`;
- menu button `Открыть LOOP`.

Операции, доступные только вручную в BotFather:

- Main App launch mode: **Fullsize**;
- `/setinline` → placeholder `Брось вызов в LOOP`;
- `/setuserpic` → `docs/brand/loop-avatar.png`.

После изменения Telegram surface проверь:

- `/start` button открывает canonical domain;
- profile/menu button и attachment-side button проходят auth;
- inline query поддерживается `getMe.supports_inline_queries`;
- mobile становится fullscreen, desktop остаётся fullsize;
- Telegram header и bottom bar чёрные.

## Безопасная диагностика

### Репозиторий

```bash
git status --short
git branch --show-current
git rev-parse HEAD
git log -8 --oneline
```

### API и миграции

```bash
curl --fail https://app.tonsuite.org/ready
cd apps/api
../../.venv/bin/alembic heads
```

### Contracts

```bash
make contracts-build
make contracts-inspect
```

CLI diagnostics после локальной настройки:

```bash
.venv/bin/loop-onchain-audit contract --mode bank
.venv/bin/loop-onchain-audit contract --mode duel
.venv/bin/loop-onchain-audit wallet --address <address>
.venv/bin/loop-onchain-audit transaction --hash <hash> --account <address>
.venv/bin/loop-onchain-audit jetton --owner <address> --master <master>
```

### Не делать при диагностике

- не выводить `.env`, process environment или protected service unit environment;
- не читать/экспортировать `wallets.toml` или mnemonic;
- не менять live contract, BotFather, webhook или DB для «проверки»;
- не запускать deploy/canary/airdrop без необходимости и явного scope;
- не считать explorer UI или wallet callback единственным доказательством.

## Снимок production 2026-07-24

- Public `/live`: `{"status":"ok"}`.
- Public `/ready`: `{"status":"ready"}`.
- Последний операторски проверенный release symlink:
  `3760e7774a6575c1c9f97f2181fe2c29559e5637`.
- Локальный `main` и `origin/main` указывали на тот же commit.
- Последний функциональный change: упрощённая панель владельца `/control`.
- GitHub automated checks/deploy заблокированы billing до начала job steps.
- Живой TON-снимок содержит просроченный direct DUEL offer; см.
  [blockchain.md](blockchain.md#снимок-сети-2026-07-24-0632-utc).

Перед использованием этого снимка повтори public health, Git SHA, contract getters и CI status.

## Инцидентные подсказки

| Симптом                      | Первые проверки                                                  |
| ---------------------------- | ---------------------------------------------------------------- |
| «Authorization failed»       | launch URL, signed initData fallback, API origin, bot identity   |
| Mini App не грузится         | `/live`, `/ready`, JS assets, CSP, Telegram SDK, console         |
| mobile не fullscreen         | Telegram platform/version, BotFather Fullsize, fullscreen events |
| desktop fullscreen           | platform classification, `exitFullscreen`, повторный `expand`    |
| UI под Telegram chrome       | safeArea/contentSafeArea, protected 72 px fullscreen inset       |
| sheet уехал при клавиатуре   | visual viewport, focus state, root scroll, `.keyboard-open`      |
| tx pending >15 минут         | provider, contract account, tx success/finality, worker          |
| worker heartbeat stale       | worker container, provider, blocked transaction, checkpoint      |
| verifier locked mismatch     | live getter vs manifest initial value; не bytecode mismatch      |
| direct invite не принимается | invitation state/wallet binding/permit expiry/creator offer      |
| contract switch blocked      | old locked, active DB rows, Alembic preflight                    |
