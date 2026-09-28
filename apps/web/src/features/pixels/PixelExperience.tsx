import { ArrowUpRight, DotsThree, GridFour, PaperPlaneTilt, X } from '@phosphor-icons/react';
import { useCallback, useEffect, useRef, useState } from 'react';
import { pixelApi } from '../../api';
import {
  haptic,
  isMockTelegram,
  openPlatformLink,
  setBackAction,
  telegram,
  telegramStartParam,
} from '../../telegram';
import { PixelCanvas } from './PixelCanvas';
import { advanceDemoPixels } from './demo';
import type { PixelModeration, PixelPoint, PixelRound, PixelScores, PixelState } from './protocol';
import { usePixels } from './usePixels';

declare global {
  interface Window {
    render_game_to_text?: () => string;
    advanceTime?: (ms: number) => void | Promise<void>;
  }
}

const colorNames = [
  'Угольный',
  'Белый',
  'Серый',
  'Графитовый',
  'Красный',
  'Оранжевый',
  'Жёлтый',
  'Салатовый',
  'Зелёный',
  'Бирюзовый',
  'Голубой',
  'Синий',
  'Фиолетовый',
  'Сиреневый',
  'Розовый',
  'Коричневый',
];
const date = (value: string) =>
  new Date(value).toLocaleDateString('ru-RU', {
    day: 'numeric',
    month: 'short',
    timeZone: 'Europe/Moscow',
  });

