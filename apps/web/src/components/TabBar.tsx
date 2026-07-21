import type { Tab } from '../types';

const tabs: { id: Tab; label: string; icon: string }[] = [
  { id: 'bank', label: 'BANK', icon: '◇' },
  { id: 'duel', label: 'DUEL', icon: '∞' },
  { id: 'profile', label: 'PROFILE', icon: '○' },
];

export function TabBar({ active, onChange }: { active: Tab; onChange: (tab: Tab) => void }) {
  return (
    <nav className="tab-bar" aria-label="Основная навигация">
      {tabs.map((tab) => (
        <button
          key={tab.id}
          className={active === tab.id ? 'active' : ''}
          onClick={() => onChange(tab.id)}
          aria-current={active === tab.id ? 'page' : undefined}
        >
          <span className="tab-icon">{tab.icon}</span>
          <span>{tab.label}</span>
        </button>
      ))}
    </nav>
  );
}
