import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { TabBar } from './TabBar';

describe('TabBar', () => {
  it('keeps DUEL and rating before the centered BANK action', () => {
    const onChange = vi.fn();
    render(<TabBar active="duel" onChange={onChange} />);

    const tabs = screen.getAllByRole('button');
    expect(tabs.map((tab) => tab.textContent)).toEqual([
      'DUEL',
      'РЕЙТИНГ',
      'BANK',
      'КОМАНДЫ',
      'ПРОФИЛЬ',
    ]);
    expect(tabs[2]).toHaveClass('bank-home-tab');
    expect(tabs[0]).toHaveAttribute('aria-current', 'page');

    fireEvent.click(tabs[1]);
    expect(onChange).toHaveBeenCalledWith('rating');
  });
});
