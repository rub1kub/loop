import { useState } from 'react';

import { haptic, openPlatformLink } from '../telegram';
import type { Announcement as AnnouncementData } from '../types';

const DISMISSED_KEY = 'loop:announcement-dismissed';

/**
 * A note from the channel, shown inside the app.
 *
 * Two thirds of the people here opened the mini app from a link and never
 * pressed Start in the bot, so Telegram will not let it write to them at all.
 * The app is the only place left to say anything to them.
 *
 * It is shaped like the message it actually is, and it is deliberately cut off:
 * the text fades into the card rather than ending, because the rest of it lives
 * in the channel and the whole point is to go there. A fade is honest about
 * that in a way a truncating ellipsis is not — nothing is hidden, the road just
 * continues elsewhere.
 */
export function Announcement({ data }: { data: AnnouncementData }) {
  const [dismissed, setDismissed] = useState(
    () => window.localStorage.getItem(DISMISSED_KEY) === data.text,
  );
  if (dismissed) return null;

  return (
    <div className="announcement">
      <button
        type="button"
        className="announcement-card"
        onClick={() => {
          haptic('selection');
          // A t.me address belongs to Telegram's own viewer, not a browser tab.
          if (data.url) openPlatformLink(data.url, data.url.includes('t.me/'));
        }}
      >
        <span className="announcement-head">
          <span className="announcement-avatar" aria-hidden>
            R
          </span>
          <span className="announcement-author">rubikub</span>
        </span>
        <span className="announcement-body">{data.text}</span>
        <span className="announcement-more">{data.url ? 'Читать полностью' : ''}</span>
      </button>
      <button
        type="button"
        className="announcement-close"
        aria-label="Скрыть объявление"
        onClick={() => {
          // Remembered by its text, so the next announcement appears on its own
          // and this one does not come back every time the app is opened.
          window.localStorage.setItem(DISMISSED_KEY, data.text);
          setDismissed(true);
        }}
      >
        ✕
      </button>
    </div>
  );
}
