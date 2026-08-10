import {
  CaretDown,
  Check,
  GearSix,
  LockSimple,
  MagnifyingGlass,
  PaperPlaneTilt,
  Plus,
  UserPlus,
  UsersThree,
  X,
} from '@phosphor-icons/react';
import { AnimatePresence, motion } from 'motion/react';
import { FormEvent, useCallback, useEffect, useMemo, useState } from 'react';

import { api } from '../../api';
import { haptic, setBackAction, sharePreparedResult } from '../../telegram';
import { formatGram } from '../../ton';
import type {
  TeamDetail,
  TeamEntry,
  TeamInvitePreview,
  TeamMember,
  TeamOverview,
} from '../../types';

interface TeamsViewProps {
  overview: TeamOverview | null;
  invite: TeamInvitePreview | null;
  onRefresh: () => Promise<void>;
  onDismissInvite: () => void;
  onError: (message: string) => void;
}

type TeamsPage = 'home' | 'create' | 'search' | 'detail';

const policyLabels = {
  open: 'Вступление свободное',
  request: 'Вступление по заявке',
  invite: 'Только по приглашению',
} as const;

function message(error: unknown): string {
  return error instanceof Error ? error.message : 'Не удалось выполнить действие';
}

function seasonLeft(endsAt: string): string {
  const seconds = Math.max(0, Math.floor((new Date(endsAt).getTime() - Date.now()) / 1000));
  const days = Math.floor(seconds / 86_400);
  const hours = Math.floor((seconds % 86_400) / 3_600);
  if (days > 0) return `${days}Д ${hours}Ч ДО ФИНИША`;
  const minutes = Math.floor((seconds % 3_600) / 60);
  return `${hours}Ч ${minutes}М ДО ФИНИША`;
}

export function TeamMark({ mark, compact = false }: { mark: number; compact?: boolean }) {
  return (
    <span
      className={`team-mark team-mark-${mark % 6}${compact ? ' is-compact' : ''}`}
      aria-hidden="true"
    >
      <i />
    </span>
  );
}

function TeamAvatar({
  mark,
  url,
  compact = false,
}: {
  mark: number;
  url: string | null;
  compact?: boolean;
}) {
  const [failedUrl, setFailedUrl] = useState<string | null>(null);
  const visibleUrl = url && url !== failedUrl ? url : null;
  return (
    <span className={`team-avatar${compact ? ' is-compact' : ''}`} aria-hidden="true">
      <TeamMark mark={mark} compact={compact} />
      {visibleUrl && (
        <img src={visibleUrl} alt="" draggable={false} onError={() => setFailedUrl(visibleUrl)} />
      )}
    </span>
  );
}

