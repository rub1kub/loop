import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { Onboarding } from './Onboarding';

describe('Onboarding', () => {
  afterEach(cleanup);

  it('pairs an intriguing opening with a plain-language explanation', () => {
    render(<Onboarding onDone={vi.fn()} />);

    expect(screen.getByRole('heading', { name: 'Войди в живой цикл.' })).toBeInTheDocument();
    expect(screen.getByText(/BANK — очередь выплат/)).toBeInTheDocument();
    expect(screen.getByLabelText('Экран 1 из 3')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'ПРОДОЛЖИТЬ' })).toBeInTheDocument();
  });

  it('explains BANK and completes from the final chapter', () => {
    const onDone = vi.fn();
    const { unmount } = render(<Onboarding initialPage={1} onDone={onDone} />);

    expect(
      screen.getByRole('heading', { name: 'Новые входят. Ранние получают.' }),
    ).toBeInTheDocument();
    expect(screen.getByText(/BANK — финансовая пирамида/)).toBeInTheDocument();
    expect(screen.getByText(/Без новых вкладов выплаты может не быть/)).toBeInTheDocument();

    unmount();
    render(<Onboarding initialPage={2} onDone={onDone} />);
    expect(
      screen.getByText(/Победителя определяют два заранее зафиксированных/),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'ВОЙТИ В LOOP' }));
    expect(onDone).toHaveBeenCalledOnce();
  });
});
