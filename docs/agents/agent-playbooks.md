# Рабочие карты для агентов

## Карта репозитория

```text
.
├── apps/
│   ├── web/                 React Mini App, browser control, Vitest, Playwright
│   └── api/                 FastAPI, aiogram, SQLAlchemy, Alembic, pytest
├── contracts/
│   ├── bank/                BankQueue Tolk
│   └── duel/                DuelEscrow Tolk
├── deployments/testnet/     проверенные deployment manifests
├── tests/                   Acton contract tests
├── scripts/                 deploy/smoke/canary/verification/screenshots
├── deploy/                  Docker, release, nginx, Apache, systemd, alerts
├── docs/                    продукт, архитектура, runbooks, screenshots
├── wrappers/                Acton-generated contract wrappers
├── wrappers-ts/             TypeScript message schema
├── Acton.toml               contracts/toolchain/scripts
├── compose.yaml             production-like runtime
├── Makefile                 единый интерфейс команд
└── .env.example             только имена и безопасные defaults
```

Локальные `AGENTS.md` и `sources/` принадлежат ChatGPT project mirror и игнорируются Git.
`sources/` всегда read-only.

## Где менять конкретную вещь

| Требование                 | Основные файлы                                                    |
| -------------------------- | ----------------------------------------------------------------- |
| tab/navigation             | `components/TabBar.tsx`, `App.tsx`, `styles.css`, `types.ts`      |
| onboarding                 | `components/Onboarding.tsx`, store settings, onboarding tests     |
| BANK UI                    | `features/bank/BankScreen.tsx`, `styles.css`, component/E2E tests |
| DUEL UI                    | `features/duel/DuelScreen.tsx`, `ton.ts`, component/E2E tests     |
| rating UI                  | `features/rating/RatingScreen.tsx`, `rating.py`, tests            |
| profile/referrals          | `components/ProfileScreen.tsx`, `routes.py`, `models.py`          |
| keyboard/safe area         | `viewport.ts`, `styles.css`, `modes.stress.spec.ts`               |
| Telegram fullscreen/chrome | `telegram.ts`, `types.ts`, Telegram tests, `docs/telegram.md`     |
| Telegram auth              | `security.py`, `routes.py`, `nonce_store.py`, auth/security tests |
| bot `/start`/inline/menu   | `bot.py`, bot tests                                               |
| TON Connect proof          | `security.py`, `ton.py`, `routes.py`, `App.tsx`, `api.ts`         |
| BANK API/model             | `modules/bank/router.py`, `models.py`, schemas, worker            |
| DUEL API/matchmaking       | `modules/duel/router.py`, `models.py`, `math.py`, worker          |
| chain projection           | `chain_worker.py`, `ton.py`, worker tests                         |
| rating formula             | `rating.py`, `schemas.py`, `RatingScreen.tsx`, docs/rating        |
| owner control API          | `control_routes.py`, `control_state.py`, `models.py`, tests       |
| owner control UI           | `control/ControlApp.tsx`, `control/api.ts`, `control.css`, E2E    |
| DB schema                  | models + новая Alembic migration                                  |
| BankQueue rule             | `contracts/bank/*.tolk`, Acton BANK tests, wrappers/manifests     |
| DuelEscrow rule            | `contracts/duel/*.tolk`, Acton DUEL tests, wrappers/manifests     |
| contract verification      | `scripts/verify-contracts.py`, manifests, verification fixtures   |
| deploy/rollback            | `deploy/activate-release.sh`, backup, Compose, deployment docs    |
| CSP/headers/proxy          | `deploy/nginx/*`, `deploy/apache/loop.conf`                       |
| monitoring/canary          | `metrics.py`, canary runner, systemd units, alert rules           |
| screenshots                | mock states, `capture-screenshots.mjs`, `docs/screenshots`        |

Перед изменением call site проверь обе стороны wire contract: Pydantic schema/API и Zod/TypeScript
type.

## Стандартный рабочий цикл

1. Прочитать `docs/agents/README.md` и один профильный документ.
2. Проверить `git status`; существующие чужие изменения не перезаписывать.
3. Найти минимальные call sites через `rg`.
4. Сформулировать инвариант и ожидаемый failure mode.
5. Изменить первопричину, не дублировать финансовое правило в новой прослойке.
6. Добавить минимальный regression test на тот же уровень.
7. Запустить целевые проверки, затем ближайший build/type boundary.
8. Для UI проверить desktop, Android Chromium и iOS WebKit.
9. Для chain state использовать read-only getter/provider proof.
10. Обновить docs/KB, если изменился контракт между компонентами.
11. Commit в Conventional Commits; deploy только если задача явно включает публикацию.
12. После deploy проверить public health и фактический release SHA.

## Решения по слоям

### Если меняется только текст

- Не меняй смысл рисков BANK/DUEL.
- Проверь отсутствие wallet/casino/guarantee copy.
- Запусти Prettier и целевой UI test.
- Если текст видим, обнови screenshot только после визуальной проверки.

### Если меняется UI layout

- Сначала воспроизведи на точном viewport/platform.
- Не исправляй iOS keyboard глобальным scroll страницы.
- Проверь Telegram top controls, bottom safe area, tab bar и sheet одновременно.
- Протести минимум 320, 390, 430 px и desktop; WebKit обязателен.
- Проверь reduced motion и отсутствие горизонтального overflow.

### Если меняется API

- Определи, является endpoint read, intent или authoritative projection.
- Не принимай финансовый terminal state из клиента.
- Проверь Origin, bearer/control auth, bounds и rate limit.
- Обнови Pydantic, Zod/types и tests вместе.
- Для mutation избегай автоматического retry без idempotency key.

