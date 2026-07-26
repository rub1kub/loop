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

  it('describes the intended PLUSH BRICK role without presenting it as already active', () => {
    render(<LandingPage />);

    expect(screen.getByRole('img', { name: 'Анимированный логотип PLUSH BRICK' })).toHaveAttribute(
      'src',
      'https://tonsuite.org/assets/plush-brick-video.gif',
    );
    expect(screen.getByRole('heading', { name: 'PLUSH BRICK замыкает круг.' })).toBeInTheDocument();
    expect(
      screen.getByText(/Сейчас LOOP только проверяет владение во внешнем кошельке/),
    ).toBeInTheDocument();
    expect(screen.getByText(/Сейчас комиссия LOOP одинакова для всех/)).toBeInTheDocument();
    expect(
      screen.getByText(/Режим без комиссии и выкуп — планы, а не текущее правило/),
    ).toBeInTheDocument();
    expect(screen.getByText(/Владение подтверждается внешним кошельком/)).toBeInTheDocument();
    // The runtime reports fee_discount_active=false and performs no buyback.
    // A "0%" tile or a present-tense discount promise must not come back
    // before the contract can actually honor it.
    expect(screen.queryByText('0%')).not.toBeInTheDocument();
    expect(screen.queryByText(/Комиссия LOOP для держателей/)).not.toBeInTheDocument();
    expect(
      screen.queryByText(/Маркет адресов TON Suite помогает находить размеченные/),
    ).not.toBeInTheDocument();
    expect(screen.queryByText(/PLUSH BRICK даёт только отметку/)).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /Маркет адресов/ })).not.toBeInTheDocument();
  });
});
