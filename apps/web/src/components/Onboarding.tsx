import { AnimatePresence, motion } from 'motion/react';
import { useEffect, useState } from 'react';

import { haptic, setBackAction } from '../telegram';

const stories = [
  'Один цикл\nначинается с одного шага.',
  'GRAM\nсоединяет людей.',
  'Создавай.\nИграй.\nПобеждай.',
  'Твой кошелёк.\nТвои средства.',
  'Добро пожаловать\nв LOOP.',
];

export function Onboarding({ onDone }: { onDone: () => void }) {
  const [page, setPage] = useState(0);

  useEffect(() => setBackAction(page ? () => setPage((value) => value - 1) : undefined), [page]);

  function next() {
    haptic('light');
    if (page === stories.length - 1) onDone();
    else setPage((value) => value + 1);
  }

  return (
    <main className="onboarding">
      <div className="story-stage" onClick={next} role="presentation">
        <AnimatePresence mode="wait">
          <motion.h1
            key={page}
            initial={{ opacity: 0, y: 18, filter: 'blur(8px)' }}
            animate={{ opacity: 1, y: 0, filter: 'blur(0px)' }}
            exit={{ opacity: 0, y: -12, filter: 'blur(6px)' }}
            transition={{ type: 'spring', stiffness: 180, damping: 24 }}
          >
            {stories[page].split('\n').map((line) => (
              <span key={line}>{line}</span>
            ))}
          </motion.h1>
        </AnimatePresence>
      </div>
      <div className="story-footer">
        <div className="story-dots" aria-label={`Экран ${page + 1} из ${stories.length}`}>
          {stories.map((story, index) => (
            <span key={story} className={index === page ? 'active' : ''} />
          ))}
        </div>
        <button className="primary-button" onClick={next}>
          {page === stories.length - 1 ? 'ВОЙТИ' : 'ДАЛЬШЕ'}
        </button>
      </div>
    </main>
  );
}