export function TeamsView({
  overview,
  invite,
  onRefresh,
  onDismissInvite,
  onError,
}: TeamsViewProps) {
  const [page, setPage] = useState<TeamsPage>(invite ? 'home' : 'home');
  const [detail, setDetail] = useState<TeamDetail | null>(overview?.my_team ?? null);
  const [busy, setBusy] = useState(false);
  const [query, setQuery] = useState('');
  const [searchResults, setSearchResults] = useState<TeamEntry[]>([]);
  const [searchTotal, setSearchTotal] = useState(0);
  const [members, setMembers] = useState<TeamMember[]>(overview?.my_team?.top_members ?? []);
  const backToTeams = useCallback(() => {
    setPage('home');
    haptic('selection');
  }, []);

  useEffect(() => setBackAction(page === 'home' ? undefined : backToTeams), [backToTeams, page]);

  const openDetail = async (team: TeamEntry | TeamDetail) => {
    setBusy(true);
    try {
      const loaded = 'top_members' in team ? team : await api.team(team.slug);
      setDetail(loaded);
      setMembers(loaded.top_members);
      setPage('detail');
      haptic('selection');
    } catch (error) {
      onError(message(error));
    } finally {
      setBusy(false);
    }
  };

  const refreshDetail = async () => {
    if (!detail) return;
    const loaded = await api.team(detail.slug);
    setDetail(loaded);
    setMembers(loaded.top_members);
    await onRefresh();
  };

  const run = async (action: () => Promise<void>) => {
    if (busy) return;
    setBusy(true);
    try {
      await action();
      haptic('success');
    } catch (error) {
      haptic('error');
      onError(message(error));
    } finally {
      setBusy(false);
    }
  };

  if (!overview) {
    return (
      <>
        <header className="mode-header">
          <p className="eyebrow">СЕЗОН · ОБНОВЛЯЕТСЯ</p>
          <h1>КОМАНДЫ</h1>
        </header>
        <div className="teams-unavailable">
          <span className="waiting-ring" aria-hidden="true" />
          <strong>Собираем команды.</strong>
          <p>Личный рейтинг продолжает работать.</p>
        </div>
      </>
    );
  }

  const submitSearch = (event: FormEvent) => {
    event.preventDefault();
    void run(async () => {
      const result = await api.searchTeams(query);
      setSearchResults(result.items);
      setSearchTotal(result.total);
    });
  };

  return (
    <AnimatePresence mode="wait" initial={false}>
      <motion.div
        key={`${page}:${detail?.id ?? 'none'}`}
        className="teams-view"
        initial={{ opacity: 0, x: 8 }}
        animate={{ opacity: 1, x: 0 }}
        exit={{ opacity: 0, x: -6 }}
        transition={{ duration: 0.18 }}
      >
        {page === 'create' ? (
          <CreateTeam
            busy={busy}
            onCreate={(input) => {
              void run(async () => {
                const created = await api.createTeam(input);
                await onRefresh();
                await openDetail(created);
              });
            }}
          />
        ) : page === 'search' ? (
          <div className="team-subpage">
            <SubpageHeader title="НАЙТИ КОМАНДУ" />
            <form className="team-search" onSubmit={submitSearch}>
              <MagnifyingGlass aria-hidden="true" />
              <input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Название или тег"
                maxLength={32}
              />
              <button type="submit" disabled={busy}>
                НАЙТИ
              </button>
            </form>
            {searchResults.length > 0 && (
              <p className="team-search-count">НАЙДЕНО · {searchTotal}</p>
            )}
            <TeamList
              entries={searchResults.length ? searchResults : overview.leaderboard}
              onOpen={(team) => void openDetail(team)}
            />
          </div>
        ) : page === 'detail' && detail ? (
          <TeamDetailPanel
            detail={detail}
            leaderboard={overview.leaderboard}
            seasonEndsAt={overview.season.ends_at}
            members={members}
            busy={busy}
            onRefresh={() => void run(refreshDetail)}
            onJoin={() => {
              void run(async () => {
                const result = await api.joinTeam(detail.slug);
                await onRefresh();
                setDetail(result.team);
              });
            }}
            onLeave={() => {
              void run(async () => {
                if (!window.confirm('Покинуть команду? Новый вход будет доступен через 24 часа.')) {
                  return;
                }
                await api.leaveTeam(detail.slug);
                await onRefresh();
                setDetail(null);
                setPage('home');
              });
            }}
            onShare={() => {
              void run(async () => {
                const prepared = await api.prepareTeamShare(detail.slug);
                if (
                  !(await sharePreparedResult(
                    prepared.prepared_message_id,
                    prepared.fallback_query,
                  ))
                ) {
                  throw new Error('Telegram не открыл отправку сообщения');
                }
              });
            }}
            onLoadMore={() => {
              void run(async () => {
                const page = await api.teamMembers(detail.slug, members.length);
                setMembers((current) => [...current, ...page.items]);
              });
            }}
            onError={onError}
          />
        ) : (
          <>
            <header className="mode-header">
              <p className="eyebrow">СЕЗОН · {overview.season.name}</p>
              <h1>КОМАНДЫ</h1>
            </header>
            <TeamHome
              overview={overview}
              invite={invite}
              busy={busy}
              onDismissInvite={onDismissInvite}
              onAcceptInvite={() => {
                if (!invite) return;
                void run(async () => {
                  const result = await api.joinTeamInvite(invite.token);
                  onDismissInvite();
                  await onRefresh();
                  setDetail(result.team);
                  setMembers(result.team.top_members);
                  setPage('detail');
                });
              }}
              onCreate={() => setPage('create')}
              onSearch={() => setPage('search')}
              onOpen={(team) => void openDetail(team)}
              onShare={() => {
                const team = overview.my_team;
                if (!team) return;
                void run(async () => {
                  const prepared = await api.prepareTeamShare(team.slug);
                  if (
                    !(await sharePreparedResult(
                      prepared.prepared_message_id,
                      prepared.fallback_query,
                    ))
                  ) {
                    throw new Error('Telegram не открыл отправку сообщения');
                  }
                });
              }}
            />
          </>
        )}
      </motion.div>
    </AnimatePresence>
  );
}

