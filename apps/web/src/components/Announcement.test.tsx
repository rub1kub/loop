import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { Announcement } from './Announcement';

const telegram = vi.hoisted(() => ({ openPlatformLink: vi.fn(), haptic: vi.fn() }));
vi.mock('../telegram', () => telegram);

const note = { text: 'Первая ночь. 575 GRAM отправлено людям.', url: 'https://t.me/rubikub/5158' };

describe('the note from the channel', () => {
  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
    window.localStorage.clear();
  });

  it('opens the post in Telegram rather than a browser tab', () => {
    // A t.me address handed to openLink leaves the app for a web view of the
    // channel, where the person is not signed in and cannot subscribe.
    render(<Announcement data={note} />);
    fireEvent.click(screen.getByText('Читать полностью'));

    expect(telegram.openPlatformLink).toHaveBeenCalledWith('https://t.me/rubikub/5158', true);
  });

  it('stays dismissed for this note, and steps aside for the next one', () => {
    const { unmount } = render(<Announcement data={note} />);
    fireEvent.click(screen.getByLabelText('Скрыть объявление'));
    expect(screen.queryByText(note.text)).toBeNull();
    unmount();

    render(<Announcement data={note} />);
    expect(screen.queryByText(note.text)).toBeNull();
    cleanup();

    // A different announcement is a different message and shows up again.
    render(<Announcement data={{ ...note, text: 'Потолок поднят до 10 GRAM.' }} />);
    expect(screen.getByText('Потолок поднят до 10 GRAM.')).toBeTruthy();
  });

  it('says nothing about reading on when there is nowhere to go', () => {
    render(<Announcement data={{ text: 'Короткая заметка', url: null }} />);
    fireEvent.click(screen.getByText('Короткая заметка'));

    expect(telegram.openPlatformLink).not.toHaveBeenCalled();
  });
});
