import { ChartBar, Diamond, Infinity as InfinityIcon, UserCircle } from '@phosphor-icons/react';

import type { Tab } from '../types';

const tabs = [
  { id: 'bank', label: 'BANK', Icon: Diamond },
  { id: 'duel', label: 'DUEL', Icon: InfinityIcon },
  { id: 'rating', label: 'РЕЙТИНГ', Icon: ChartBar },
  { id: 'profile', label: 'ПРОФИЛЬ', Icon: UserCircle },
] satisfies { id: Tab; label: string; Icon: typeof Diamond }[];

export function TabBar({ active, onChange }: { active: Tab; onChange: (tab: Tab) => void }) {
  return (
    <nav className="tab-bar" aria-label="Основная навигация">
      {tabs.map(({ id, label, Icon }) => {
        const selected = active === id;
        return (
          <button
            key={id}
            className={selected ? 'active' : ''}
            onClick={() => onChange(id)}
            aria-current={selected ? 'page' : undefined}
          >
            <Icon size={25} weight={selected ? 'regular' : 'thin'} aria-hidden="true" />
            <span>{label}</span>
          </button>
        );
      })}
    </nav>
  );
}