function TeamHome({
  overview,
  invite,
  busy,
  onDismissInvite,
  onAcceptInvite,
  onCreate,
  onSearch,
  onOpen,
  onShare,
}: {
  overview: TeamOverview;
  invite: TeamInvitePreview | null;
  busy: boolean;
  onDismissInvite: () => void;
  onAcceptInvite: () => void;
  onCreate: () => void;
  onSearch: () => void;
  onOpen: (team: TeamEntry | TeamDetail) => void;
  onShare: () => void;
}) {
  const myTeam = overview.my_team;
  const rival = myTeam ? overview.leaderboard.find((team) => team.rank === myTeam.rank - 1) : null;
  return (
    <>
      {invite && (
        <section className="team-invite-card">
          <button className="team-invite-close" onClick={onDismissInvite} aria-label="Закрыть">
            <X aria-hidden="true" />
          </button>
          <TeamAvatar mark={invite.team.mark} url={invite.team.avatar_url} />
          <p className="eyebrow">{invite.inviter_name.toUpperCase()} ЗОВЁТ ТЕБЯ</p>
          <h2>{invite.team.name}</h2>
          <p>
            #{invite.team.rank} · {formatGram(invite.team.flow_nano, 2)} GRAM за неделю
          </p>
          <button className="primary-button" onClick={onAcceptInvite} disabled={busy}>
            ВСТУПИТЬ В КОМАНДУ
          </button>
        </section>
      )}

      {myTeam ? (
        <section className="my-team-card" onClick={() => onOpen(myTeam)}>
          <div className="my-team-head">
            <TeamAvatar mark={myTeam.mark} url={myTeam.avatar_url} />
            <div>
              <span className="eyebrow">ТВОЯ КОМАНДА</span>
              <h2>{myTeam.name}</h2>
              <p>#{myTeam.tag}</p>
            </div>
            <strong>#{myTeam.rank}</strong>
          </div>
          <div className="my-team-score">
            <strong>{formatGram(myTeam.flow_nano, 2)}</strong>
            <span>GRAM ЗА НЕДЕЛЮ</span>
          </div>
          <div className="my-team-chase">
            <span>{seasonLeft(overview.season.ends_at)}</span>
            <span>
              {rival
                ? `${formatGram(Math.max(0, rival.flow_nano - myTeam.flow_nano), 2)} ДО #${rival.rank}`
                : 'ВЫ ВЕДЁТЕ'}
            </span>
          </div>
          <div className="my-team-progress" aria-hidden="true">
            <span
              style={{
                width: `${Math.min(100, rival ? (myTeam.flow_nano / rival.flow_nano) * 100 : 100)}%`,
              }}
            />
          </div>
          <div className="my-team-actions" onClick={(event) => event.stopPropagation()}>
            <button className="primary-button" onClick={onShare} disabled={busy}>
              <PaperPlaneTilt aria-hidden="true" /> ПРИГЛАСИТЬ
            </button>
          </div>
        </section>
      ) : (
        <section className="team-empty-state">
          <span className="team-orbit" aria-hidden="true">
            <i />
            <i />
            <i />
          </span>
          <p className="eyebrow">КОМАНДНЫЙ ЗАЧЁТ</p>
          <h2>
            Одного видно.
            <br />
            Команду замечают.
          </h2>
          <p>Собирайтесь вместе и двигайтесь вверх каждую неделю.</p>
          <div>
            <button className="primary-button" onClick={onSearch}>
              <UsersThree aria-hidden="true" /> НАЙТИ КОМАНДУ
            </button>
            <button className="secondary-button" onClick={onCreate}>
              <Plus aria-hidden="true" /> СОЗДАТЬ СВОЮ
            </button>
          </div>
        </section>
      )}

      <div className="section-label team-section-label">
        <span>КОМАНДЫ СЕЙЧАС</span>
        <small>{overview.season.name}</small>
      </div>
      <TeamList entries={overview.leaderboard} onOpen={onOpen} />
      {!myTeam && (
        <button className="team-search-more" onClick={onSearch}>
          ПОКАЗАТЬ ВСЕ <MagnifyingGlass aria-hidden="true" />
        </button>
      )}
    </>
  );
}

