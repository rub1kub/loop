import { useEffect, useState, type PointerEvent as ReactPointerEvent, type ReactNode } from 'react';

const telegramUrl = 'https://t.me/getloopbot?startapp';
const githubUrl = 'https://github.com/rub1kub/loop';
const plushBrickLogoUrl = 'https://tonsuite.org/assets/plush-brick-video.gif';

const sourceAreas = [
  {
    id: 'contracts',
    label: 'Контракты',
    path: 'contracts/',
    title: 'BANK И DUEL',
    description: 'Контракты написаны на Tolk. Их можно прочитать, собрать и проверить.',
    files: ['bank/BankQueue.tolk', 'duel/DuelEscrow.tolk'],
    href: `${githubUrl}/tree/main/contracts`,
  },
  {
    id: 'product',
    label: 'Приложение',
    path: 'apps/',
    title: 'ПРИЛОЖЕНИЕ И БОТ',
    description: 'Здесь весь LOOP: интерфейс, сервер и Telegram-бот.',
    files: ['web/src/', 'api/app/'],
    href: `${githubUrl}/tree/main/apps`,
  },
  {
    id: 'checks',
    label: 'Тесты',
    path: 'tests/',
    title: 'ТЕСТЫ',
    description: 'Тесты BANK и DUEL запускаются прямо из репозитория.',
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
          <a href="#open-source">GITHUB</a>
          <a href="#bank">BANK</a>
          <a href="#duel">DUEL</a>
          <a href="#plush-brick">PLUSH BRICK</a>
        </nav>
        <ExternalLink className="landing-header__cta" href={telegramUrl}>
          Запустить
          <ArrowIcon />
        </ExternalLink>
      </header>

      <main id="content">
        <section className="landing-hero" id="top">
          <div className="landing-hero__copy">
            <span className="landing-eyebrow">ИГРА ВНУТРИ TELEGRAM</span>
            <h1>
              Зайди. <span>Дальше — твой ход.</span>
            </h1>
            <p>В LOOP есть очередь BANK и дуэли 50/50. Всё открывается прямо в Telegram.</p>
            <div className="landing-actions">
              <ExternalLink className="landing-button landing-button--light" href={telegramUrl}>
                <TelegramIcon />
                Запустить LOOP
              </ExternalLink>
              <a className="landing-button landing-button--ghost" href="#bank">
                Посмотреть режимы
                <ArrowIcon />
              </a>
            </div>
            <span className="landing-wallet-note">Транзакции подписываются в твоём кошельке.</span>
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
            <span className="landing-eyebrow">ОТКРЫТЫЙ КОД</span>
            <h2>
              Весь LOOP — <span>на GitHub.</span>
            </h2>
            <p>
              Интерфейс, бот, сервер, контракты и тесты доступны всем. Можно проверить, собрать или
              предложить правку.
            </p>
            <ExternalLink className="landing-button landing-button--source" href={githubUrl}>
              <GitHubIcon />
              Открыть репозиторий
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
            <h2>Встань в очередь.</h2>
            <p>
              Выбираешь сумму и цель — получаешь место. Новые взносы сначала пополняют позиции тех,
              кто вошёл раньше.
            </p>
            <div className="landing-facts">
              <span>Твоё место</span>
              <span>Цель</span>
              <span>До выплаты</span>
            </div>
            <small>Нет новых позиций — очередь стоит. Выплата не гарантирована.</small>
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
              <span>ДО ЦЕЛИ</span>
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
            <h2>Брось вызов.</h2>
            <p>
              Позови друга или найди соперника. Ставки равны, а исход складывается из скрытых чисел
              обоих игроков — сервер его не выбирает.
            </p>
            <div className="landing-duel__rules">
              <span>Друг или случайный соперник</span>
              <span>Одинаковая ставка</span>
              <span>Не сыграли — возврат</span>
            </div>
          </div>
        </section>

        <section className="landing-plush" id="plush-brick">
          <div className="landing-plush__mark" data-reveal>
            <ExternalLink className="landing-plush__logo-link" href="https://plushbrick.fun/">
              <img
                className="landing-plush__logo"
                src={plushBrickLogoUrl}
                alt="Анимированный логотип PLUSH BRICK"
                width="800"
                height="800"
                loading="lazy"
                decoding="async"
              />
            </ExternalLink>
            <span className="landing-plush__network">ЭКОСИСТЕМА TON SUITE</span>
          </div>

          <div className="landing-section-copy" data-reveal>
            <span className="landing-index">03</span>
            <span className="landing-eyebrow">PLUSH BRICK</span>
            <h2>Есть PLUSH BRICK? LOOP это увидит.</h2>
            <p>
              Это мем‑токен TON Suite. LOOP проверит подключённый кошелёк и покажет отметку в
              профиле.
            </p>
            <div className="landing-plush__steps">
              <div>
                <span>01</span>
                <p>Кошелёк подключён</p>
              </div>
              <div>
                <span>02</span>
                <p>Токен найден</p>
              </div>
              <div>
                <span>03</span>
                <p>Отметка в профиле</p>
              </div>
            </div>
            <p className="landing-plush__market-note">
              Маркет адресов TON Suite помогает находить размеченные кошельки китов, трейдеров и
              инфлюенсеров.
            </p>
            <small>
              PLUSH BRICK даёт только отметку. На очередь BANK и шансы DUEL он не влияет.
            </small>
            <div className="landing-inline-links">
              <ExternalLink href="https://plushbrick.fun/">
                Сайт PLUSH BRICK
                <ArrowIcon />
              </ExternalLink>
              <ExternalLink href="https://tracker.plushbrick.fun/">
                Маркет адресов
                <ArrowIcon />
              </ExternalLink>
            </div>
          </div>
        </section>

        <section className="landing-proof">
          <div className="landing-proof__heading" data-reveal>
            <span className="landing-eyebrow">ПРОВЕРКА</span>
            <h2>Проверь сам.</h2>
          </div>
          <div className="landing-proof__grid">
            <article data-reveal>
              <span>01</span>
              <h3>Ключи — у тебя</h3>
              <p>LOOP их не получает.</p>
            </article>
            <article data-reveal>
              <span>02</span>
              <h3>Подпись — в кошельке</h3>
              <p>Транзакцию подтверждаешь сам.</p>
            </article>
            <article data-reveal>
              <span>03</span>
              <h3>История — в TON</h3>
              <p>BANK и DUEL можно сверить с сетью.</p>
            </article>
          </div>
        </section>

        <section className="landing-final">
          <div data-reveal>
            <InfinityMark />
            <span className="landing-eyebrow">LOOP В TELEGRAM</span>
            <h2>Зайди и выбери режим.</h2>
            <ExternalLink className="landing-button landing-button--dark" href={telegramUrl}>
              <TelegramIcon />
              Запустить LOOP
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
        <p>В BANK нет гарантированной выплаты. В DUEL можно проиграть.</p>
        <div>
          <a href="/privacy.html">Конфиденциальность</a>
          <a href="/terms.html">Условия</a>
          <span>© 2026 LOOP</span>
        </div>
      </footer>
    </div>
  );
}
