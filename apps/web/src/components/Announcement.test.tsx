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
    window.sessionStorage.clear();
  });

  it('opens the post in Telegram rather than a browser tab', () => {
    // Handed to a browser the reader lands on the channel signed out, where
    // subscribing — the entire purpose — is not offered.
    render(<Announcement data={note} />);
    fireEvent.click(screen.getByText('ЧИТАТЬ ПОЛНОСТЬЮ'));

    expect(telegram.openPlatformLink).toHaveBeenCalledWith('https://t.me/rubikub/5158', true);
  });

  it('never returns once it has been read', () => {
    const first = render(<Announcement data={note} />);
    fireEvent.click(screen.getByText('ЧИТАТЬ ПОЛНОСТЬЮ'));
    first.unmount();

    // A new session, which is what a reopened mini app is.
    window.sessionStorage.clear();
    render(<Announcement data={note} />);
    expect(screen.queryByText(note.text)).toBeNull();
  });

  it('treats the cross as "not now" and asks again next time the app opens', () => {
    const first = render(<Announcement data={note} />);
    fireEvent.click(screen.getByLabelText('Закрыть'));
    expect(screen.queryByText(note.text)).toBeNull();
    first.unmount();

    // Same session: still out of the way.
    const second = render(<Announcement data={note} />);
    expect(screen.queryByText(note.text)).toBeNull();
    second.unmount();

    window.sessionStorage.clear();
    render(<Announcement data={note} />);
    expect(screen.getByText(note.text)).toBeTruthy();
  });

  it('lets the next announcement through on its own', () => {
    const first = render(<Announcement data={note} />);
    fireEvent.click(screen.getByText('ЧИТАТЬ ПОЛНОСТЬЮ'));
    first.unmount();

    render(<Announcement data={{ ...note, text: 'Потолок поднят до 10 GRAM.' }} />);
    expect(screen.getByText('Потолок поднят до 10 GRAM.')).toBeTruthy();
  });

  it('offers no way onward when there is nowhere to go', () => {
    render(<Announcement data={{ text: 'Короткая заметка', url: null }} />);
    expect(screen.queryByText('ЧИТАТЬ ПОЛНОСТЬЮ')).toBeNull();
    expect(telegram.openPlatformLink).not.toHaveBeenCalled();
  });
});
