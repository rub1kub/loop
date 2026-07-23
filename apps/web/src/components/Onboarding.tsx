import { AnimatePresence, motion } from 'motion/react';
import { useEffect, useState } from 'react';

import { haptic, setBackAction } from '../telegram';

const stories = [
  {
    signal: 'LOOP · TON TESTNET',
    title: 'Войди в живой\nцикл.',
    detail: 'BANK — очередь выплат. DUEL — честный вызов 1 на 1. Кошелёк остаётся внешним.',
  },
  {
    signal: '01 · BANK',
    title: 'Твой вклад\nзанимает очередь.',
    detail:
      'Следующие вклады сначала наполняют ранние банки. На 100% контракт платит. Срок не фиксирован; досрочной отмены нет.',
  },
  {
    signal: '02 · DUEL + SCORE',
    title: 'Равные условия.\nПубличный след.',
    detail:
      'Оба вносят одинаковую ставку 50/50. Контракт определяет результат, а завершённые on-chain действия повышают LOOP Score.',
  },
];

export function Onboarding({
  onDone,
  initialPage = 0,
}: {
  onDone: () => void;
  initialPage?: number;
}) {
  const [page, setPage] = useState(initialPage);
  const story = stories[page];

  useEffect(() => setBackAction(page ? () => setPage((value) => value - 1) : undefined), [page]);

  function next() {
    haptic('light');
    if (page === stories.length - 1) onDone();
    else setPage((value) => value + 1);
  }

  return (
    <main className="onboarding">
      <span className="onboarding-brand">LOOP · TESTNET</span>
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
            <img className="story-mark" src="/assets/loop-loader.webp" alt="" />
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