function TeamList({
  entries,
  onOpen,
}: {
  entries: TeamEntry[];
  onOpen: (team: TeamEntry) => void;
}) {
  if (!entries.length) {
    return <p className="team-list-empty">Пока тихо. Первая команда сразу станет первой.</p>;
  }
  return (
    <div className="team-list">
      {entries.map((team) => (
        <button
          key={team.id}
          className={team.is_mine ? 'is-mine' : ''}
          onClick={() => onOpen(team)}
        >
          <b>{team.rank}</b>
          <TeamAvatar mark={team.mark} url={team.avatar_url} compact />
          <span>
            <strong>{team.name}</strong>
            <small>
              {team.member_count} человек · {team.active_members} в зачёте
            </small>
          </span>
          <em>{formatGram(team.flow_nano, 2)}</em>
        </button>
      ))}
    </div>
  );
}

function CreateTeam({
  busy,
  onCreate,
}: {
  busy: boolean;
  onCreate: (input: {
    name: string;
    tag: string;
    join_policy: 'open' | 'request' | 'invite';
  }) => void;
}) {
  const [name, setName] = useState('');
  const [tag, setTag] = useState('');
  const [policy, setPolicy] = useState<'open' | 'request' | 'invite'>('open');
  return (
    <div className="team-subpage team-create">
      <SubpageHeader title="НОВАЯ КОМАНДА" />
      <p className="team-create-intro">Имя останется. Неделя начнётся заново.</p>
      <form
        onSubmit={(event) => {
          event.preventDefault();
          onCreate({ name, tag, join_policy: policy });
        }}
      >
        <label>
          <span>НАЗВАНИЕ</span>
          <input
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder="VOID"
            minLength={3}
            maxLength={32}
            required
          />
        </label>
        <label>
          <span>КОРОТКИЙ ТЕГ</span>
          <input
            value={tag}
            onChange={(event) => setTag(event.target.value.toUpperCase())}
            placeholder="VOID"
            minLength={2}
            maxLength={8}
            required
          />
        </label>
        <label>
          <span>КТО МОЖЕТ ВСТУПИТЬ</span>
          <span className="team-select">
            <select
              value={policy}
              onChange={(event) => setPolicy(event.target.value as typeof policy)}
            >
              <option value="open">Свободно</option>
              <option value="request">По заявке</option>
              <option value="invite">По приглашению</option>
            </select>
            <CaretDown aria-hidden="true" />
          </span>
        </label>
        <p>Количество участников не ограничено. Один человек может быть только в одной команде.</p>
        <button className="primary-button" type="submit" disabled={busy}>
          СОЗДАТЬ КОМАНДУ
        </button>
      </form>
    </div>
  );
}

