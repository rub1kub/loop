import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import type { TeamOverview } from '../../types';
import { TeamsView } from './TeamsView';

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
});
