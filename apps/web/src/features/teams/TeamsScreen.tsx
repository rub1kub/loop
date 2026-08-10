import { TeamsView } from './TeamsView';
import type { TeamInvitePreview, TeamOverview } from '../../types';

export function TeamsScreen({
  teams,
  invite,
  onRefresh,
  onDismissInvite,
  onError,
}: {
  teams: TeamOverview | null;
  invite: TeamInvitePreview | null;
  onRefresh: () => Promise<void>;
  onDismissInvite: () => void;
  onError: (message: string) => void;
}) {
  return (
    <section className="screen teams-screen" aria-labelledby="teams-title">
      <header className="mode-header">
        <p className="eyebrow">СЕЗОН · {teams?.season.name ?? 'ОБНОВЛЯЕТСЯ'}</p>
        <h1 id="teams-title">КОМАНДЫ</h1>
      </header>
      <TeamsView
        overview={teams}
        invite={invite}
        onRefresh={onRefresh}
        onDismissInvite={onDismissInvite}
        onError={onError}
      />
    </section>
  );
}
