import { describe, expect, it } from 'vitest';

import { humanError, isWalletRefusal } from './errors';

describe('humanError', () => {
  it('says nothing when the person simply declined in their wallet', () => {
    // TON Connect throws this after the confirmation sheet is dismissed. It is
    // a decision, not a failure, and it used to be shown as a wall of brackets.
    const rejected = new Error('[TON_CONNECT_SDK_ERROR] Wallet declined the request');
    rejected.name = 'UserRejectsError';

    expect(isWalletRefusal(rejected)).toBe(true);
    expect(humanError(rejected, 'Не удалось создать DUEL')).toBeNull();
  });

  it('replaces a library status code with a sentence', () => {
    // Telegram answers an unsupported storage tier with exactly this word.
    expect(humanError(new Error('UNSUPPORTED'), 'Не удалось создать DUEL')).toBe(
      'Не удалось создать DUEL',
    );
    expect(humanError(new Error('[TON_CONNECT_SDK_ERROR] BadRequestError'), 'Запасной')).toBe(
      'Запасной',
    );
    expect(humanError({ weird: true }, 'Запасной')).toBe('Запасной');
  });

  it('keeps the messages we wrote for people ourselves', () => {
    expect(humanError(new Error('Сейчас ставка — ровно 0,5 GRAM'), 'Запасной')).toBe(
      'Сейчас ставка — ровно 0,5 GRAM',
    );
    expect(humanError(new Error('DUEL сейчас закрыт'), 'Запасной')).toBe('DUEL сейчас закрыт');
  });

  it('does not mistake a Russian refusal notice for machine noise', () => {
    expect(humanError(new Error('Кошелёк отклонил запрос пользователя'), 'Запасной')).toBeNull();
  });

  it('does not treat an ambiguous cancellation after broadcast as a refusal', () => {
    expect(isWalletRefusal(new Error('Transaction cancelled after broadcast timeout'))).toBe(false);
  });
});
