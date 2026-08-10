import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import type { TeamOverview } from '../../types';
import { TeamsView } from './TeamsView';

const telegram = vi.hoisted(() => ({ backAction: undefined as (() => void) | undefined }));

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
});

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
    const team = {
      id: 'team-1',
      slug: 'dev',
      name: 'dev',
      description: '',
      tag: 'DEV',
      mark: 0,
      avatar_url: null,
      join_policy: 'open' as const,
      member_count: 1,
      active_members: 1,
      flow_nano: 0,
      bank_entries: 0,
      bank_payouts: 0,
      duel_settlements: 0,
      rank: 1,
      is_mine: true,
      my_role: 'owner' as const,
      my_join_state: 'joined' as const,
      my_flow_nano: 0,
      top_members: [],
      recent_activity: [],
      pending_requests: [],
    };
    render(
      <TeamsView
        overview={{ ...overview, my_team: team, leaderboard: [team] }}
        invite={null}
        onRefresh={vi.fn(() => Promise.resolve())}
        onDismissInvite={vi.fn()}
        onError={vi.fn()}
      />,
    );

    const card = screen.getByText('ТВОЯ КОМАНДА').closest('section');
    expect(card).not.toBeNull();
    fireEvent.click(card!);
    await waitFor(() => expect(screen.queryByRole('heading', { name: 'КОМАНДЫ' })).toBeNull());
    expect(screen.getByRole('heading', { name: 'dev' })).toBeInTheDocument();
    fireEvent.click(screen.getByText('УПРАВЛЕНИЕ'));
    expect(screen.queryByText('ЗНАК БЕЗ ИЗОБРАЖЕНИЯ')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Эмблема/ })).not.toBeInTheDocument();
  });
});
