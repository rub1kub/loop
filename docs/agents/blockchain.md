# TON и смарт-контракты

## Граница TON

LOOP работает только с TON testnet, global ID `-3`. Пользователь подписывает действия внешним
кошельком через TON Connect. Backend не имеет пользовательских ключей и не может подписать
финансовую транзакцию вместо пользователя.

`1 GRAM = 1_000_000_000 nanoGRAM`. Все расчёты контрактов целочисленные; `mulDivFloor`
округляет вниз.

## Активные deployments

| Контракт   | Version | Address                                            | Code hash                                                          | Fee  |
| ---------- | ------- | -------------------------------------------------- | ------------------------------------------------------------------ | ---- |
| BankQueue  | 1.2.0   | `kQAQRNh3sG80ykjME39tnWnfswnjCDcRtrrCDOQP4jv4FL_y` | `9BF8EF5B9E75DF597E1EE4F4FE0DE2816D6B38899F4408E6A72857E0BD4A57C2` | 1%   |
| DuelEscrow | 1.2.0   | `kQAiTNwDqQf0NB4iTWJCDjjm-12d6RH94lc4aJXFoWXv-t9d` | `3347D324C4EE67C23A29E5CFC70C817CB0863DBFC0C7B09F779E4CB889083ACE` | 2.5% |

Explorer:

- [BankQueue](https://testnet.tonviewer.com/kQAQRNh3sG80ykjME39tnWnfswnjCDcRtrrCDOQP4jv4FL_y)
- [DuelEscrow](https://testnet.tonviewer.com/kQAiTNwDqQf0NB4iTWJCDjjm-12d6RH94lc4aJXFoWXv-t9d)

Owner и treasury обоих deployments — публичный адрес
`kQC820tGBtPVavhCbFZHnFavQObnCLitBKlGaEZ6-eyQTIY6`.

Полные deployment transaction, LT, initial data hash, toolchain и getters находятся в:

- `deployments/testnet/bank.json`;
- `deployments/testnet/duel.json`.

Manifest доказывает развёртывание и начальную конфигурацию. Он не является live state для
`locked`, balance, paused, fee, owner или treasury.

## BankQueue 1.2.0

### Константы

| Параметр                | Значение                      |
| ----------------------- | ----------------------------- |
| principal               | `1–100 GRAM`                  |
| multiplier              | `12500`, `15000`, `20000` bps |
| максимальная fee        | `1000 bps`                    |
| текущая fee             | `100 bps`                     |
| create gas buffer       | `0.08 GRAM`                   |
| admin minimum gas       | `0.02 GRAM`                   |
| withdraw gas buffer     | `0.05 GRAM`                   |
| retained reserve        | `0.2 GRAM`                    |
| max allocation steps/tx | `81`                          |

### Формулы

```text
target payout = floor(principal × multiplier_bps / 10_000)
fee           = floor(principal × fee_bps / 10_000)
distributable = principal − fee
```

`in.value` должен быть не меньше `principal + 0.08 GRAM`. Газ не входит в principal и target.

### Алгоритм

`allocateDeposit` проходит queue от `headQueueIndex`:

1. выделяет старой position `min(available, target - funded)`;
2. увеличивает `lockedFunding`;
3. при полном target удаляет position из active map и queue, уменьшает `lockedFunding` на target
   и отправляет `BankPayout`;
4. продолжает до конца available или queue;
5. нераспределённый остаток становится `fundedAmount` новой position;
6. новая position всегда добавляется в tail.

Contract не имеет cancel/early-refund сообщения для подтверждённой position.

### Storage

- owner, treasury, feeBps, paused;
- headQueueIndex, nextQueueIndex, lockedFunding;
- positions: position ID → owner/principal/multiplier/target/funded/index/timestamps/status;
- queue: queue index → position ID;
- activePositions: owner address → position ID;
- usedPositionIds: replay protection.

Один owner address не может иметь две активные позиции. Position ID никогда не используется
повторно.

### Сообщения

| Opcode       | Message               | Кто вызывает         |
| ------------ | --------------------- | -------------------- |
| `0x4C424E01` | `CreatePosition`      | пользователь         |
| `0x4C424E02` | `SetBankPaused`       | owner                |
| `0x4C424E03` | `BankFundReserve`     | owner                |
| `0x4C424E04` | `BankWithdrawSurplus` | owner, только paused |
| `0x4C424E05` | `BankSetFee`          | owner, только paused |
| `0x4C424E06` | `BankSetTreasury`     | owner, только paused |
| `0x4C424E07` | `BankSetOwner`        | owner, только paused |
| `0x4C424E11` | `BankPayout`          | исходящее событие    |
| `0x4C424E12` | `BankProtocolFee`     | исходящее событие    |
| `0x4C424E13` | `BankAdminWithdrawal` | исходящее событие    |

Getters: `contractConfig`, `queueData`, `positionData`, `activePosition`, `adminState`.

### Owner controls

- Pause блокирует только новые positions.
- `FundReserve` оставляет declared amount на контракте.
- Withdrawal разрешён только paused и только в treasury.
- Верхняя граница:
  `balance_before_call − lockedFunding − 0.2 GRAM`.
- Fee не выше `10%`.
- Treasury не может быть адресом самого контракта.
- Новый owner должен отличаться от текущего и контракта.

## DuelEscrow 1.2.0

### Константы

| Параметр                 | Значение                        |
| ------------------------ | ------------------------------- |
| total pool               | `1–100 GRAM`, кратен 4 nanoGRAM |
| supported chances        | `2500`, `5000`, `7500` bps      |
| новый продукт            | только `5000 + 5000`            |
| текущая fee              | `250 bps`                       |
| open gas buffer          | `0.05 GRAM`                     |
| action/admin minimum gas | `0.02 GRAM`                     |
| withdraw gas buffer      | `0.05 GRAM`                     |
| offer expiry             | 30–3600 секунд от chain time    |
| reveal window            | 300 секунд                      |
| retained reserve         | `0.2 GRAM`                      |

Contract сохраняет weighted `25/75` и `75/25` для recovery старых offers. API запрещает создавать
новые неравные AFK/direct offers.

### Stakes и payout

```text
stake A = floor(total_pool × chance_A / 10_000)
stake B = total_pool − stake A
fee     = floor(total_pool × fee_bps / 10_000)
payout  = total_pool − fee
```

Для нового `50/50` оба вносят ровно половину pool.

### Domain separation

Commitment:

```text
hash(COMMITMENT_DOMAIN, network_id, contract_address, offer_id, owner, secret)
```

Outcome при двух reveals:

```text
hash(OUTCOME_DOMAIN, network_id, contract_address, duel_id,
     offer_A_id, secret_A, offer_B_id, secret_B)
```

Direct permit:

```text
hash(DIRECT_ACCEPT_DOMAIN, network_id, contract_address,
     invite_id, creator_offer_id, invited_address, valid_until)
```

Такой commitment/permit нельзя перенести на другую сеть, deployment, offer или wallet.

### Match и winner

- Offers должны быть open, не просрочены, иметь одинаковый total pool и complementary chances.
- Owners должны различаться.
- AFK match разрешён только между двумя offers без direct metadata.
- Direct match требует взаимно связанных opponent addresses.
- Duel ID равен большему из двух offer IDs; canonical order — по ID.
- При двух reveals `outcome % total_pool < stake_A` выбирает A, иначе B.
- При одном reveal после deadline выигрывает единственный revealer.
- При нуле reveals оба stakes возвращаются.

### Storage

- owner, treasury, feeBps, networkId, inviteSignerPublicKey, paused, locked;
- offers: offer ID → owner/commitment/chance/pool/stake/expiry/state/direct;
- duels: duel ID → two offer IDs/deadline/secrets/revealedMask;
- activeOffers: owner address → offer ID;
- usedOfferIds: replay protection.

Contract удаляет terminal offers/duel из active maps и уменьшает `locked` перед отправкой payout
или refund.

### Сообщения

| Opcode       | Message               | Назначение                        |
| ------------ | --------------------- | --------------------------------- |
| `0x4C4F4F01` | `OpenOffer`           | AFK/legacy offer                  |
| `0x4C4F4F02` | `CancelOffer`         | owner refund до match             |
| `0x4C4F4F03` | `MatchOffers`         | permissionless AFK match          |
| `0x4C4F4F04` | `Reveal`              | раскрытие секрета                 |
| `0x4C4F4F05` | `ExpireOffer`         | permissionless unmatched refund   |
| `0x4C4F4F06` | `ExpireDuel`          | deadline settlement/refund        |
| `0x4C4F4F07` | `SetPaused`           | owner pause                       |
| `0x4C4F4F08` | `OpenDirectOffer`     | creator direct invite             |
| `0x4C4F4F09` | `AcceptDirectOffer`   | address-bound atomic accept/match |
| `0x4C4F4F0A` | `DuelFundReserve`     | owner reserve                     |
| `0x4C4F4F0B` | `DuelWithdrawSurplus` | owner surplus withdrawal          |
| `0x4C4F4F0C` | `DuelSetFee`          | owner fee                         |
| `0x4C4F4F0D` | `DuelSetTreasury`     | owner treasury                    |
| `0x4C4F4F0E` | `DuelSetOwner`        | ownership transfer                |
| `0x4C4F4F11` | `DuelPayout`          | исходящее winner event            |
| `0x4C4F4F12` | `OfferRefund`         | исходящее refund event            |
| `0x4C4F4F13` | `ProtocolFee`         | исходящее fee event               |
| `0x4C4F4F14` | `DuelAdminWithdrawal` | исходящее admin withdrawal        |

Getters: `contractConfig`, `offerData`, `duelData`, `directOfferData`, `activeOffer`,
`adminState`.

### Owner controls

- Pause не блокирует cancel/reveal/expire/recovery.
- Withdrawal только paused, только в treasury и не выше
  `balance_before_call − locked − 0.2 GRAM`.
- Fee change только paused и только при `locked=0`.
- Fee не выше `10%`.
- Treasury/owner изменения требуют paused.
- Invite signer immutable в текущем bytecode; его ротация требует нового deployment.

## Chain worker как доказательная граница

Worker принимает transaction только если:

- account — текущий configured contract;
- transaction не emulated, не aborted;
- compute success true, exit code `0`, action success не false;
- `mc_block_seqno > 0`;
- входящий body декодируется в известный opcode;
- sender, value, query/entity IDs, terms и contract address согласованы;
- ожидаемые outgoing payout/refund/fee имеют точный destination и value.

BANK worker заново проигрывает FIFO allocation и не завершает event, пока outgoing payout не
совпадёт. DUEL worker перепроверяет direct permit, match, reveal owner и terminal payout/refund.

## Проверка deployment

Безопасные read-only команды:

```bash
make contracts-build
make contracts-inspect
```

Полный verifier:

```bash
make contracts-verify
```

`scripts/verify-contracts.py` проверяет local build hash, active account, code hash, deployment
transaction, initial data hash, masterchain inclusion и getters. Smoke-проверка выполняется
только если manifest содержит `verified_smoke`.

Текущие v1.2 manifests не содержат `verified_smoke`, поэтому verifier сейчас не доказывает
отдельную smoke-транзакцию. Кроме того, он сравнивает живой mutable `locked` с начальным нулём в
manifest. При активном offer это даёт ложный failure.

## Снимок сети 2026-07-24 06:32 UTC

`make contracts-inspect` показал:

- BankQueue active, code hash совпадает, balance `0.499907732 GRAM`, `lockedFunding=0`, queue
  пуста.
- DuelEscrow active, code hash совпадает, balance `7.325824626 GRAM`, `locked=0.5 GRAM`.
- В DUEL был один direct offer `8500169712360770`, expiry
  `2026-07-24T01:33:00Z`, без opponent и duel.
- `make contracts-verify` завершился ошибкой `DuelEscrow: locked balance mismatch` только из-за
  сравнения с manifest `locked_nano=0`.

Этот offer уже был просрочен на момент снимка. Перед recovery:

1. повторно вызови `make contracts-inspect`;
2. убедись, что offer всё ещё open и duel отсутствует;
3. используй permissionless `ExpireOffer`, а не owner withdrawal;
4. проверь refund и `locked=0` в masterchain-finalized транзакции;
5. не раскрывай и не экспортируй signing key в логи.

## Предыдущие контракты

- Previous BANK:
  `kQC1zcM8cxIDn3mFR0RV_PS_y2PzNkFttJ8NfAPHTyHrmc4l`, paused, recorded
  `locked=0.99 GRAM`, owner-only position `2207202601`.
- Previous DUEL:
  `kQDVeChmpyLsgjLZRLW-gtwSS4s5depJWpBhuYkfhgYdu3Tw`, paused, recorded `locked=0`.

Старый BANK locked value нельзя выводить как surplus; это обязательство position. Старые адреса
не должны снова принимать новые пользовательские действия.

## DUEL canary

Canary использует две заранее созданные изолированные low-value testnet Acton aliases:

1. fork rehearsal;
2. direct open;
3. address-bound accept;
4. оба reveals;
5. settlement;
6. серверная повторная проверка transaction и payout;
7. запись только подтверждённого результата в Redis metrics.

Canary не создаёт кошельки автоматически, не использует user wallets и не запускается в CI.
Testnet faucet запрашивается только ниже заданного balance floor. Private material остаётся в
защищённом Acton store.

## Изменение контракта

1. Определи, можно ли выполнить задачу существующим owner message без изменения поведения.
2. Если меняется финансовое правило, signer или storage — нужен новый контракт/address.
3. Измени Tolk и Acton tests; проверь value conservation, replay, race, timeout и permissions.
4. Выполни emulation/fork smoke.
5. Перед DUEL switch докажи старый `locked=0` и отсутствие active DB projection.
6. Разворачивай только с явным broadcast gate.
7. Зафиксируй новый manifest, адрес, code/data hash, deployment proof и smoke evidence.
8. Обнови production environment через staged atomic release.
9. Запусти read-only verification, API/worker attestation и live canary.
10. Mainnet не разворачивать без независимого аудита, governance, legal и recovery gates.