function TeamDetailPanel({
  detail,
  leaderboard,
  seasonEndsAt,
  members,
  busy,
  onRefresh,
  onJoin,
  onLeave,
  onShare,
  onLoadMore,
  onError,
}: {
  detail: TeamDetail;
  leaderboard: TeamEntry[];
  seasonEndsAt: string;
  members: TeamMember[];
  busy: boolean;
  onRefresh: () => void;
  onJoin: () => void;
  onLeave: () => void;
  onShare: () => void;
  onLoadMore: () => void;
  onError: (message: string) => void;
}) {
  const rival = leaderboard.find((team) => team.rank === detail.rank - 1);
  const canManage = detail.my_role === 'owner' || detail.my_role === 'admin';
  const activityLabels = {
    bank_entry: 'вошёл в BANK',
    bank_payout: 'завершил цикл',
    duel_settlement: 'завершил DUEL',
  } as const;
  return (
    <div className="team-subpage team-detail">
      <section className="team-detail-hero">
        <TeamAvatar mark={detail.mark} url={detail.avatar_url} />
        <p className="eyebrow">КОМАНДА · #{detail.rank}</p>
        <h2>{detail.name}</h2>
        <p>{detail.description || policyLabels[detail.join_policy]}</p>
        <strong>{formatGram(detail.flow_nano, 2)}</strong>
        <span>GRAM ЗА НЕДЕЛЮ</span>
        <div className="team-detail-chase">
          <span>{seasonLeft(seasonEndsAt)}</span>
          <span>
            {rival
              ? `${formatGram(Math.max(0, rival.flow_nano - detail.flow_nano), 2)} ДО #${rival.rank}`
              : 'ЛИДЕР ЗАЧЁТА'}
          </span>
        </div>
      </section>

      <div className="team-detail-actions">
        {detail.my_role ? (
          <button className="primary-button" onClick={onShare} disabled={busy}>
            <PaperPlaneTilt aria-hidden="true" /> ПРИГЛАСИТЬ
          </button>
        ) : detail.my_join_state === 'pending' ? (
          <button className="primary-button" disabled>
            <Check aria-hidden="true" /> ЗАЯВКА ОТПРАВЛЕНА
          </button>
        ) : detail.join_policy === 'invite' ? (
          <button className="primary-button" disabled>
            <LockSimple aria-hidden="true" /> НУЖНО ПРИГЛАШЕНИЕ
          </button>
        ) : (
          <button className="primary-button" onClick={onJoin} disabled={busy}>
            <UserPlus aria-hidden="true" />
            {detail.join_policy === 'request' ? 'ОТПРАВИТЬ ЗАЯВКУ' : 'ВСТУПИТЬ'}
          </button>
        )}
      </div>

      <div className="team-detail-metrics">
        <div>
          <strong>{detail.member_count}</strong>
          <span>В КОМАНДЕ</span>
        </div>
        <div>
          <strong>{detail.active_members}</strong>
          <span>В ЗАЧЁТЕ</span>
        </div>
        <div>
          <strong>{detail.bank_payouts}</strong>
          <span>ЦИКЛОВ</span>
        </div>
      </div>

      <div className="section-label team-section-label">
        <span>ВКЛАД УЧАСТНИКОВ</span>
        {detail.my_role && <small>ТЫ · {formatGram(detail.my_flow_nano, 2)}</small>}
      </div>
      <div className="team-members">
        {members.map((member, index) => (
          <MemberRow
            key={member.user_id}
            member={member}
            rank={index + 1}
            managerRole={detail.my_role}
            teamSlug={detail.slug}
            busy={busy}
            onDone={onRefresh}
            onError={onError}
          />
        ))}
      </div>
      {members.length < detail.member_count && (
        <button className="team-load-more" onClick={onLoadMore} disabled={busy}>
          ПОКАЗАТЬ ЕЩЁ · {detail.member_count - members.length}
        </button>
      )}

      {detail.recent_activity.length > 0 && (
        <>
          <div className="section-label team-section-label">
            <span>ДВИЖЕНИЕ</span>
          </div>
          <div className="team-activity">
            {detail.recent_activity.map((event) => (
              <div key={event.id}>
                <span />
                <p>
                  <strong>{event.username ? `@${event.username}` : event.first_name}</strong>{' '}
                  {activityLabels[event.kind]}
                </p>
                <b>{event.amount_nano > 0 ? `+${formatGram(event.amount_nano, 2)}` : '✓'}</b>
              </div>
            ))}
          </div>
        </>
      )}

      {canManage && (
        <TeamManagement detail={detail} busy={busy} onRefresh={onRefresh} onError={onError} />
      )}
      {detail.my_role && detail.my_role !== 'owner' && (
        <button className="team-danger-action" onClick={onLeave} disabled={busy}>
          ПОКИНУТЬ КОМАНДУ
        </button>
      )}
    </div>
  );
}