### Если меняется БД

- Создай новую migration; не редактируй применённую revision.
- Проверь clean install и upgrade path.
- Сохрани partial unique indexes и event identities.
- Contract address/network всегда часть финансовой identity.
- Не мигрируй `legacy_*` в текущий финансовый state догадкой.

### Если меняется worker

- Начни с failed, malformed, duplicate и non-final transaction tests.
- Не продвигай checkpoint через `RETRY`.
- Сравни исходящие destination/value/body.
- Сохрани отдельные BANK/DUEL события и savepoints.
- Permissionless on-chain entity без app user должна индексироваться безопасно.

### Если меняется контракт

- Используй Tolk + Acton, не backend emulation.
- Докажи value conservation, replay protection, bounded loops и recovery.
- Owner не должен выводить locked user value.
- Pause не должен выключать recovery.
- Новый behavior/signer/storage означает новый deployment и manifest.
- Live broadcast никогда не является неявным шагом теста.

### Если меняется control

- `/control` остаётся независимым от Telegram.
- UI только готовит transaction; owner wallet и contract — финальная authority.
- Сверяй live code hash, owner, paused, locked и withdrawable перед payload.
- Dangerous actions требуют paused и явного подтверждения.
- Не позволяй withdrawal за границу `locked + reserve`.

## Проверки по слоям

### Web

```bash
npm run lint:web
npm run test:web
npm run build:web
npm run format:check
```

### API

```bash
.venv/bin/ruff check apps/api
cd apps/api
../../.venv/bin/mypy app
../../.venv/bin/pytest tests -q
```

### Миграции

```bash
make test-integration
```

### Contracts

```bash
acton fmt --check
acton check
acton test --coverage --coverage-format text --coverage-minimum-percent 75
```

### UI E2E

```bash
npm --workspace @loop/web run e2e
npm --workspace @loop/web run e2e:webkit
npx playwright test --project=desktop-chromium
```

Запускай минимальный релевантный набор, но не называй результат production-ready без проверки
всех затронутых границ.

## Секреты и чувствительные данные

Агент обязан:

- не открывать `wallets.toml` без отдельной необходимости и разрешения;
- не печатать содержимое `.env`, service environment или GitHub secrets;
- не вставлять credentials из чата в command line, commit, docs или test fixtures;
- использовать placeholders в примерах;
- не создавать новый кошелёк, если задача явно этого не требует;
- не экспортировать mnemonic из Acton secure store;
- при secret scan выводить только безопасное резюме, а не найденное значение.

Public address/transaction/hash не является secret, но связь адреса с личностью может быть PII и
не должна без нужды попадать в виджет или лог.

## Generated и временные файлы

Не коммитить:

- `.env*`, кроме `.env.example`;
- `.venv`, `node_modules`, `.acton`;
- `build`, `gen`, `output`, coverage;
- `wallets.toml`, `libraries.toml`;
- `.boc`, `.fif`, runtime logs.

Wrappers обновляются штатной Acton-командой при изменении message/storage ABI; не правь generated
код вручную, если генератор доступен.

## Документация

| Изменился                    | Обновить                                                    |
| ---------------------------- | ----------------------------------------------------------- |
| продуктовый смысл/риск       | `product-and-ux.md`, `docs/product.md`, README              |
| API/table/flow               | `architecture-and-data.md`, профильный docs                 |
| contract/address/hash/opcode | `blockchain.md`, manifest, `docs/contracts.md`, env example |
| Telegram lifecycle/BotFather | `product-and-ux.md`, `docs/telegram.md`                     |
| tests/commands               | `operations.md`, `docs/testing.md`, Makefile                |
| release/monitoring           | `operations.md`, `docs/deployment.md`                       |
| operational snapshot         | дата и проверка; не выдавать snapshot за invariant          |

После правки проверь относительные Markdown links и `git diff --check`.

## Известные долги на снимке

1. GitHub Actions jobs заблокированы billing до выполнения шагов.
2. `contracts-verify` неверно сравнивает live mutable `locked` с начальным manifest value.
3. V1.2 manifests пока не содержат отдельные `verified_smoke` evidence.
4. В DUEL на снимке остался просроченный direct offer с `0.5 GRAM locked`; требуется повторная
   проверка и permissionless expiry.
5. UI DUEL сообщает предварительный минимум `0.25 GRAM`, а effective equal-stake minimum —
   `0.5 GRAM`.
6. Profile referral reward `100` и monthly rating referral score `25` имеют одинаковое
   пользовательское название.
7. Referral qualification вызывается только после DUEL settlement, не после BANK payout.
8. No-reveal `ExpireDuel` помечает offers как refunded, но worker сейчас не переводит
   соответствующий `Duel.state` из `revealing`; это может оставить ложный overdue projection.
9. Consumer browser identity отсутствует; пользовательское приложение по-прежнему требует
   Telegram.
10. Mainnet выключен, внешнего профессионального аудита нет.
11. PLUSH BRICK discount выключен.
12. Старый BANK имеет recorded owner-only position и не должен считаться свободным surplus.

Не исправляй эти пункты попутно в несвязанной задаче. Если задача касается пункта — сначала
повтори фактическую проверку.

## Definition of done

Задача завершена, когда:

- реализован согласованный пользовательский результат;
- соблюдены BANK/DUEL, auth и chain-proof инварианты;
- есть regression test для исправленного failure mode;
- минимальные релевантные проверки реально прошли;
- видимый UI проверен на нужных Telegram/browser режимах;
- migration/contract/deploy изменения имеют recovery path;
- документация не обещает больше, чем доказано;
- diff не содержит secrets, generated noise или чужих изменений;
- при публикации известны deployed SHA и результат public smoke.
