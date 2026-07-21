import {
  ArrowLeft,
  ChatCircleDots,
  Infinity as InfinityIcon,
  ShieldCheck,
} from '@phosphor-icons/react';

export function InlineDuelPreview() {
  return (
    <main className="inline-preview" aria-label="Telegram inline LOOP DUEL">
      <header className="telegram-header">
        <ArrowLeft aria-hidden="true" />
        <span className="telegram-avatar">
          <InfinityIcon aria-hidden="true" />
        </span>
        <div>
          <strong>LOOP</strong>
          <small>bot</small>
        </div>
        <ChatCircleDots aria-hidden="true" />
      </header>

      <section className="telegram-chat">
        <article className="inline-duel-card">
          <p className="eyebrow">LOOP DUEL</p>
          <h1>Дмитрий бросает тебе вызов.</h1>
          <dl>
            <div>
              <dt>ТВОЯ СТАВКА</dt>
              <dd>1 GRAM</dd>
            </div>
            <div>
              <dt>ТВОЙ ШАНС</dt>
              <dd>25%</dd>
            </div>
          </dl>
          <p className="inline-proof">
            <ShieldCheck aria-hidden="true" />
            При победе: +2.9 GRAM · TON testnet
          </p>
          <button>ПРИНЯТЬ</button>
        </article>
        <time>18:42</time>
      </section>
    </main>
  );
}
