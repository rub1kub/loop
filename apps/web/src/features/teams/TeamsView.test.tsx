import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { TeamDetail, TeamEntry, TeamOverview } from '../../types';
import { TeamsView } from './TeamsView';

const telegram = vi.hoisted(() => ({ backAction: undefined as (() => void) | undefined }));
const apiMocks = vi.hoisted(() => ({
  team: vi.fn(),
  updateTeam: vi.fn(),
  updateTeamAvatar: vi.fn(),
  deleteTeamAvatar: vi.fn(),
}));

vi.mock('../../api', () => ({ api: apiMocks }));

vi.mock('../../telegram', () => ({
  haptic: vi.fn(),
  sharePreparedResult: vi.fn(),
  setBackAction: vi.fn((action?: () => void) => {
    telegram.backAction = action;
    return () => {
      if (telegram.backAction === action) telegram.backAction = undefined;
    };
  }),
}));

afterEach(() => {
  cleanup();
  telegram.backAction = undefined;
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

beforeEach(() => vi.clearAllMocks());

const overview: TeamOverview = {
  season: {
    id: 'season-1',
    key: '2026-W32',
    name: '10–16 АВГУСТА',
    starts_at: '2026-08-10T00:00:00Z',
    ends_at: '2026-08-17T00:00:00Z',
    competition: 'bank_flow',
  },
  my_team: null,
  leaderboard: [],
};

const ownedTeam: TeamDetail = {
  id: 'team-1',
  slug: 'dev',
  name: 'DEV',
  description: '',
  tag: 'DEV',
  mark: 0,
  avatar_url: null,
  join_policy: 'open',
  member_count: 1,
  active_members: 1,
  flow_nano: 0,
  bank_entries: 0,
  bank_payouts: 0,
  duel_settlements: 0,
  rank: 1,
  is_mine: true,
  my_role: 'owner',
  my_join_state: 'joined',
  my_flow_nano: 0,
  top_members: [],
  recent_activity: [],
  pending_requests: [],
};

describe('team forms', () => {
  it('waits for a real tap before focusing the create form', async () => {
    render(
      <TeamsView
        overview={overview}
        invite={null}
        onRefresh={vi.fn(() => Promise.resolve())}
        onDismissInvite={vi.fn()}
        onError={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: /СОЗДАТЬ СВОЮ/ }));
    const name = await screen.findByRole('textbox', { name: 'НАЗВАНИЕ' });
    expect(screen.queryByRole('textbox', { name: 'КОРОТКИЙ ТЕГ' })).not.toBeInTheDocument();

    await waitFor(() => expect(name).not.toHaveFocus());
    name.focus();
    expect(name).toHaveFocus();
  });

  it('uses Telegram BackButton instead of rendering a duplicate back control', async () => {
    render(
      <TeamsView
        overview={overview}
        invite={null}
        onRefresh={vi.fn(() => Promise.resolve())}
        onDismissInvite={vi.fn()}
        onError={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: /СОЗДАТЬ СВОЮ/ }));
    await screen.findByText('НОВАЯ КОМАНДА');
    expect(screen.queryByRole('button', { name: 'Назад' })).not.toBeInTheDocument();
    expect(telegram.backAction).toBeTypeOf('function');

    telegram.backAction?.();
    await screen.findByRole('heading', { name: 'КОМАНДЫ' });
  });

  it('does not repeat the teams page title inside a team profile', async () => {
    render(
      <TeamsView
        overview={{ ...overview, my_team: ownedTeam, leaderboard: [ownedTeam] }}
        invite={null}
        onRefresh={vi.fn(() => Promise.resolve())}
        onDismissInvite={vi.fn()}
        onError={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: 'Открыть команду DEV' }));
    await waitFor(() => expect(screen.queryByRole('heading', { name: 'КОМАНДЫ' })).toBeNull());
    expect(screen.getByRole('heading', { name: 'DEV' })).toBeInTheDocument();
    fireEvent.click(screen.getByText('УПРАВЛЕНИЕ'));
    expect(screen.queryByText('ЗНАК БЕЗ ИЗОБРАЖЕНИЯ')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Эмблема/ })).not.toBeInTheDocument();
  });

  it('opens its own leaderboard row without waiting for another network request', async () => {
    render(
      <TeamsView
        overview={{ ...overview, my_team: ownedTeam, leaderboard: [ownedTeam] }}
        invite={null}
        onRefresh={vi.fn(() => Promise.resolve())}
        onDismissInvite={vi.fn()}
        onError={vi.fn()}
      />,
    );

    fireEvent.click(document.querySelector('.team-list button')!);

    expect(await screen.findByRole('heading', { name: 'DEV' })).toBeVisible();
    expect(apiMocks.team).not.toHaveBeenCalled();
  });

  it('names only a real weekly leader as the team that holds BANK', () => {
    const leader = { ...ownedTeam, flow_nano: 5_000_000_000, bank_entries: 3 };
    render(
      <TeamsView
        overview={{ ...overview, my_team: leader, leaderboard: [leader] }}
        invite={null}
        onRefresh={vi.fn(() => Promise.resolve())}
        onDismissInvite={vi.fn()}
        onError={vi.fn()}
      />,
    );

    expect(screen.getAllByText(/ДЕРЖИТ BANK/).length).toBeGreaterThan(0);
  });

  it('shows an immediate transition while another team is loading', async () => {
    let finish!: (team: TeamDetail) => void;
    apiMocks.team.mockReturnValue(
      new Promise<TeamDetail>((resolve) => {
        finish = resolve;
      }),
    );
    const other: TeamEntry = {
      id: 'team-2',
      slug: 'north',
      name: 'NORTH',
      description: '',
      tag: 'NORTH',
      mark: 0,
      avatar_url: null,
      join_policy: 'open',
      member_count: 1,
      active_members: 1,
      flow_nano: 0,
      bank_entries: 0,
      bank_payouts: 0,
      duel_settlements: 0,
      rank: 1,
      is_mine: false,
    };
    render(
      <TeamsView
        overview={{ ...overview, my_team: null, leaderboard: [other] }}
        invite={null}
        onRefresh={vi.fn(() => Promise.resolve())}
        onDismissInvite={vi.fn()}
        onError={vi.fn()}
      />,
    );

    fireEvent.click(document.querySelector('.team-list button')!);
    const loading = await screen.findByText('ОТКРЫВАЕМ КОМАНДУ');
    await waitFor(() => expect(loading).toBeVisible());

    finish({ ...ownedTeam, ...other, top_members: [], recent_activity: [], pending_requests: [] });
    expect(await screen.findByRole('heading', { name: 'NORTH' })).toBeVisible();
  });

  it('uses the saved avatar response immediately instead of reverting to stale overview data', async () => {
    const fresh = {
      ...ownedTeam,
      avatar_url: '/api/v1/team-cards/dev/avatar.jpg?v=fresh',
    };
    apiMocks.updateTeam.mockResolvedValue(ownedTeam);
    apiMocks.updateTeamAvatar.mockResolvedValue(fresh);
    vi.stubGlobal('URL', {
      ...URL,
      createObjectURL: vi.fn(() => 'blob:preview'),
      revokeObjectURL: vi.fn(),
    });
    render(
      <TeamsView
        overview={{ ...overview, my_team: ownedTeam, leaderboard: [ownedTeam] }}
        invite={null}
        onRefresh={vi.fn(() => Promise.resolve())}
        onDismissInvite={vi.fn()}
        onError={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: 'Открыть команду DEV' }));
    fireEvent.click(await screen.findByText('УПРАВЛЕНИЕ'));
    const file = new File(['avatar'], 'avatar.png', { type: 'image/png' });
    fireEvent.change(document.querySelector('.team-avatar-upload input')!, {
      target: { files: [file] },
    });
    fireEvent.click(screen.getByRole('button', { name: 'СОХРАНИТЬ ВИД КОМАНДЫ' }));

    await waitFor(() => expect(apiMocks.updateTeamAvatar).toHaveBeenCalledWith('dev', file));
    await waitFor(() =>
      expect(document.querySelector('.team-detail-hero .team-avatar img')).toHaveAttribute(
        'src',
        fresh.avatar_url,
      ),
    );
  });

  it('retries a versioned avatar after a temporary image failure', async () => {
    vi.useFakeTimers();
    const withAvatar = {
      ...ownedTeam,
      avatar_url: '/api/v1/team-cards/dev/avatar.jpg?v=stable',
    };
    render(
      <TeamsView
        overview={{ ...overview, my_team: withAvatar, leaderboard: [] }}
        invite={null}
        onRefresh={vi.fn(() => Promise.resolve())}
        onDismissInvite={vi.fn()}
        onError={vi.fn()}
      />,
    );
    const image = document.querySelector('.my-team-head .team-avatar img');
    expect(image).toHaveAttribute('src', withAvatar.avatar_url);
    fireEvent.error(image!);
    expect(document.querySelector('.my-team-head .team-avatar img')).toBeNull();

    await act(async () => vi.advanceTimersByTimeAsync(1_500));
    expect(document.querySelector('.my-team-head .team-avatar img')).toHaveAttribute(
      'src',
      `${withAvatar.avatar_url}&retry=1`,
    );
  });

  it('shows member photos and falls back to an initial after a loading error', async () => {
    const memberPhoto = 'https://t.me/i/userpic/320/member.jpg';
    const withMember = {
      ...ownedTeam,
      top_members: [
        {
          user_id: 'member-1',
          first_name: 'Мария',
          username: 'maria',
          photo_url: memberPhoto,
          role: 'member' as const,
          joined_at: '2026-08-10T00:00:00Z',
          flow_nano: 0,
          bank_entries: 0,
          bank_payouts: 0,
          duel_settlements: 0,
          is_me: false,
        },
      ],
    };
    render(
      <TeamsView
        overview={{ ...overview, my_team: withMember, leaderboard: [withMember] }}
        invite={null}
        onRefresh={vi.fn(() => Promise.resolve())}
        onDismissInvite={vi.fn()}
        onError={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: 'Открыть команду DEV' }));
    await screen.findByRole('heading', { name: 'DEV' });
    const avatar = await waitFor(() => {
      const image = document.querySelector('.team-member-avatar img');
      expect(image).not.toBeNull();
      return image;
    });
    expect(avatar).toHaveAttribute('src', memberPhoto);
    expect(avatar).toHaveAttribute('referrerpolicy', 'no-referrer');

    fireEvent.error(avatar!);
    expect(document.querySelector('.team-member-avatar img')).toBeNull();
    expect(document.querySelector('.team-member-avatar')).toHaveTextContent('М');
  });
});