function MemberRow({
  member,
  rank,
  managerRole,
  teamSlug,
  busy,
  onDone,
  onError,
}: {
  member: TeamMember;
  rank: number;
  managerRole: TeamDetail['my_role'];
  teamSlug: string;
  busy: boolean;
  onDone: () => void;
  onError: (message: string) => void;
}) {
  const canEdit =
    !member.is_me &&
    member.role !== 'owner' &&
    (managerRole === 'owner' || (managerRole === 'admin' && member.role === 'member'));
  const act = async (action: () => Promise<void>) => {
    try {
      await action();
      onDone();
    } catch (error) {
      onError(message(error));
    }
  };
  return (
    <div className={member.is_me ? 'is-me' : ''}>
      <b>{rank}</b>
      <span className="team-member-avatar">{member.first_name.slice(0, 1).toUpperCase()}</span>
      <p>
        <strong>{member.is_me ? 'ТЫ' : member.first_name}</strong>
        <small>
          {member.role === 'owner'
            ? 'ВЛАДЕЛЕЦ'
            : member.role === 'admin'
              ? 'УПРАВЛЯЮЩИЙ'
              : 'УЧАСТНИК'}
        </small>
      </p>
      <em>{formatGram(member.flow_nano, 2)}</em>
      {canEdit && (
        <details className="team-member-menu">
          <summary>
            <GearSix aria-hidden="true" />
          </summary>
          <div>
            {managerRole === 'owner' && (
              <button
                disabled={busy}
                onClick={() =>
                  void act(() =>
                    api.updateTeamMember(
                      teamSlug,
                      member.user_id,
                      member.role === 'admin' ? 'member' : 'admin',
                    ),
                  )
                }
              >
                {member.role === 'admin' ? 'Снять роль' : 'Сделать управляющим'}
              </button>
            )}
            {managerRole === 'owner' && (
              <button
                disabled={busy}
                onClick={() => {
                  if (
                    window.confirm(
                      `Передать команду ${member.first_name}? Вернуть владение сможет только новый владелец.`,
                    )
                  ) {
                    void act(() => api.transferTeam(teamSlug, member.user_id));
                  }
                }}
              >
                Передать команду
              </button>
            )}
            <button
              disabled={busy}
              onClick={() => {
                if (window.confirm(`Удалить ${member.first_name} из команды?`)) {
                  void act(() => api.removeTeamMember(teamSlug, member.user_id));
                }
              }}
            >
              Удалить из команды
            </button>
          </div>
        </details>
      )}
    </div>
  );
}

