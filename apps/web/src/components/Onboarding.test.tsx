import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { Onboarding } from './Onboarding';

describe('Onboarding', () => {
  afterEach(cleanup);

  it('pairs an intriguing opening with a plain-language explanation', () => {
    render(<Onboarding onDone={vi.fn()} />);

    expect(screen.getByRole('heading', { name: 'Цикл уже начался.' })).toBeInTheDocument();
    expect(screen.getByText('BANK и DUEL — два режима одной живой системы.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'ПРОДОЛЖИТЬ' })).toBeInTheDocument();
  });

  it('explains BANK and completes from the final chapter', () => {
    const onDone = vi.fn();
    const { unmount } = render(<Onboarding initialPage={1} onDone={onDone} />);

    expect(screen.getByRole('heading', { name: 'Следующие двигают первых.' })).toBeInTheDocument();
    expect(
      screen.getByText('Создай позицию. Новые участники продвигают очередь.'),
    ).toBeInTheDocument();

    unmount();
    render(<Onboarding initialPage={4} onDone={onDone} />);
    fireEvent.click(screen.getByRole('button', { name: 'ВОЙТИ В LOOP' }));
    expect(onDone).toHaveBeenCalledOnce();
  });
});
