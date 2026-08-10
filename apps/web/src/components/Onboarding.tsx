import { AnimatePresence, motion } from 'motion/react';
import { useEffect, useState } from 'react';

import { haptic, openPlatformLink, setBackAction } from '../telegram';

const plushBrickLogoUrl = '/assets/plush-brick-loop.webp';
const plushBrickFallbackUrl = '/assets/plush-brick-mark.webp';
const plushBrickMarkets = [
  {
    name: 'dTrade',
    url: 'https://t.me/dtrade?start=1IPvnLpaEN_EQAJ40p3zlCoomgANMQ4u5eIktLMZtWP87GGKDKlyW_EZBwt',
    telegramNative: true,
  },
  {
    name: 'RedoTrade',
    url: 'https://t.me/redotrade?start=rubikub-EQAJ40p3zlCoomgANMQ4u5eIktLMZtWP87GGKDKlyW_EZBwt',
    telegramNative: true,
  },
  {
    name: 'STON.fi',
    url: 'https://app.ston.fi/swap?chartVisible=true&ft=GRAM&tt=EQAJ40p3zlCoomgANMQ4u5eIktLMZtWP87GGKDKlyW_EZBwt&chartInterval=1w&fa=%2225%22',
    telegramNative: false,
  },
] as const;

const stories = [
  {
    signal: 'LOOP · НАЧАЛО',
    title: 'Войди в живой\nцикл.',
    detail: 'BANK — финансовая пирамида. DUEL — вызов 1 на 1. Каждое действие подтверждаешь сам.',
  },
  {
    signal: '01 · BANK',
    title: 'Новые входят.\nРанние получают.',
    detail:
      'BANK — финансовая пирамида: новые взносы наполняют ранние позиции. Без новых взносов выплаты может не быть; позицию нельзя отменить.',
  },
  {
    signal: '02 · DUEL + СЧЁТ',
    title: 'Равная ставка.\nИсход из двух чисел.',
    detail:
      'Оба вносят одинаковую сумму. Победителя определяют два заранее зафиксированных тайных числа; завершённые действия повышают твой счёт LOOP.',
  },
  {
    signal: '03 · PLUSH BRICK',
    title: 'Кирпич замыкает\nцикл.',
    detail:
      'PLUSH BRICK нужен для режима без комиссии. Часть дохода LOOP возвращается на рынок — на выкуп токена.',
    mark: plushBrickLogoUrl,
  },
];

function PlushBrickMark() {
  const [attempt, setAttempt] = useState(0);
  const [failed, setFailed] = useState(false);
  const [loaded, setLoaded] = useState(false);
  useEffect(() => {
    if (!failed || attempt >= 3) return;
    const timeout = window.setTimeout(
      () => {
        setAttempt((value) => value + 1);
        setFailed(false);
      },
      1_500 * 2 ** attempt,
    );
    return () => window.clearTimeout(timeout);
  }, [attempt, failed]);
  const source = attempt > 0 ? `${plushBrickLogoUrl}?retry=${attempt}` : plushBrickLogoUrl;

  return (
    <span
      className="story-mark story-mark-plush"
      role="img"
      aria-label="Анимированный логотип PLUSH BRICK"
    >
      <img className="story-plush-fallback" src={plushBrickFallbackUrl} alt="" />
      {!failed && (
        <img
          key={source}
          className={`story-plush-motion${loaded ? ' is-loaded' : ''}`}
          src={source}
          alt=""
          onLoad={() => setLoaded(true)}
          onError={() => {
            setLoaded(false);
            setFailed(true);
          }}
        />
      )}
    </span>
  );
}

export function Onboarding({
  onDone,
  initialPage = 0,
}: {
  onDone: () => void;
  initialPage?: number;
}) {
  const [page, setPage] = useState(initialPage);
  const story = stories[page];

  // The mark lands on the last screen, so it is fetched while the reader is
  // still on the first one and is decoded by the time they swipe to it.
  useEffect(() => {
    const fallback = new Image();
    fallback.src = plushBrickFallbackUrl;
    const preload = new Image();
    preload.src = plushBrickLogoUrl;
  }, []);

  useEffect(() => setBackAction(page ? () => setPage((value) => value - 1) : undefined), [page]);

  function next() {
    haptic('light');
    if (page === stories.length - 1) onDone();
    else setPage((value) => value + 1);
  }

  function openMarket(url: string, telegramNative: boolean) {
    haptic('light');
    openPlatformLink(url, telegramNative);
  }

  const isPlushBrickStory = story.mark === plushBrickLogoUrl;

  return (
    <main className="onboarding">
      <span className="onboarding-brand">LOOP</span>
      <button className="story-stage" onClick={next} aria-label="Продолжить историю LOOP">
        <AnimatePresence mode="wait">
          <motion.div
            className="story-copy"
            key={page}
            initial={{ opacity: 0, y: 18, filter: 'blur(8px)' }}
            animate={{ opacity: 1, y: 0, filter: 'blur(0px)' }}
            exit={{ opacity: 0, y: -12, filter: 'blur(6px)' }}
            transition={{ duration: 0.24, ease: [0.22, 1, 0.36, 1] }}
          >
            {isPlushBrickStory ? (
              <PlushBrickMark />
            ) : (
              <img
                className="story-mark"
                src={story.mark ?? '/assets/loop-loader.webp'}
                width={640}
                height={427}
                alt=""
              />
            )}
            <p className="story-signal">{story.signal}</p>
            <h1 aria-label={story.title.replace('\n', ' ')}>
              {story.title.split('\n').map((line) => (
                <span key={line}>{line}</span>
              ))}
            </h1>
            <p className="story-detail">{story.detail}</p>
          </motion.div>
        </AnimatePresence>
      </button>
      <div className="story-footer">
        {isPlushBrickStory ? (
          <div className="story-market-links" aria-label="Купить PLUSH BRICK">
            {plushBrickMarkets.map((market) => (
              <a
                key={market.name}
                href={market.url}
                target="_blank"
                rel="noopener noreferrer"
                aria-label={`Купить PLUSH BRICK в ${market.name}`}
                onClick={(event) => {
                  event.preventDefault();
                  openMarket(market.url, market.telegramNative);
                }}
              >
                <small>КУПИТЬ В</small>
                <span>{market.name}</span>
              </a>
            ))}
          </div>
        ) : null}
        <div className="story-dots" aria-label={`Экран ${page + 1} из ${stories.length}`}>
          {stories.map((story, index) => (
            <span key={story.signal} className={index === page ? 'active' : ''} />
          ))}
        </div>
        <button className="primary-button" onClick={next}>
          {page === stories.length - 1 ? 'ВОЙТИ В LOOP' : page === 0 ? 'ПРОДОЛЖИТЬ' : 'ДАЛЬШЕ'}
        </button>
      </div>
    </main>
  );
}
