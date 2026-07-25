import { useEffect, useState, type PointerEvent as ReactPointerEvent, type ReactNode } from 'react';

const telegramUrl = 'https://t.me/getloopbot?startapp';
const githubUrl = 'https://github.com/rub1kub/loop';

const sourceAreas = [
  {
    id: 'contracts',
    label: 'Контракты',
    path: 'contracts/',
    title: 'BANK + DUEL',
    description: 'Правила исполнения написаны на Tolk и доступны для независимой проверки.',
    files: ['bank/BankQueue.tolk', 'duel/DuelEscrow.tolk'],
    href: `${githubUrl}/tree/main/contracts`,
  },
  {
    id: 'product',
    label: 'Приложение',
    path: 'apps/',
    title: 'WEB + API + BOT',
    description: 'Интерфейс, сервер и Telegram-бот открыты вместе с историей изменений.',
    files: ['web/src/', 'api/app/'],
    href: `${githubUrl}/tree/main/apps`,
  },
  {
    id: 'checks',
    label: 'Проверки',
    path: 'tests/',
    title: 'TESTS + PROOFS',
    description: 'Сценарии BANK, DUEL и проверки сети можно запустить самостоятельно.',
    files: ['bank_queue.test.tolk', 'duel_contract.test.tolk'],
    href: `${githubUrl}/tree/main/tests`,
  },
] as const;

function ArrowIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M5 12h14M13 6l6 6-6 6" />
    </svg>
  );
}

function TelegramIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="m21 4-3 16-6.2-4.6-3.1 3v-5.2L18 6.8 6.6 12 2 10.5 21 4Z" />
    </svg>
  );
}

function GitHubIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M12 2.8a9.4 9.4 0 0 0-3 18.3c.5.1.7-.2.7-.5v-1.8c-2.9.6-3.5-1.2-3.5-1.2-.5-1.2-1.2-1.5-1.2-1.5-1-.7.1-.7.1-.7 1.1.1 1.7 1.1 1.7 1.1 1 1.7 2.6 1.2 3.2.9.1-.7.4-1.2.7-1.5-2.3-.3-4.7-1.2-4.7-4.7 0-1 .4-1.9 1-2.5-.1-.3-.4-1.3.1-2.5 0 0 .8-.3 2.6 1a9 9 0 0 1 4.8 0c1.8-1.2 2.6-1 2.6-1 .5 1.2.2 2.2.1 2.5.7.7 1 1.5 1 2.5 0 3.6-2.4 4.4-4.7 4.7.4.3.7 1 .7 1.9v2.8c0 .4.2.6.7.5A9.4 9.4 0 0 0 12 2.8Z" />
    </svg>
  );
}

function InfinityMark({ compact = false }: { compact?: boolean }) {
  return (
    <svg
      className={compact ? 'landing-infinity landing-infinity--compact' : 'landing-infinity'}
      viewBox="0 0 240 120"
      aria-hidden="true"
    >
      <path d="M24 60c0-28 34-43 58-24l76 48c24 19 58 4 58-24s-34-43-58-24L82 84C58 103 24 88 24 60Z" />
    </svg>
  );
}

function ExternalLink({
  href,
  children,
  className = '',
}: {
  href: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <a className={className} href={href} target="_blank" rel="noreferrer">
      {children}
    </a>
  );
}

