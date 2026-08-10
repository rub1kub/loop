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
    <section className="screen teams-screen" aria-label="Команды">
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