export function PixelExperience({
  userId,
  open,
  onOpenChange,
  blocked,
}: {
  userId: string;
  open: boolean;
  onOpenChange: (value: boolean) => void;
  blocked: boolean;
}) {
  const game = usePixels(userId, open);
  const { serverNow } = game;
  const [selection, setSelection] = useState<PixelPoint>({ x: 64, y: 64 });
  const [focus, setFocus] = useState<PixelPoint | null>(null);
  const [color, setColor] = useState(1);
  const [panel, setPanel] = useState(false);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [archived, setArchived] = useState<PixelState | null>(null);
  const [rounds, setRounds] = useState<PixelRound[]>([]);
  const [scores, setScores] = useState<PixelScores | null>(null);
  const [moderation, setModeration] = useState<PixelModeration>([]);
  const [sharing, setSharing] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [now, setNow] = useState(0);
  const modal = useRef<HTMLDivElement>(null);
  const launch = useRef<HTMLButtonElement>(null);
  const sharedLoaded = useRef(false);
  const state = archived ?? game.state;
  const roundId = state?.round?.id;
  const close = useCallback(() => {
    setPanel(false);
    setPaletteOpen(false);
    onOpenChange(false);
  }, [onOpenChange]);
  const back = useCallback(() => {
    if (panel) setPanel(false);
    else if (paletteOpen) setPaletteOpen(false);
    else if (archived) setArchived(null);
    else close();
  }, [panel, paletteOpen, archived, close]);

  useEffect(() => {
    if (!blocked && game.state?.enabled !== false) return;
    const frame = window.requestAnimationFrame(close);
    return () => window.cancelAnimationFrame(frame);
  }, [blocked, game.state?.enabled, close]);

  useEffect(() => {
    if (!open) return;
    const cleanup = setBackAction(back, 100);
    const keydown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        back();
      }
      if (event.key === 'Tab') {
        const controls = [
          ...(modal.current?.querySelectorAll<HTMLElement>(
            'button:not(:disabled), canvas[tabindex="0"], summary',
          ) ?? []),
        ].filter((element) => element.getClientRects().length > 0);
        const first = controls[0],
          last = controls.at(-1);
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last?.focus();
        }
        if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first?.focus();
        }
      }
    };
    window.addEventListener('keydown', keydown);
    return () => {
      cleanup();
      window.removeEventListener('keydown', keydown);
    };
  }, [open, back]);

  useEffect(() => {
    if (!open) return;
    const update = () => setNow(serverNow());
    const first = window.setTimeout(update, 0);
    const timer = window.setInterval(update, 500);
    return () => {
      window.clearTimeout(first);
      window.clearInterval(timer);
    };
  }, [open, serverNow, state?.server_time]);

  useEffect(() => {
    if (open) modal.current?.focus();
    else launch.current?.focus({ preventScroll: true });
  }, [open]);

  useEffect(() => {
    if (!game.state?.enabled || sharedLoaded.current) return;
    sharedLoaded.current = true;
    const start = telegramStartParam();
    const demoScreen =
      isMockTelegram() && new URLSearchParams(location.search).get('screen') === 'pixels';
    if (demoScreen || start === 'pixels' || start?.startsWith('pixel_')) onOpenChange(true);
    if (start?.startsWith('pixel_') && !isMockTelegram()) {
      void pixelApi
        .sharedRegion(start.slice(6))
        .then(async (region) => {
          setSelection({ x: region.x, y: region.y });
          setFocus({ x: region.x, y: region.y });
          if (region.round_id !== game.state?.round?.id)
            setArchived(await pixelApi.round(region.round_id));
        })
        .catch(() => setNotice('Этот фрагмент недоступен. Открыто текущее полотно'));
    }
  }, [game.state, onOpenChange]);

  useEffect(() => {
    if (!panel || !roundId) return;
    let alive = true;
    if (isMockTelegram()) {
      void Promise.resolve().then(() => {
        if (alive)
          setScores({
            teams: [
              {
                team_id: 'demo-1',
                name: 'COMICS CREW',
                held_pixels: 183,
                points: 6240,
                is_mine: false,
              },
              { team_id: 'demo-2', name: 'DEV', held_pixels: 124, points: 4380, is_mine: true },
            ],
            my_team: null,
          });
      });
      return () => {
        alive = false;
      };
    }
    void Promise.all([pixelApi.scores(roundId), pixelApi.archive(), pixelApi.moderation(roundId)])
      .then(([ranking, archive, log]) => {
        if (alive) {
          setScores(ranking);
          setRounds(archive);
          setModeration(log);
        }
      })
      .catch(() => {
        if (alive) setNotice('Не удалось обновить подробности. Открой их ещё раз');
      });
    return () => {
      alive = false;
    };
  }, [panel, roundId]);

  // A deterministic review hook exists only in the compile-time mock build.
  useEffect(() => {
    if (!isMockTelegram() || !open) return;
    const previousText = window.render_game_to_text;
    const previousAdvance = window.advanceTime;
    window.render_game_to_text = () =>
      JSON.stringify({
        mode: open ? 'pixels' : 'background',
        coordinate_system: 'origin top-left; x right, y down; 128×128',
        revision: state?.round?.revision,
        selected: selection,
        selected_color: color,
        cell_color: state?.pixels?.[selection.y * 128 + selection.x],
        ready_in_seconds:
          Math.max(0, Math.ceil((Date.parse(state?.ready_at ?? '') - game.serverNow()) / 1000)) ||
          0,
        connected: game.connected,
        placing: game.placing,
        archived: Boolean(archived),
        panel,
        paletteOpen,
      });
    window.advanceTime = async (ms) => {
      advanceDemoPixels(ms);
      game.refresh();
      await new Promise<void>((resolve) => window.setTimeout(resolve, 0));
      setNow(game.serverNow());
    };
    return () => {
      window.render_game_to_text = previousText;
      window.advanceTime = previousAdvance;
    };
  }, [open, state, selection, color, game, archived, panel, paletteOpen]);

  const remaining = Math.max(0, Math.ceil((Date.parse(state?.ready_at ?? '') - now) / 1000)) || 0;
  const ended = Boolean(
    state?.round && (state.round.archived || Date.parse(state.round.ends_at) <= now),
  );
  const sameColor = state?.pixels?.[selection.y * 128 + selection.x] === color.toString(16);
  const select = (point: PixelPoint) => {
    setSelection(point);
    game.clearError();
    setNotice(null);
    haptic('selection');
  };

  const share = async () => {
    if (!state?.round || sharing) return;
    setSharing(true);
    setNotice(null);
    try {
      if (isMockTelegram()) {
        setNotice('Карточка фрагмента готова');
        return;
      }
      const result = await pixelApi.share(state.round.id, selection);
      const bridge = telegram();
      if (result.prepared_message_id && bridge?.shareMessage) {
        bridge.shareMessage(result.prepared_message_id, () => undefined);
      } else {
        openPlatformLink(
          `https://t.me/share/url?url=${encodeURIComponent(result.url)}&text=${encodeURIComponent('Помоги дорисовать — бесплатно, прямо в Telegram')}`,
          true,
        );
      }
    } catch {
      setNotice('Не удалось подготовить карточку. Попробуй ещё раз');
    } finally {
      setSharing(false);
    }
  };

  if (!game.state?.enabled || !game.state.round || !state?.round) return null;
  return (
    <>
      <div className="pixel-background" aria-hidden="true">
        <PixelCanvas state={game.state} background />
      </div>
      {!open && !blocked && (
        <button
          ref={launch}
          className="pixel-launch"
          onClick={() => {
            haptic('light');
            onOpenChange(true);
          }}
        >
          <GridFour size={15} weight="fill" />
          <span>ПОЛОТНО</span>
          <ArrowUpRight size={13} />
        </button>
      )}
      {open && (
        <div
          className="pixel-mode"
          role="dialog"
          aria-modal="true"
          aria-labelledby="pixel-title"
          tabIndex={-1}
          ref={modal}
        >
          <header className="pixel-header">
            <div>
              <span className="pixel-eyebrow">{ended ? 'РАУНД ЗАВЕРШЁН' : 'ОБЩИЙ ФОН LOOP'}</span>
              <h1 id="pixel-title">ПОЛОТНО</h1>
            </div>
            <div className="pixel-header-actions">
              <button
                className="pixel-icon-button"
                aria-label="О полотне"
                onClick={() => {
                  setPaletteOpen(false);
                  setPanel(true);
                }}
              >
                <DotsThree size={26} />
              </button>
              {(!telegram()?.BackButton || isMockTelegram()) && (
                <button className="pixel-icon-button" aria-label="Закрыть полотно" onClick={close}>
                  <X size={20} />
                </button>
              )}
            </div>
          </header>
          <div className="pixel-round-line">
            <span>
              {date(state.round.starts_at)} — {date(state.round.ends_at)}
            </span>
            <span>{ended ? 'АРХИВ' : '1 ПИКСЕЛЬ / 30 СЕК'}</span>
          </div>
          <PixelCanvas
            key={state.round.id}
            state={state}
            selection={selection}
            onSelect={select}
            focus={focus}
          />
          <div className="pixel-coordinate-line">
            <span>
              {selection.x + 1} : {selection.y + 1}
            </span>
            <span role="status">
              {!game.connected
                ? 'Восстанавливаем связь…'
                : ended
                  ? 'Рисунок сохранён'
                  : 'Приближай · выбирай · рисуй'}
            </span>
          </div>
          <footer className="pixel-tools">
            {(notice || game.error) && (
              <p className="pixel-notice" role="status">
                {notice ?? game.error}
              </p>
            )}
            {ended ? (
              <button
                className="primary-button"
                onClick={() => {
                  setArchived(null);
                  game.refresh();
                }}
              >
                ТЕКУЩЕЕ ПОЛОТНО
              </button>
            ) : (
              <div className="pixel-paint-row">
                <button
                  className="pixel-color-button"
                  aria-label="Выбрать цвет"
                  aria-expanded={paletteOpen}
                  onClick={() => {
                    setPanel(false);
                    setPaletteOpen((value) => !value);
                  }}
                >
                  <span style={{ background: state.palette[color] }} />
                  <span>ЦВЕТ</span>
                </button>
                <button
                  className="primary-button pixel-paint"
                  disabled={game.placing || !game.connected || remaining > 0 || sameColor}
                  onClick={() => {
                    void game.place(selection.x, selection.y, color).then((placed) => {
                      if (placed) {
                        haptic('success');
                        setNotice(null);
                      }
                    });
                  }}
                >
                  {game.placing
                    ? 'СТАВИМ…'
                    : remaining > 0
                      ? `СЛЕДУЮЩИЙ ЧЕРЕЗ ${remaining} С`
                      : sameColor
                        ? 'ЗДЕСЬ УЖЕ ЭТОТ ЦВЕТ'
                        : 'ПОСТАВИТЬ ПИКСЕЛЬ'}
                </button>
              </div>
            )}
            <button className="pixel-share" onClick={() => void share()} disabled={sharing}>
              <PaperPlaneTilt size={17} />
              {sharing ? 'ГОТОВИМ КАРТОЧКУ…' : 'ПОЗВАТЬ РИСОВАТЬ'}
            </button>
          </footer>
          {paletteOpen && (
            <div className="pixel-palette-panel" role="group" aria-label="Палитра">
              <div className="pixel-panel-title">
                <span>ВЫБЕРИ ЦВЕТ</span>
                <button
                  className="pixel-icon-button"
                  aria-label="Закрыть палитру"
                  onClick={() => setPaletteOpen(false)}
                >
                  <X size={18} />
                </button>
              </div>
              <div className="pixel-palette">
                {state.palette.map((hex, index) => (
                  <button
                    key={hex}
                    style={{ background: hex }}
                    aria-label={colorNames[index]}
                    aria-pressed={color === index}
                    onClick={() => {
                      setColor(index);
                      setPaletteOpen(false);
                      game.clearError();
                      haptic('selection');
                    }}
                  />
                ))}
              </div>
            </div>
          )}
          {panel && (
            <div className="pixel-details-backdrop" onClick={() => setPanel(false)}>
              <section
                className="pixel-details"
                aria-label="Правила и команды"
                onClick={(event) => event.stopPropagation()}
              >
                <div className="pixel-panel-title">
                  <span>НАШЕ ПОЛОТНО</span>
                  <button
                    className="pixel-icon-button"
                    aria-label="Закрыть подробности"
                    onClick={() => setPanel(false)}
                  >
                    <X size={19} />
                  </button>
                </div>
                <p>
                  Один бесплатный пиксель каждые 30 секунд. Рисуй своё и перекрашивай чужое. Ходы не
                  копятся. У всех одинаковый лимит.
                </p>
                <p>
                  Раунд заканчивается в понедельник в 00:00 МСК. Рисунок остаётся в архиве,
                  начинается новое полотно.
                </p>
                <details>
                  <summary>Как соревнуются команды</summary>
                  <p>
                    Пиксель принадлежит команде того, кто последним изменил его цвет. Минута
                    удержания одного пикселя даёт одно очко. Смена команды не переносит уже занятые
                    пиксели. Деньги и токены не дают преимущества.
                  </p>
                </details>
                {scores && scores.teams.length > 0 && (
                  <div className="pixel-team-list">
                    {scores.teams.map((team, index) => (
                      <div key={team.team_id} className={team.is_mine ? 'is-mine' : ''}>
                        <span>{index + 1}</span>
                        <strong>{team.name}</strong>
                        <span>
                          {team.points.toLocaleString('ru-RU')}
                          <small>{team.held_pixels} пикс.</small>
                        </span>
                      </div>
                    ))}
                  </div>
                )}
                {scores?.teams.length === 0 && (
                  <p className="pixel-muted">Первый рисунок команды начнёт её счёт.</p>
                )}
                {rounds.length > 0 && (
                  <details>
                    <summary>Архив рисунков</summary>
                    {rounds.map((round) => (
                      <button
                        className="pixel-archive-link"
                        key={round.id}
                        onClick={() => {
                          void pixelApi
                            .round(round.id)
                            .then((snapshot) => {
                              setArchived(snapshot);
                              setPanel(false);
                              setFocus(null);
                            })
                            .catch(() => setNotice('Не удалось открыть архив'));
                        }}
                      >
                        {date(round.starts_at)} — {date(round.ends_at)}
                        <ArrowUpRight size={17} />
                      </button>
                    ))}
                  </details>
                )}
                <details>
                  <summary>Модерация</summary>
                  <p>
                    Модератор может убрать недопустимый рисунок. Каждая такая правка остаётся в этом
                    журнале.
                  </p>
                  {moderation.length === 0 ? (
                    <p>Правок модератора в этом раунде нет.</p>
                  ) : (
                    moderation.map((entry) => (
                      <p key={entry.id}>
                        {date(entry.created_at)} · {entry.reason} · область {entry.x + 1}:
                        {entry.y + 1}
                      </p>
                    ))
                  )}
                </details>
              </section>
            </div>
          )}
        </div>
      )}
    </>
  );
}