export function LandingPage() {
  const [activeSourceId, setActiveSourceId] =
    useState<(typeof sourceAreas)[number]['id']>('contracts');
  const activeSource = sourceAreas.find((source) => source.id === activeSourceId) ?? sourceAreas[0];

  useEffect(() => {
    const elements = Array.from(document.querySelectorAll<HTMLElement>('[data-reveal]'));
    if (!('IntersectionObserver' in window)) {
      elements.forEach((element) => element.classList.add('is-visible'));
      return;
    }

    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (!entry.isIntersecting) return;
          (entry.target as HTMLElement).classList.add('is-visible');
          observer.unobserve(entry.target);
        });
      },
      { rootMargin: '0px 0px -9% 0px', threshold: 0.12 },
    );
    elements.forEach((element) => observer.observe(element));
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    const landing = document.querySelector<HTMLElement>('.landing');
    if (!landing) return;

    const updateProgress = () => {
      const scrollable = document.documentElement.scrollHeight - window.innerHeight;
      const progress = scrollable > 0 ? Math.min(1, Math.max(0, window.scrollY / scrollable)) : 0;
      landing.style.setProperty('--landing-progress', progress.toString());
    };

    updateProgress();
    window.addEventListener('scroll', updateProgress, { passive: true });
    window.addEventListener('resize', updateProgress);
    return () => {
      window.removeEventListener('scroll', updateProgress);
      window.removeEventListener('resize', updateProgress);
    };
  }, []);

  const updatePointer = (event: ReactPointerEvent<HTMLElement>) => {
    if (event.pointerType === 'touch') return;
    const bounds = event.currentTarget.getBoundingClientRect();
    const x = (event.clientX - bounds.left) / bounds.width;
    const y = (event.clientY - bounds.top) / bounds.height;
    event.currentTarget.style.setProperty('--pointer-x', ((x - 0.5) * 2).toFixed(3));
    event.currentTarget.style.setProperty('--pointer-y', ((y - 0.5) * 2).toFixed(3));
    event.currentTarget.style.setProperty('--spotlight-x', `${(x * 100).toFixed(1)}%`);
    event.currentTarget.style.setProperty('--spotlight-y', `${(y * 100).toFixed(1)}%`);
  };

  const resetPointer = (event: ReactPointerEvent<HTMLElement>) => {
    event.currentTarget.style.setProperty('--pointer-x', '0');
    event.currentTarget.style.setProperty('--pointer-y', '0');
    event.currentTarget.style.setProperty('--spotlight-x', '50%');
    event.currentTarget.style.setProperty('--spotlight-y', '50%');
  };

  return (
    <div className="landing">
      <a className="landing-skip" href="#content">
        Перейти к содержимому
      </a>

      <header className="landing-header">
        <a className="landing-brand" href="#top" aria-label="LOOP — наверх">
          <InfinityMark compact />
          <span>LOOP</span>
        </a>
        <nav aria-label="Навигация по странице">
          <a href="#open-source">OPEN SOURCE</a>
          <a href="#bank">BANK</a>
          <a href="#duel">DUEL</a>
          <a href="#plush-brick">PLUSH BRICK</a>
        </nav>
        <ExternalLink className="landing-header__cta" href={telegramUrl}>
          Открыть
          <ArrowIcon />
        </ExternalLink>
      </header>

      <main id="content">
        <section className="landing-hero" id="top">
          <div className="landing-hero__copy">
            <span className="landing-eyebrow">TELEGRAM × TON</span>
            <h1>
              Ты входишь. <span>Цикл продолжается.</span>
            </h1>
            <p>
              LOOP — социальная игра внутри Telegram. Двигай очередь BANK или принимай честный вызов
              DUEL. Важные действия подтверждает сеть TON.
            </p>
            <div className="landing-actions">
              <ExternalLink className="landing-button landing-button--light" href={telegramUrl}>
                <TelegramIcon />
                Открыть в Telegram
              </ExternalLink>
              <a className="landing-button landing-button--ghost" href="#bank">
                Как устроен LOOP
                <ArrowIcon />
              </a>
            </div>
            <span className="landing-wallet-note">Кошелёк остаётся внешним. Всегда.</span>
          </div>

          <div
            className="landing-hero__art"
            aria-label="BANK и DUEL образуют LOOP"
            onPointerMove={updatePointer}
            onPointerLeave={resetPointer}
          >
            <div className="landing-hero__art-motion">
              <div className="landing-orbit landing-orbit--outer" />
              <div className="landing-orbit landing-orbit--inner" />
              <InfinityMark />
              <span className="landing-orbit__label landing-orbit__label--bank">BANK</span>
              <span className="landing-orbit__label landing-orbit__label--duel">DUEL</span>
              <div className="landing-pulse" />
            </div>
          </div>
        </section>

        <section className="landing-open-source" id="open-source">
          <div className="landing-open-source__copy" data-reveal>
            <span className="landing-eyebrow">OPEN SOURCE</span>
            <h2>
              Код открыт. <span>Цикл виден.</span>
            </h2>
            <p>Контракты, приложение и тесты LOOP лежат в публичном репозитории.</p>
            <ExternalLink className="landing-button landing-button--source" href={githubUrl}>
              <GitHubIcon />
              Смотреть на GitHub
              <ArrowIcon />
            </ExternalLink>
          </div>

          <div className="landing-open-source__stage" data-reveal>
            <div
              className="landing-repository"
              onPointerMove={updatePointer}
              onPointerLeave={resetPointer}
            >
              <div className="landing-repository__chrome">
                <span aria-hidden="true">
                  <i />
                  <i />
                  <i />
                </span>
                <strong>rub1kub / loop</strong>
                <em>PUBLIC</em>
              </div>
              <div className="landing-repository__tabs" aria-label="Разделы репозитория">
                {sourceAreas.map((source) => (
                  <button
                    key={source.id}
                    type="button"
                    aria-pressed={activeSource.id === source.id}
                    onClick={() => setActiveSourceId(source.id)}
                  >
                    {source.label}
                  </button>
                ))}
              </div>
              <div className="landing-repository__panel" key={activeSource.id}>
                <div>
                  <span>{activeSource.path}</span>
                  <h3>{activeSource.title}</h3>
                  <p>{activeSource.description}</p>
                </div>
                <div className="landing-repository__files">
                  {activeSource.files.map((file, index) => (
                    <span key={file}>
                      <i>{String(index + 1).padStart(2, '0')}</i>
                      <code>{file}</code>
                    </span>
                  ))}
                </div>
                <ExternalLink href={activeSource.href}>
                  Открыть раздел
                  <ArrowIcon />
                </ExternalLink>
              </div>
            </div>
          </div>
        </section>

        <section className="landing-bank" id="bank">
          <div className="landing-section-copy" data-reveal>
            <span className="landing-index">01</span>
            <span className="landing-eyebrow">BANK</span>
            <h2>Банка помнит очередь.</h2>
            <p>
              Создай позицию, выбери цель и наблюдай, как новые входы постепенно двигают цикл
              вперёд.
            </p>
            <div className="landing-facts">
              <span>Позиция</span>
              <span>Цель</span>
              <span>Прогресс</span>
            </div>
            <small>
              Новые позиции финансируют более ранние. Без новых входов движение может остановиться.
            </small>
          </div>

          <div className="landing-jar-stage" data-reveal>
            <div className="landing-jar-glow" />
            <img
              src="/assets/living-jar.webp"
              width="900"
              height="1015"
              alt="Стеклянная банка LOOP, наполненная движущимся песком"
            />
            <div className="landing-jar-caption">
              <span>ЖИВОЙ ЦИКЛ</span>
              <strong>62%</strong>
            </div>
          </div>
        </section>

        <section className="landing-duel" id="duel">
          <div className="landing-duel__visual" data-reveal>
            <div className="landing-player">
              <span>ТЫ</span>
            </div>
            <div className="landing-duel__link">
              <i />
              <InfinityMark compact />
              <i />
            </div>
            <div className="landing-player landing-player--muted">
              <span>?</span>
            </div>
            <strong>50 / 50</strong>
          </div>

          <div className="landing-section-copy landing-section-copy--dark" data-reveal>
            <span className="landing-index">02</span>
            <span className="landing-eyebrow">DUEL</span>
            <h2>Один вызов. Два человека.</h2>
            <p>
              Вызови друга или найди соперника. Одинаковые ставки, равные условия и результат,
              который исполняет контракт.
            </p>
            <div className="landing-duel__rules">
              <span>Прямой вызов</span>
              <span>Поиск соперника</span>
              <span>Возвраты по правилам</span>
            </div>
          </div>
        </section>

        <section className="landing-plush" id="plush-brick">
          <div className="landing-plush__mark" data-reveal aria-hidden="true">
            <div className="landing-brick">
              <span>PLUSH</span>
              <strong>BRICK</strong>
            </div>
            <span className="landing-plush__network">TON SUITE ECOSYSTEM</span>
          </div>

          <div className="landing-section-copy" data-reveal>
            <span className="landing-index">03</span>
            <span className="landing-eyebrow">PLUSH BRICK</span>
            <h2>Свой знак внутри экосистемы.</h2>
            <p>
              PLUSH BRICK — отдельный мем‑токен TON Suite. LOOP проверяет его во внешнем кошельке и
              подтверждает статус владельца прямо через сеть.
            </p>
            <div className="landing-plush__steps">
              <div>
                <span>01</span>
                <p>Подключаешь внешний кошелёк.</p>
              </div>
              <div>
                <span>02</span>
                <p>LOOP проверяет владение, не забирая токен.</p>
              </div>
              <div>
                <span>03</span>
                <p>Подтверждённый статус появляется в профиле LOOP.</p>
              </div>
            </div>
            <p className="landing-plush__market-note">
              В той же экосистеме работает маркет адресов: он помогает находить размеченные
              TON‑кошельки — китов, трейдеров и инфлюенсеров.
            </p>
            <small>PLUSH BRICK не меняет очередь BANK и не влияет на шансы DUEL.</small>
            <div className="landing-inline-links">
              <ExternalLink href="https://plushbrick.fun/">
                Открыть PLUSH BRICK
                <ArrowIcon />
              </ExternalLink>
              <ExternalLink href="https://tracker.plushbrick.fun/">
                Маркет TON‑адресов
                <ArrowIcon />
              </ExternalLink>
            </div>
          </div>
        </section>

        <section className="landing-proof">
          <div className="landing-proof__heading" data-reveal>
            <span className="landing-eyebrow">ТО, ЧТО МОЖНО ПРОВЕРИТЬ</span>
            <h2>Правила живут не в обещаниях.</h2>
          </div>
          <div className="landing-proof__grid">
            <article data-reveal>
              <span>01</span>
              <h3>Внешний кошелёк</h3>
              <p>LOOP не хранит ключи и средства пользователя.</p>
            </article>
            <article data-reveal>
              <span>02</span>
              <h3>Подтверждение в TON</h3>
              <p>Транзакции подписываются в подключённом кошельке.</p>
            </article>
            <article data-reveal>
              <span>03</span>
              <h3>Видимая история</h3>
              <p>Состояние BANK и DUEL сверяется с сетью.</p>
            </article>
          </div>
        </section>

        <section className="landing-final">
          <div data-reveal>
            <InfinityMark />
            <span className="landing-eyebrow">ЦИКЛ УЖЕ ИДЁТ</span>
            <h2>Твоё место — внутри.</h2>
            <ExternalLink className="landing-button landing-button--dark" href={telegramUrl}>
              <TelegramIcon />
              Открыть LOOP
            </ExternalLink>
          </div>
        </section>
      </main>

      <footer className="landing-footer">
        <a className="landing-brand" href="#top">
          <InfinityMark compact />
          <span>LOOP</span>
        </a>
        <nav aria-label="Ссылки экосистемы">
          <ExternalLink href="https://t.me/getloopbot">Telegram</ExternalLink>
          <ExternalLink href="https://tonsuite.org/">TON Suite</ExternalLink>
          <ExternalLink href="https://plushbrick.fun/">PLUSH BRICK</ExternalLink>
          <ExternalLink href="https://github.com/rub1kub/loop">GitHub</ExternalLink>
        </nav>
        <p>Участие связано с риском. Результат BANK не гарантирован.</p>
        <div>
          <a href="/privacy.html">Конфиденциальность</a>
          <a href="/terms.html">Условия</a>
          <span>© 2026 LOOP</span>
        </div>
      </footer>
    </div>
  );
}