function TeamManagement({
  detail,
  busy,
  onRefresh,
  onError,
}: {
  detail: TeamDetail;
  busy: boolean;
  onRefresh: () => void;
  onError: (message: string) => void;
}) {
  const [policy, setPolicy] = useState(detail.join_policy);
  const [name, setName] = useState(detail.name);
  const [description, setDescription] = useState(detail.description);
  const [mark, setMark] = useState(detail.mark % 6);
  const [avatarFile, setAvatarFile] = useState<File | null>(null);
  const [avatarRemoved, setAvatarRemoved] = useState(false);
  const [saving, setSaving] = useState(false);
  const avatarPreview = useMemo(
    () => (avatarFile ? URL.createObjectURL(avatarFile) : null),
    [avatarFile],
  );
  useEffect(() => {
    if (!avatarPreview) return;
    return () => URL.revokeObjectURL(avatarPreview);
  }, [avatarPreview]);
  const savePolicy = async (value: TeamDetail['join_policy']) => {
    setPolicy(value);
    try {
      await api.updateTeam(detail.slug, { join_policy: value });
      onRefresh();
    } catch (error) {
      setPolicy(detail.join_policy);
      onError(message(error));
    }
  };
  const saveBrand = async () => {
    setSaving(true);
    try {
      await api.updateTeam(detail.slug, { name, description, mark });
      if (avatarFile) {
        await api.updateTeamAvatar(detail.slug, avatarFile);
      } else if (avatarRemoved) {
        await api.deleteTeamAvatar(detail.slug);
      }
      setAvatarFile(null);
      setAvatarRemoved(false);
      onRefresh();
    } catch (error) {
      onError(message(error));
    } finally {
      setSaving(false);
    }
  };
  return (
    <details className="team-management">
      <summary>
        <span>
          <GearSix aria-hidden="true" /> УПРАВЛЕНИЕ
        </span>
        <CaretDown aria-hidden="true" />
      </summary>
      {detail.my_role === 'owner' && (
        <div className="team-brand-settings">
          <div className="team-avatar-setting">
            <span>ИЗОБРАЖЕНИЕ</span>
            <label className="team-avatar-upload">
              <TeamAvatar
                mark={mark}
                url={avatarRemoved ? null : (avatarPreview ?? detail.avatar_url)}
              />
              <span>
                <strong>{detail.avatar_url || avatarFile ? 'ЗАМЕНИТЬ' : 'ЗАГРУЗИТЬ'}</strong>
                <small>JPG, PNG или WebP · до 5 МБ</small>
              </span>
              <input
                type="file"
                accept="image/jpeg,image/png,image/webp"
                onChange={(event) => {
                  const file = event.currentTarget.files?.[0] ?? null;
                  event.currentTarget.value = '';
                  if (!file) return;
                  if (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type)) {
                    onError('Поддерживаются JPG, PNG и WebP');
                    return;
                  }
                  if (file.size > 5 * 1024 * 1024) {
                    onError('Файл больше 5 МБ');
                    return;
                  }
                  setAvatarFile(file);
                  setAvatarRemoved(false);
                }}
              />
            </label>
            {(detail.avatar_url || avatarFile) && !avatarRemoved && (
              <button
                className="team-avatar-remove"
                type="button"
                onClick={() => {
                  setAvatarFile(null);
                  setAvatarRemoved(true);
                }}
              >
                УБРАТЬ ИЗОБРАЖЕНИЕ
              </button>
            )}
          </div>
          <label>
            <span>НАЗВАНИЕ</span>
            <input
              value={name}
              onChange={(event) => setName(event.target.value)}
              minLength={3}
              maxLength={32}
            />
          </label>
          <label>
            <span>ОПИСАНИЕ</span>
            <textarea
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              maxLength={160}
              placeholder="Коротко: кто вы и за чем идёте"
            />
            <small>{description.length}/160</small>
          </label>
          <div>
            <span>ЗНАК БЕЗ ИЗОБРАЖЕНИЯ</span>
            <div className="team-mark-picker">
              {Array.from({ length: 6 }, (_, choice) => (
                <button
                  key={choice}
                  type="button"
                  className={mark === choice ? 'active' : ''}
                  onClick={() => setMark(choice)}
                  aria-label={`Эмблема ${choice + 1}`}
                >
                  <TeamMark mark={choice} compact />
                </button>
              ))}
            </div>
          </div>
          <button
            className="secondary-button"
            type="button"
            disabled={busy || saving || name.trim().length < 3}
            onClick={() => void saveBrand()}
          >
            СОХРАНИТЬ ВИД КОМАНДЫ
          </button>
        </div>
      )}
      <label>
        <span>ВСТУПЛЕНИЕ</span>
        <span className="team-select">
          <select
            value={policy}
            onChange={(event) => void savePolicy(event.target.value as typeof policy)}
          >
            <option value="open">Свободное</option>
            <option value="request">По заявке</option>
            <option value="invite">По приглашению</option>
          </select>
          <CaretDown aria-hidden="true" />
        </span>
      </label>
      {detail.my_role === 'owner' && (
        <p className="team-role-hint">
          Роли участников меняются через кнопку настроек рядом с их именем.
        </p>
      )}
      {detail.pending_requests.length > 0 && (
        <div className="team-requests">
          <p>ЗАЯВКИ · {detail.pending_requests.length}</p>
          {detail.pending_requests.map((request) => (
            <div key={request.id}>
              <span>{request.first_name.slice(0, 1).toUpperCase()}</span>
              <strong>{request.username ? `@${request.username}` : request.first_name}</strong>
              <button
                disabled={busy}
                aria-label="Принять"
                onClick={() => {
                  void (async () => {
                    try {
                      await api.decideTeamRequest(detail.slug, request.id, true);
                      onRefresh();
                    } catch (error) {
                      onError(message(error));
                    }
                  })();
                }}
              >
                <Check aria-hidden="true" />
              </button>
              <button
                disabled={busy}
                aria-label="Отклонить"
                onClick={() => {
                  void (async () => {
                    try {
                      await api.decideTeamRequest(detail.slug, request.id, false);
                      onRefresh();
                    } catch (error) {
                      onError(message(error));
                    }
                  })();
                }}
              >
                <X aria-hidden="true" />
              </button>
            </div>
          ))}
        </div>
      )}
    </details>
  );
}

function SubpageHeader({ title }: { title: string }) {
  return (
    <header className="team-subpage-header">
      <strong>{title}</strong>
    </header>
  );
}
