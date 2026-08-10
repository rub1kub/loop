import { useIsConnectionRestored, useTonConnectUI, useTonWallet } from '@tonconnect/ui-react';
import { AnimatePresence, motion } from 'motion/react';
import { useCallback, useEffect, useRef, useState } from 'react';

import { api } from './api';
import { InlineDuelPreview } from './components/InlineDuelPreview';
import { humanError } from './errors';
import { Loader } from './components/Loader';
import { PrelaunchScreen } from './components/PrelaunchScreen';
import { Onboarding } from './components/Onboarding';
import { ProfileScreen } from './components/ProfileScreen';
import { Announcement } from './components/Announcement';
import { Celebration } from './components/Celebration';
import { TabBar } from './components/TabBar';
import { BankScreen } from './features/bank/BankScreen';
import { DuelScreen } from './features/duel/DuelScreen';
import { RatingScreen } from './features/rating/RatingScreen';
import { ResultSheet } from './features/results/ResultSheet';
import { installInteractionGuards } from './interactionGuards';
import {
  haptic,
  initializeTelegram,
  isMockTelegram,
  loadTelegramSdk,
  removeDuelSecret,
  toggleFullscreen,
} from './telegram';
import { useLoopStore } from './store';
import { installViewportBehavior } from './viewport';

import { sameWalletConnection, WALLET_MISMATCH_MESSAGE } from './address';

