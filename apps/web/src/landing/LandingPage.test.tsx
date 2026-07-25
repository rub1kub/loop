import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';

import { LandingPage } from './LandingPage';

afterEach(cleanup);

describe('browser landing', () => {
  it('explains LOOP and sends the visitor into Telegram', () => {
    render(<LandingPage />);

    expect(screen.getByRole('heading', { name: 'Зайди. Дальше — твой ход.' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Встань в очередь.' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Брось вызов.' })).toBeInTheDocument();
    expect(screen.getByText(/Нет новых позиций — очередь стоит/)).toBeInTheDocument();
    expect(screen.getAllByRole('link', { name: 'Запустить LOOP' })[0]).toHaveAttribute(
      'href',
      'https://t.me/getloopbot?startapp',
    );
  });

  it('puts the public source code in focus and lets visitors explore it', () => {
    render(<LandingPage />);

    expect(screen.queryByText('Здесь не хранят средства.')).not.toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Весь LOOP — на GitHub.' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Открыть репозиторий/ })).toHaveAttribute(
      'href',
      'https://github.com/rub1kub/loop',
    );
    expect(screen.getByText('bank/BankQueue.tolk')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Приложение' }));

    expect(screen.getByRole('heading', { name: 'ПРИЛОЖЕНИЕ И БОТ' })).toBeInTheDocument();
    expect(screen.getByText('web/src/')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Открыть раздел/ })).toHaveAttribute(
      'href',
      'https://github.com/rub1kub/loop/tree/main/apps',
    );
  });

  it('describes the real PLUSH BRICK behavior without promising an active discount', () => {
    render(<LandingPage />);

    expect(screen.getByText(/LOOP проверит подключённый кошелёк/)).toBeInTheDocument();
    expect(screen.getByText(/На очередь BANK и шансы DUEL он не влияет/)).toBeInTheDocument();
    expect(
      screen.getByText(/Маркет адресов TON Suite помогает находить размеченные/),
    ).toBeInTheDocument();
    expect(screen.queryByText(/скидк/i)).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Маркет адресов/ })).toHaveAttribute(
      'href',
      'https://tracker.plushbrick.fun/',
    );
  });
});
