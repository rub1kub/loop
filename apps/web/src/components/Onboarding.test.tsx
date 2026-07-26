import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import type { TelegramWebApp } from '../types';
import { Onboarding } from './Onboarding';

describe('Onboarding', () => {
  afterEach(() => {
    cleanup();
    delete window.Telegram;
  });

  it('pairs an intriguing opening with a plain-language explanation', () => {
    render(<Onboarding onDone={vi.fn()} />);

    expect(screen.getByRole('heading', { name: 'Войди в живой цикл.' })).toBeInTheDocument();
    expect(screen.getByText(/BANK — очередь выплат/)).toBeInTheDocument();
    expect(screen.getByLabelText('Экран 1 из 4')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'ПРОДОЛЖИТЬ' })).toBeInTheDocument();
  });

  it('explains BANK and DUEL in plain language', () => {
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
  });

  it('introduces PLUSH BRICK and links to each market before completing', () => {
    const onDone = vi.fn();
    render(<Onboarding initialPage={3} onDone={onDone} />);

    expect(
      screen.getByRole('heading', { name: 'Отдельный токен сообщества.' }),
    ).toBeInTheDocument();
    expect(screen.getByText(/не меняет комиссию, очередь BANK и шанс в DUEL/)).toBeInTheDocument();
    expect(screen.queryByText(/нужен для режима без комиссии/)).not.toBeInTheDocument();
    expect(screen.getByRole('img', { name: 'Анимированный логотип PLUSH BRICK' })).toHaveAttribute(
      'src',
      'https://tonsuite.org/assets/plush-brick-video.gif',
    );
    expect(screen.getByRole('link', { name: 'Купить PLUSH BRICK в dTrade' })).toHaveAttribute(
      'href',
      expect.stringContaining('https://t.me/dtrade'),
    );
    expect(screen.getByRole('link', { name: 'Купить PLUSH BRICK в RedoTrade' })).toHaveAttribute(
      'href',
      expect.stringContaining('https://t.me/redotrade'),
    );
    expect(screen.getByRole('link', { name: 'Купить PLUSH BRICK в STON.fi' })).toHaveAttribute(
      'href',
      expect.stringContaining('https://app.ston.fi/swap'),
    );
    fireEvent.click(screen.getByRole('button', { name: 'ВОЙТИ В LOOP' }));
    expect(onDone).toHaveBeenCalledOnce();
  });

  it('opens Telegram markets through the native bridge', () => {
    const openTelegramLink = vi.fn();
    window.Telegram = {
      WebApp: {
        openTelegramLink,
      } as unknown as TelegramWebApp,
    };
    render(<Onboarding initialPage={3} onDone={vi.fn()} />);

    fireEvent.click(screen.getByRole('link', { name: 'Купить PLUSH BRICK в dTrade' }));

    expect(openTelegramLink).toHaveBeenCalledWith(
      expect.stringContaining('https://t.me/dtrade?start='),
    );
  });
});
