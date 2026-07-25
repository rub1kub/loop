import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';

import { LandingPage } from './LandingPage';

afterEach(cleanup);

describe('browser landing', () => {
  it('explains LOOP and sends the visitor into Telegram', () => {
    render(<LandingPage />);

    expect(
      screen.getByRole('heading', { name: 'Ты входишь. Цикл продолжается.' }),
    ).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Банка помнит очередь.' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Один вызов. Два человека.' })).toBeInTheDocument();
    expect(screen.getByText(/Новые позиции финансируют более ранние/)).toBeInTheDocument();
    expect(
      screen.getAllByRole('link', { name: /Открыть в Telegram|Открыть LOOP/ })[0],
    ).toHaveAttribute('href', 'https://t.me/getloopbot?startapp');
  });

  it('puts the public source code in focus and lets visitors explore it', () => {
    render(<LandingPage />);

    expect(screen.queryByText('Здесь не хранят средства.')).not.toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Код открыт. Цикл виден.' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Смотреть на GitHub/ })).toHaveAttribute(
      'href',
      'https://github.com/rub1kub/loop',
    );
    expect(screen.getByText('bank/BankQueue.tolk')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Приложение' }));

    expect(screen.getByRole('heading', { name: 'WEB + API + BOT' })).toBeInTheDocument();
    expect(screen.getByText('web/src/')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Открыть раздел/ })).toHaveAttribute(
      'href',
      'https://github.com/rub1kub/loop/tree/main/apps',
    );
  });

  it('describes the real PLUSH BRICK behavior without promising an active discount', () => {
    render(<LandingPage />);

    expect(screen.getByText(/LOOP проверяет его во внешнем кошельке/)).toBeInTheDocument();
    expect(
      screen.getByText(/PLUSH BRICK не меняет очередь BANK и не влияет на шансы DUEL/),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/маркет адресов: он помогает находить размеченные/),
    ).toBeInTheDocument();
    expect(screen.queryByText(/скидк/i)).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Маркет TON‑адресов/ })).toHaveAttribute(
      'href',
      'https://tracker.plushbrick.fun/',
    );
  });
});
