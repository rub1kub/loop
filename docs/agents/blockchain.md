# TON и смарт-контракты

## Граница TON

Текущий пользовательский runtime LOOP работает с TON testnet, global ID `-3`. Код также
поддерживает mainnet `-239`, но этот путь закрыт evidence gate и не активирован. Пользователь
подписывает действия внешним кошельком через TON Connect. Backend не имеет пользовательских
ключей и не может подписать финансовую транзакцию вместо пользователя.

`1 GRAM = 1_000_000_000 nanoGRAM`. Все расчёты контрактов целочисленные; `mulDivFloor`
округляет вниз.

## Активные deployments

| Контракт   | Version | Address                                            | Code hash                                                          | Fee  |
| ---------- | ------- | -------------------------------------------------- | ------------------------------------------------------------------ | ---- |
| BankQueue  | 1.3.0   | `kQCqjhisqfxDrsPOEMWFE6AI1OWBtIQy_VVfXZU25zD50Il3` | `BA0A33E5D7A39358732E89720981EA421374A453AAF5B44C552569C5C71FB3E2` | 1%   |
| DuelEscrow | 1.3.0   | `kQD7JaRbyRrkGFzk9Xk3rfpRqNBSAUF2T-kXxfDlXYw4lg3M` | `5BDAED2F56EF9F51B33F0B388EF7B31DDE843961D23876A16243BA06D53C17FB` | 2.5% |

Explorer:

- [BankQueue](https://testnet.tonviewer.com/kQCqjhisqfxDrsPOEMWFE6AI1OWBtIQy_VVfXZU25zD50Il3)
- [DuelEscrow](https://testnet.tonviewer.com/kQD7JaRbyRrkGFzk9Xk3rfpRqNBSAUF2T-kXxfDlXYw4lg3M)

Owner и treasury обоих deployments — публичный адрес
`kQC820tGBtPVavhCbFZHnFavQObnCLitBKlGaEZ6-eyQTIY6`.

Полные deployment transaction, LT, initial data hash, toolchain и getters находятся в:

- `deployments/testnet/bank.json`;
- `deployments/testnet/duel.json`.

Manifest доказывает развёртывание и начальную конфигурацию. Он не является live state для
`locked`, balance, paused, fee, owner или treasury.

Поле `source_commit=21e604…` в testnet manifests — commit, из которого был собран неизменившийся
bytecode контрактов. Оно не обязано совпадать с более новым application runtime commit
`fc9f786…`: verifier отдельно доказывает, что текущая локальная сборка всё ещё имеет тот же code
hash.

## BankQueue 1.4.0

### Константы

| Параметр                | Значение                      |
| ----------------------- | ----------------------------- |
| minimum principal       | `1 GRAM`                      |
| initial principal limit | `5 GRAM`                      |
| maturity thresholds     | `10 @ 25`, `15 @ 100` GRAM    |
| later expansion         | `+5 GRAM / 250 completions`   |
| absolute limit          | `100 GRAM`                    |
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
3. при полном target увеличивает `completedPositions`, удаляет position из active map и queue,
   уменьшает `lockedFunding` на target и отправляет `BankPayout`;
4. продолжает до конца available или queue;
5. нераспределённый остаток становится `fundedAmount` новой position;
6. новая position всегда добавляется в tail.

Contract не имеет cancel/early-refund сообщения для подтверждённой position.

### Очистка завершённых позиций (v1.4)

Завершённая position удаляется из `positions`, а не сохраняется со статусом `payout_sent`.
Раньше словарь рос вместе с историей контракта, и каждый шаг каскада платил тем больше газа, чем
старше контракт. Это делало `BANK_MAX_ALLOCATION_STEPS = 81` мёртвым кодом: крупный депозит
против длинной очереди исчерпывал лимит `1 000 000` gas примерно на 69 шаге и падал с
`exit_code -14`, вместо того чтобы дойти до guard'а. После очистки худший достижимый каскад в 81
шаг укладывается в `861 439` gas, то есть guard снова осмыслен, а `-14` из честных состояний
недостижим. Защита от повторов остаётся в `usedPositionIds`, который трогается один раз на
депозит, а не на каждый шаг; публичным доказательством выплаты остаётся сообщение `BankPayout`.
Getter `positionData` больше не отвечает по завершённой позиции.

### Storage

- owner, treasury, feeBps, paused;
- headQueueIndex, nextQueueIndex, completedPositions, lockedFunding;
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

## DuelEscrow 1.5.0

### Константы

| Параметр                 | Значение                        |
| ------------------------ | ------------------------------- |
| total pool               | `1–100 GRAM`, кратен 4 nanoGRAM |
| initial chances          | новый продукт `5000 + 5000`     |
| boost range              | `1000–9000` bps                 |
| minimum boost            | `0.1 GRAM`                      |
| boost / extension / cap  | `60 / 20 / 180` секунд          |
| текущая fee              | `250 bps`                       |
| open gas buffer          | `0.05 GRAM`                     |
| action/admin minimum gas | `0.02 GRAM`                     |
| withdraw gas buffer      | `0.05 GRAM`                     |
| offer expiry             | 30–3600 секунд от chain time    |
| reveal window            | 300 секунд                      |
| retained reserve         | `0.2 GRAM`                      |

Contract сохраняет canonical `25/75` и `75/25` только на входе для protocol compatibility. API
создаёт новые AFK/direct offers с равными начальными долями. После match доли меняются только
сообщением `BoostDuel`.

### Stakes и payout

```text
chance A = floor(stake_A × 10_000 / (stake_A + stake_B))
chance B = 10_000 − chance A
fee      = feeExempt(winner) ? 0 : floor((stake_A + stake_B) × fee_bps / 10_000)
payout   = stake_A + stake_B − fee
```

Для нового матча оба начинают с половины pool. После каждого boost оба offers получают новый
итоговый pool/chance; `locked` увеличивается ровно на подтверждённую сумму.

### Holder fee exemption (v1.4)

Локальный source репозитория — DuelEscrow **1.4.0**; testnet deployment остаётся 1.3.0 до
следующего явного broadcast. v1.4 добавляет:

- `HolderFeePermit { validUntil, signature }` — опциональный maybe-ref в конце `OpenOffer`,
  `OpenDirectOffer` и `AcceptDirectOffer`;
- домен `0x4C4F4F63`: `hash(HOLDER_FEE_DOMAIN, network_id, contract_address, offer_id, owner,
valid_until)`, подпись — тот же `inviteSignerPublicKey`;
- `OfferData.feeExempt: bool` в storage и getter'ах; `contractConfig` дополнен
  `holderFeeSupported`;
- при settlement победитель с `feeExempt` получает полный пул: комиссия не удерживается и fee
  message не отправляется. Шанс, boost-математика и refund paths не меняются;
- невалидный или просроченный permit отвергает всё открытие (`InvalidHolderPermit=134`,
  `HolderPermitExpired=135`) — молчаливого «взяли комиссию всё равно» нет;
- v1.3 не принимает тела с maybe-bit, поэтому клиент строит layout строго по
  `holder_fee_supported` из ответа API, а backend включает выдачу permits только флагом
  `LOOP_DUEL_HOLDER_FEE_ENABLED`, который production startup сверяет с живым
  `holderFeeSupported`.

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
- Match создаёт `boostDeadline=now+60`, `hardDeadline=now+180` и revision `0`.
- Boost разрешён только владельцу своего offer, с точной revision и до обоих дедлайнов.
- Поздний boost переносит soft deadline на `min(now+20, hardDeadline)`.
- v1.5: boost принимается только если до `hardDeadline` остаётся полное окно расширения
  (`now + 20 <= hardDeadline`). Иначе последнее усиление могло прийти в ту же секунду, когда окно
  закрывается, и соперник доказуемо не успевал ответить. Ущерба это не давало — при
  пропорциональных долях EV не меняется, — но продукт обещает окно ответа, поэтому его
  обеспечивает контракт, а не оговорка в интерфейсе.
- Reveal до `boostDeadline` запрещён.
- При двух reveals `outcome % total_pool < stake_A` выбирает A, иначе B.
- При одном reveal после deadline выигрывает единственный revealer.
- При нуле reveals оба stakes возвращаются.

### Storage

- owner, treasury, feeBps, networkId, inviteSignerPublicKey, paused, locked;
- offers: offer ID → owner/commitment/chance/pool/stake/expiry/state/direct;
- duels: duel ID → offer IDs, boost/hard/reveal deadlines, revision, secrets/revealedMask;
- activeOffers: owner address → offer ID;
- usedOfferIds: replay protection.

Contract удаляет terminal offers/duel из active maps и уменьшает `locked` перед отправкой payout
или refund.

### Сообщения

| Opcode       | Message               | Назначение                         |
| ------------ | --------------------- | ---------------------------------- |
| `0x4C4F4F01` | `OpenOffer`           | AFK/legacy offer                   |
| `0x4C4F4F02` | `CancelOffer`         | owner refund до match              |
| `0x4C4F4F03` | `MatchOffers`         | permissionless AFK match           |
| `0x4C4F4F04` | `Reveal`              | раскрытие секрета                  |
| `0x4C4F4F05` | `ExpireOffer`         | permissionless unmatched refund    |
| `0x4C4F4F06` | `ExpireDuel`          | deadline settlement/refund         |
| `0x4C4F4F07` | `SetPaused`           | owner pause                        |
| `0x4C4F4F08` | `OpenDirectOffer`     | creator direct invite              |
| `0x4C4F4F09` | `AcceptDirectOffer`   | address-bound atomic accept/match  |
| `0x4C4F4F0A` | `DuelFundReserve`     | owner reserve                      |
| `0x4C4F4F0B` | `DuelWithdrawSurplus` | owner surplus withdrawal           |
| `0x4C4F4F0C` | `DuelSetFee`          | owner fee                          |
| `0x4C4F4F0D` | `DuelSetTreasury`     | owner treasury                     |
| `0x4C4F4F0E` | `DuelSetOwner`        | ownership transfer                 |
| `0x4C4F4F0F` | `BoostDuel`           | увеличить stake и пересчитать шанс |
| `0x4C4F4F11` | `DuelPayout`          | исходящее winner event             |
| `0x4C4F4F12` | `OfferRefund`         | исходящее refund event             |
| `0x4C4F4F13` | `ProtocolFee`         | исходящее fee event                |
| `0x4C4F4F14` | `DuelAdminWithdrawal` | исходящее admin withdrawal         |

Getters: `contractConfig`, `offerData`, `duelData`, `duelBoostData`, `directOfferData`, `activeOffer`,
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
совпадёт. DUEL worker перепроверяет direct permit, match, boost sender/value/revision/deadlines,
reveal owner и terminal payout/refund.

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

DUEL manifest содержит masterchain-finalized доказательства цепочек open → cancel → refund и
direct pair → boost → reveal → settlement. Verifier декодирует boost context, читает mutable
`locked` из сети и проверяет покрытие обязательств резервом.

## Проверка сети 2026-07-26 16:32 UTC

`scripts/verify-contracts.py --network testnet --require-smoke` показал:

- BankQueue v1.3 active, `completedPositions=1`, `principalLimit=5 GRAM`,
  `lockedFunding=0.73 GRAM`, live balance `1.417633799 GRAM`, reserve covered.
- DuelEscrow v1.3 active, active offers/duels пусты, `locked=0`.
- BANK limit smoke принял ровно 5 GRAM при стартовом лимите.
- BANK two-wallet smoke подтвердил два deposits, две fees и payout `1.25 GRAM`; остаток второго
  contributor стал текущей активной позицией и не является surplus.
- DUEL smoke открыл и отменил offer с полным возвратом.
- Двухкошельковый canary подтвердил boost `0.1 GRAM`, шанс `54.54%`, реальный deadline,
  settlement и masterchain finality.

Полный операционный снимок: [current-state.md](current-state.md).

## Предыдущие контракты

- Previous BankQueue v1.2:
  `kQAQRNh3sG80ykjME39tnWnfswnjCDcRtrrCDOQP4jv4FL_y`, paused, `locked=0`.
- Previous DuelEscrow v1.2:
  `kQD9vsBIFke3V_cxWQaW8ostPE-3ama0D7Hm_YGac02xo6yP`, paused, `locked=0`.
- Earlier BANK:
  `kQC1zcM8cxIDn3mFR0RV_PS_y2PzNkFttJ8NfAPHTyHrmc4l`, paused, recorded
  `locked=0.99 GRAM`, owner-only position `2207202601`.
- Earlier DUEL:
  `kQAiTNwDqQf0NB4iTWJCDjjm-12d6RH94lc4aJXFoWXv-t9d`, paused on-chain with `locked=0`.
- Earlier DUEL:
  `kQDVeChmpyLsgjLZRLW-gtwSS4s5depJWpBhuYkfhgYdu3Tw`, paused, recorded `locked=0`.

Старый BANK locked value нельзя выводить как surplus; это обязательство position. Старые адреса
не должны снова принимать новые пользовательские действия.

## DUEL canary

Canary использует две заранее созданные изолированные low-value Acton aliases на выбранной сети:

1. fork rehearsal с искусственным переводом времени;
2. direct open и address-bound accept в реальной сети;
3. подтверждённый boost и проверка revision/chance;
4. ожидание реального boost deadline;
5. оба reveals и settlement;
6. повторная проверка boost, payout и masterchain finality;
7. запись только подтверждённого результата в Redis metrics.

Canary не создаёт кошельки автоматически, не использует user wallets и не запускается в CI.
Testnet faucet запрашивается только ниже заданного balance floor; mainnet никогда не вызывает
faucet и требует отдельного явного разрешения. Private material остаётся в защищённом Acton store.

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
10. Mainnet не разворачивать без независимого аудита, release evidence, source verification,
    finalized smoke/canary proof и проверки полного drain старой сети.
