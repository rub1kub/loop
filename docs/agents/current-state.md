# Текущее состояние LOOP

Это проверяемый снимок, а не бессрочная гарантия. Он отделяет фактическое состояние production и
TON от намерений, примеров и будущего mainnet-релиза.

## Метаданные снимка

| Поле                    | Значение                                   |
| ----------------------- | ------------------------------------------ |
| Проверено               | 2026-07-26 16:32 UTC                       |
| Активный runtime commit | `fc9f786d4954ab538bf095c0518064ac5dc57516` |
| Активная ветка          | `main`                                     |
| Пользовательская сеть   | TON testnet, global ID `-3`                |
| Публичный домен         | <https://app.tonsuite.org>                 |
| Telegram                | [@getloopbot](https://t.me/getloopbot)     |
| Mainnet                 | не активирован                             |

Коммит этой документации может быть новее runtime-коммита: документационный выпуск в GitHub сам
по себе не меняет работающий сервер. Актуальную ревизию базы знаний определяй через историю Git
самих файлов `docs/agents/`.

## Production

На момент проверки:

- `/live` и `/ready` отвечают успешно;
- release и web release указывают на один commit `fc9f786…`;
- `api`, `worker`, `notifier`, `db` и `redis` имеют состояние `healthy`;
- бот отвечает как `@getloopbot`;
- inline mode и webhook включены;
- ожидающих Telegram updates и последней ошибки webhook нет;
- приложение развёрнуто прямым SSH-релизом, GitHub Actions не участвует.

Проверять повторно:

```bash
npm run deploy:vps:status
curl --fail https://app.tonsuite.org/live
curl --fail https://app.tonsuite.org/ready
```

## Контракты testnet

### BankQueue 1.3.0

| Поле             | Значение                                                           |
| ---------------- | ------------------------------------------------------------------ |
| Address          | `kQCqjhisqfxDrsPOEMWFE6AI1OWBtIQy_VVfXZU25zD50Il3`                 |
| Code hash        | `BA0A33E5D7A39358732E89720981EA421374A453AAF5B44C552569C5C71FB3E2` |
| Live balance     | `1.417633799 GRAM`                                                 |
| Locked funding   | `0.73 GRAM`                                                        |
| Retained reserve | `0.2 GRAM`                                                         |
| Completed        | `1` position                                                       |
| Current limit    | `5 GRAM`                                                           |
| Reserve covered  | да                                                                 |

Двухкошельковый цикл подтвердил два входа по `1 GRAM`, две комиссии по `0.01 GRAM` и выплату
`1.25 GRAM` первой позиции. Вторая позиция закономерно осталась с наполнением `0.73 GRAM`.
Поэтому текущий testnet BANK **не пуст**: эта сумма является пользовательским обязательством и
не считается свободным остатком.

Полные transaction hashes, LT, masterchain blocks и message values находятся в
[`deployments/testnet/bank.json`](../../deployments/testnet/bank.json).

### DuelEscrow 1.3.0

| Поле             | Значение                                                           |
| ---------------- | ------------------------------------------------------------------ |
| Address          | `kQD7JaRbyRrkGFzk9Xk3rfpRqNBSAUF2T-kXxfDlXYw4lg3M`                 |
| Code hash        | `5BDAED2F56EF9F51B33F0B388EF7B31DDE843961D23876A16243BA06D53C17FB` |
| Live balance     | `2.011894980 GRAM`                                                 |
| Locked value     | `0 GRAM`                                                           |
| Retained reserve | `0.2 GRAM`                                                         |
| Active offers    | нет подтверждённых обязательств                                    |
| Active duels     | нет подтверждённых обязательств                                    |
| Reserve covered  | да                                                                 |

Доказаны open → cancel → refund и двухкошельковая цепочка direct match → boost `0.1 GRAM` →
deadline → reveal → settlement. Полные доказательства находятся в
[`deployments/testnet/duel.json`](../../deployments/testnet/duel.json).

Повторная read-only проверка:

```bash
.venv/bin/python scripts/verify-contracts.py --network testnet --require-smoke
```

Она сверяет локальную сборку, live code hash, initial data, getters, резерв, входящие сообщения,
комиссии, payout/refund и masterchain finality.

## Проверочная база

Последний полный технический прогон:

| Проверка                        | Результат                                |
| ------------------------------- | ---------------------------------------- |
| Контрактные тесты               | `72/72`: BANK `19`, DUEL `53`            |
| Покрытие контрактов             | строки `99.67%`, ветви `87.45%`          |
| BANK mutation critical / major  | пороги `90%` / `75%` пройдены            |
| DUEL mutation critical          | `99.2%` (порог `95%`)                    |
| API pytest                      | `106`                                    |
| Web Vitest                      | `63` в `14` файлах                       |
| Playwright stress/E2E           | `6` сценариев, включая keyboard/viewport |
| Alembic                         | `0001 → 0010`, новых операций нет        |
| Ruff / mypy / ESLint / TS build | успешно                                  |
| npm audit                       | `0` известных уязвимостей                |
| Python dependency audit         | известных уязвимостей не найдено         |

Автоматические проверки уменьшают известный риск, но не доказывают отсутствие всех
уязвимостей.

## Mainnet: что готово

- frontend и backend понимают network IDs `-3` и `-239`;
- production config требует явный `LOOP_MAINNET_ENABLED=true`;
- runtime commit обязан совпадать с externally audited commit;
- обязателен SHA-256 реального отчёта независимого аудитора;
- CORS в production допускает только canonical public origin;
- mainnet provider не может указывать на testnet;
- application limits обязаны совпасть с audited release evidence;
- production BANK должен быть paused и иметь пустую очередь;
- production DUEL должен быть paused и не иметь locked value;
- BANK payout smoke выполняется только на отдельном shadow-контракте с тем же bytecode;
- DUEL требует финализированный canary двух разных mainnet-кошельков;
- source verification URLs и live code hashes обязательны;
- переключение сети блокируется при незавершённых обязательствах старой сети;
- аудитный ZIP строится детерминированно и не включает secrets.

## Mainnet: что отсутствует

| Gate                                    | Состояние             |
| --------------------------------------- | --------------------- |
| Независимый профессиональный аудит      | отсутствует           |
| Отчёт под `docs/audits/`                | отсутствует           |
| `deployments/mainnet/release.json`      | намеренно отсутствует |
| Production BANK/DUEL mainnet manifests  | отсутствуют           |
| Mainnet source verification             | отсутствует           |
| BANK shadow finalized payout evidence   | отсутствует           |
| DUEL mainnet two-wallet canary evidence | отсутствует           |
| Production runtime network `-239`       | выключен              |

Поэтому LOOP готов к передаче аудитору, но **не готов к приёму реальных средств**. Текущий
`make contracts-mainnet-preflight` корректно завершается ошибкой на отсутствующем
`deployments/mainnet/release.json`.

## Актуальные ограничения и долги

1. BANK зависит от новых взносов и не имеет cancel/early refund после подтверждения.
2. Текущая testnet BANK-позиция с `0.73 GRAM` должна оставаться защищённым обязательством.
3. PLUSH BRICK fee-free — утверждённая mainnet-модель. DuelEscrow v1.4 (holder-permit)
   реализован в репозитории: контракт, backend, frontend и тесты готовы, но **testnet
   deployment остаётся v1.3**, поэтому `LOOP_DUEL_HOLDER_FEE_ENABLED` выключен и профиль
   возвращает `fee_discount_active=false`. До v1.4 broadcast `make contracts-verify` ожидаемо
   сообщает hash mismatch для DUEL: локальная сборка новее манифеста. Buyback — ручное
   намерение без публичного журнала.
4. `ReferralReward` начисляет `100`, а месячный рейтинг даёт `25` за квалифицированного друга.
   Это две разные проекции; интерфейс профиля показывает число подтвердивших друзей и больше не
   называет обе метрики «очками», но сами счётчики всё ещё не объединены продуктовым решением.
5. Direct-invite signer immutable в текущем DuelEscrow; ротация требует нового deployment.
6. Обычный браузер получает лендинг, а не пользовательскую browser-версию игры.
7. Независимого security/contract audit пока нет; нельзя утверждать, что закрыты все возможные
   уязвимости.

Закрыто 2026-07-26 (проверять на текущем commit, не на этом снимке):

- referral qualification выполняется после подтверждённой BANK payout, а не только после DUEL
  settlement;
- no-reveal `ExpireDuel` переводит `Duel.state` в `refunded`, поэтому мониторинг больше не
  показывает вечный overdue duel; settlement-строка при возврате намеренно не создаётся;
- публичный `X-Content-Type-Options` снова имеет значение `nosniff`; значения заголовков
  проверяются тестом.

Перед работой с любым пунктом сначала воспроизведи его на текущем commit: список долгов — тоже
снимок.