export default function App() {
  const state = useLoopStore();
  const wallet = useTonWallet();
  const connectionRestored = useIsConnectionRestored();
  const [tonConnectUI] = useTonConnectUI();
  const [proofEpoch, setProofEpoch] = useState(0);
  const profileUserId = state.profile?.user.id ?? null;
  const verificationInFlight = useRef<string | null>(null);
  const staleSessionHandled = useRef<string | null>(null);
  const bootstrap = useCallback(() => useLoopStore.getState().bootstrap(), []);
  const setError = useCallback(
    (message: string | null) => useLoopStore.getState().setError(message),
    [],
  );
  const refresh = useCallback(() => useLoopStore.getState().refresh(), []);
  const refreshRating = useCallback(() => useLoopStore.getState().refreshRating(), []);

  useEffect(() => {
    const cleanupInteractionGuards = installInteractionGuards();
    const cleanupViewport = installViewportBehavior();
    const telegramReady = initializeTelegram();
    void loadTelegramSdk().then(() => {
      if (!telegramReady) initializeTelegram();
      window.dispatchEvent(new Event('resize'));
      return bootstrap();
    });
    const onKey = (event: KeyboardEvent) => {
      if (event.key.toLowerCase() === 'f') toggleFullscreen();
    };
    window.addEventListener('keydown', onKey);
    return () => {
      cleanupInteractionGuards();
      cleanupViewport();
      window.removeEventListener('keydown', onKey);
    };
  }, [bootstrap]);

  // The challenge the wallet signs lives five minutes on the server. It used to
  // be fetched once per page load and never again, so anyone who looked around
  // first and pressed connect later signed something already expired — and no
  // retry could help, because the page never asked for another one. Only
  // restarting the mini app did. Keep it fresh instead: renew before it lapses,
  // and immediately after a verification fails.
  useEffect(() => {
    if (state.loading || !profileUserId || isMockTelegram()) return;
    let alive = true;
    let renewal = 0;
    let first = true;
    const arm = () => {
      // Only the first fetch may hold the connect dialog: putting it back into
      // `loading` while somebody is midway through connecting would interrupt
      // them, and a renewal has nothing to interrupt for.
      if (first) tonConnectUI.setConnectRequestParameters({ state: 'loading' });
      first = false;
      void api
        .walletChallenge()
        .then(({ payload, expires_at }) => {
          if (!alive) return;
          tonConnectUI.setConnectRequestParameters({
            state: 'ready',
            value: { tonProof: payload },
          });
          // Well before the edge, and never a busy loop: an absent or unparsable
          // expiry must not become setTimeout(0) and hammer the server.
          const remaining = new Date(expires_at).getTime() - Date.now();
          const delay = Number.isFinite(remaining) ? remaining * 0.6 : 180_000;
          renewal = window.setTimeout(arm, Math.min(Math.max(delay, 30_000), 600_000));
        })
        .catch((error: unknown) => {
          if (!alive) return;
          setError(humanError(error, 'Не удалось подготовить подключение кошелька') ?? '');
          renewal = window.setTimeout(arm, 30_000);
        });
    };
    arm();
    return () => {
      alive = false;
      window.clearTimeout(renewal);
    };
  }, [profileUserId, proofEpoch, setError, state.loading, tonConnectUI]);

  useEffect(() => {
    if (
      !connectionRestored ||
      state.loading ||
      !state.profile ||
      !wallet ||
      isMockTelegram() ||
      sameWalletConnection(state.profile.wallet, wallet.account)
    ) {
      return;
    }
    const sessionKey = `${wallet.account.chain}:${wallet.account.address}`;
    const proof = wallet.connectItems?.tonProof;
    if (!proof || !('proof' in proof) || !wallet.account.publicKey) {
      // TON Connect restores its session from this browser's localStorage.
      // A restored session has no fresh ton_proof and may point at a wallet
      // that used to belong to this profile. It must never reach a money flow.
      if (staleSessionHandled.current === sessionKey) return;
      staleSessionHandled.current = sessionKey;
      setError(WALLET_MISMATCH_MESSAGE);
      void tonConnectUI.disconnect().catch(() => undefined);
      return;
    }
    if (verificationInFlight.current === sessionKey) return;
    verificationInFlight.current = sessionKey;
    void api
      .verifyWallet({
        address: wallet.account.address,
        network: Number(wallet.account.chain),
        publicKey: wallet.account.publicKey,
        proof: proof.proof,
      })
      .then(() => refresh())
      .catch(async (error: unknown) => {
        setError(humanError(error, 'Не удалось подтвердить кошелёк'));
        // Whatever went wrong, the challenge has been spent. Without a new one
        // the next attempt fails the same way, and the person is stuck until
        // they restart the app.
        setProofEpoch((epoch) => epoch + 1);
        await tonConnectUI.disconnect().catch(() => undefined);
      })
      .finally(() => {
        if (verificationInFlight.current === sessionKey) verificationInFlight.current = null;
      });
  }, [connectionRestored, refresh, setError, state.loading, state.profile, tonConnectUI, wallet]);

  useEffect(() => {
    const bankActive =
      state.bankPosition &&
      ['pending_confirmation', 'queued', 'partially_funded', 'completed'].includes(
        state.bankPosition.current_status,
      );
    const duelActive = state.offers.some((offer) =>
      ['pending_funding', 'open', 'reserved', 'matched'].includes(offer.state),
    );
    // Watching the jar is itself a reason to keep it current: the fill moves
    // when other people deposit, not only when this user does. Something of
    // one's own in flight is polled faster than a screen merely being looked
    // at, and nothing is polled while the app is in the background.
    const watchingBank = state.activeTab === 'bank';
    if (!bankActive && !duelActive && !watchingBank) return;
    const period = bankActive || duelActive ? 5000 : 12_000;
    const tick = () => {
      if (document.visibilityState === 'hidden') return;
      void refresh().catch((error: unknown) => {
        setError(humanError(error, 'Не удалось обновить данные'));
      });
    };
    const timer = window.setInterval(tick, period);
    document.addEventListener('visibilitychange', tick);
    return () => {
      window.clearInterval(timer);
      document.removeEventListener('visibilitychange', tick);
    };
  }, [refresh, setError, state.activeTab, state.bankPosition, state.offers]);

  // A toast that only clears on tap sits there forever when the error keeps
  // being re-raised, which reads as the app being stuck rather than as one
  // failed action.
  useEffect(() => {
    if (!state.error) return;
    const timer = window.setTimeout(() => setError(null), 6000);
    return () => window.clearTimeout(timer);
  }, [setError, state.error]);

  useEffect(() => {
    if (state.activeTab !== 'rating' || isMockTelegram()) return;
    void refreshRating();
    const timer = window.setInterval(() => void refreshRating(), 20_000);
    return () => window.clearInterval(timer);
  }, [refreshRating, state.activeTab]);

  useEffect(() => {
    for (const duel of state.duels) {
      if (['settled', 'refunded', 'expired'].includes(duel.state)) {
        void removeDuelSecret(duel.offer_id).catch(() => undefined);
      }
    }
  }, [state.duels]);

  const documentationScreen = isMockTelegram()
    ? new URLSearchParams(window.location.search).get('screen')
    : null;
  if (documentationScreen === 'loader') return <Loader />;
  if (documentationScreen === 'inline') return <InlineDuelPreview />;

  if (state.loading) return <Loader />;

  if (state.profile && !state.profile.app_open && state.prelaunch) {
    return <PrelaunchScreen prelaunch={state.prelaunch} />;
  }

  if (state.error && !state.profile) {
    return (
      <main className="fatal-screen">
        <img className="fatal-mark" src="/assets/loop-loader.webp" alt="" />
        <h1>LOOP недоступен</h1>
        <p>{state.error}</p>
        <button className="primary-button" onClick={() => window.location.reload()}>
          ПОВТОРИТЬ
        </button>
      </main>
    );
  }

  if (!state.profile) return null;
  if (state.showOnboarding)
    return (
      <Onboarding initialPage={state.onboardingPage} onDone={() => void state.finishOnboarding()} />
    );

  const screen = {
    bank: (
      <BankScreen
        profile={state.profile}
        position={state.bankPosition}
        queuePulse={state.bankPulse}
        pulse={state.rating?.pulse ?? null}
        onRefresh={() => state.refresh()}
        onMockCreated={(position) => state.setMockBankPosition(position)}
      />
    ),
    duel: (
      <DuelScreen
        profile={state.profile}
        offers={state.offers}
        duels={state.duels}
        invite={state.invite}
        challengeOfferId={state.challengeOfferId}
        onDeclineInvite={() => state.declineInvite()}
        onRefresh={() => state.refresh()}
      />
    ),
    rating: <RatingScreen rating={state.rating} />,
    profile: (
      <ProfileScreen
        profile={state.profile}
        rating={state.rating}
        bankHistory={state.bankHistory}
        duels={state.duels}
        onReplay={() => state.replayOnboarding()}
        onResultNotificationsChange={async (enabled) => {
          try {
            await state.setResultNotificationsEnabled(enabled);
          } catch (error) {
            state.setError(humanError(error, 'Не удалось изменить настройку') ?? '');
          }
        }}
      />
    ),
  }[state.activeTab];

  return (
    <main className="app-shell">
      {state.profile?.announcement && <Announcement data={state.profile.announcement} />}
      <AnimatePresence mode="wait">
        <motion.div
          key={state.activeTab}
          className="screen-stage"
          initial={{ opacity: 0, x: 8, scale: 0.995 }}
          animate={{ opacity: 1, x: 0, scale: 1 }}
          exit={{ opacity: 0, x: -5, scale: 0.995 }}
          transition={{ duration: 0.24, ease: [0.22, 1, 0.36, 1] }}
        >
          {screen}
        </motion.div>
      </AnimatePresence>

      <Celebration />
      <TabBar
        active={state.activeTab}
        onChange={(tab) => {
          haptic('selection');
          state.setTab(tab);
        }}
      />

      <AnimatePresence>
        {state.results.find((card) => card.seen_at === null) && (
          <ResultSheet
            key={state.results.find((card) => card.seen_at === null)!.id}
            card={state.results.find((card) => card.seen_at === null)!}
            onClose={async () => {
              const active = state.results.find((card) => card.seen_at === null);
              if (!active) return;
              // Closed is closed. The dismissal is stored locally and the call
              // retries on its own, so a failed request is ours to worry about.
              await state.markResultSeen(active.id).catch(() => undefined);
            }}
            onError={(message) => state.setError(message)}
          />
        )}
      </AnimatePresence>

      <AnimatePresence>
        {state.error && (
          <motion.button
            className="toast"
            initial={{ opacity: 0, y: 30 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 20 }}
            onClick={() => state.setError(null)}
          >
            {state.error}
          </motion.button>
        )}
      </AnimatePresence>
    </main>
  );
}
