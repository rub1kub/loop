import { useEffect, useState } from 'react';

import { haptic, openPlatformLink } from '../telegram';
import type { Announcement as AnnouncementData } from '../types';

const SEEN_KEY = 'loop:announcement-read';

/**
 * A note from the channel, shown where the bot is not allowed to write.
 *
 * Two thirds of the people here opened the mini app from a link and never
 * pressed Start in the bot, so Telegram refuses to deliver anything to them.
 * Inside the app there is no such wall.
 *
 * It is shaped like the message it is, and it is deliberately cut short: the
 * text fades into the sheet rather than ending, because the rest of it lives in
 * the channel and going there is the whole point. A fade is honest about that
 * in a way a truncating ellipsis is not — nothing is hidden, the road simply
 * continues elsewhere.
 *
 * Once dismissed it is gone for good, whichever way it was dismissed. Closing
 * it is an answer too, and asking the same question again every time the app
 * opens is how a note stops being read and starts being swatted. The next
 * announcement is a different message and shows up on its own.
 */
export function Announcement({ data }: { data: AnnouncementData }) {
  const [open, setOpen] = useState(() => window.localStorage.getItem(SEEN_KEY) !== data.text);

  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') dismiss();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  if (!open) return null;

  function dismiss() {
    // Remembered by the text, so the next announcement is a new question.
    window.localStorage.setItem(SEEN_KEY, data.text);
    setOpen(false);
  }

  function read() {
    haptic('selection');
    dismiss();
    // A t.me address belongs to Telegram's own viewer: opened in a browser tab
    // the reader arrives at the channel signed out and cannot subscribe.
    if (data.url) openPlatformLink(data.url, data.url.includes('t.me/'));
  }

  return (
    <div className="announcement-backdrop" onClick={dismiss}>
      <div
        className="announcement-sheet"
        role="dialog"
        aria-modal="true"
        aria-label="Сообщение из канала"
        onClick={(event) => event.stopPropagation()}
      >
        <button type="button" className="announcement-close" aria-label="Закрыть" onClick={dismiss}>
          ✕
        </button>
        <div className="announcement-head">
          <img className="announcement-avatar" src="/assets/channel-avatar.jpg" alt="" />
          <span className="announcement-author">rubikub</span>
        </div>
        <div className="announcement-body">{data.text}</div>
        {data.url && (
          <button type="button" className="announcement-read" onClick={read}>
            ЧИТАТЬ ПОЛНОСТЬЮ
          </button>
        )}
      </div>
    </div>
  );
}
