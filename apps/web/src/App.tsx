import { useTonConnectUI, useTonWallet } from '@tonconnect/ui-react';
import { AnimatePresence, motion } from 'motion/react';
import { useCallback, useEffect, useRef } from 'react';

import { api } from './api';
import { InlineDuelPreview } from './components/InlineDuelPreview';
import { Loader } from './components/Loader';
import { Onboarding } from './components/Onboarding';
import { ProfileScreen } from './components/ProfileScreen';
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

import { sameAddress } from './address';

export default function App() {
  const state = useLoopStore();
  const wallet = useTonWallet();
  const [tonConnectUI] = useTonConnectUI();
  const proofConfigured = useRef(false);
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

  useEffect(() => {
    if (state.loading || !state.profile || isMockTelegram() || proofConfigured.current) return;
    proofConfigured.current = true;
    tonConnectUI.setConnectRequestParameters({ state: 'loading' });
    void api
      .walletChallenge()
      .then(({ payload }) => {
        tonConnectUI.setConnectRequestParameters({ state: 'ready', value: { tonProof: payload } });
      })
      .catch((error: unknown) => {
        proofConfigured.current = false;
        setError(
          error instanceof Error ? error.message : 'Не удалось подготовить подключение кошелька',
        );
      });
  }, [setError, state.loading, state.profile, tonConnectUI]);

  useEffect(() => {
    if (
      !wallet ||
      isMockTelegram() ||
      sameAddress(state.profile?.wallet?.address, wallet.account.address)
    )
      return;
    const proof = wallet.connectItems?.tonProof;
    if (!proof || !('proof' in proof) || !wallet.account.publicKey) return;
    void api
      .verifyWallet({
        address: wallet.account.address,
        network: Number(wallet.account.chain),
        publicKey: wallet.account.publicKey,
        proof: proof.proof,
      })
      .then(() => refresh())
      .catch((error: unknown) => {
        setError(error instanceof Error ? error.message : 'Подпись в кошельке отклонена');
        void tonConnectUI.disconnect();
      });
  }, [refresh, setError, state.profile?.wallet?.address, tonConnectUI, wallet]);

  useEffect(() => {
    const bankActive =
      state.bankPosition &&
      ['pending_confirmation', 'queued', 'partially_funded', 'completed'].includes(
        state.bankPosition.current_status,
      );
    const duelActive = state.offers.some((offer) =>
      ['pending_funding', 'open', 'reserved', 'matched'].includes(offer.state),
    );
    if (!bankActive && !duelActive) return;
    const timer = window.setInterval(() => {
      void refresh().catch((error: unknown) => {
        setError(error instanceof Error ? error.message : 'Не удалось обновить дуэль');
      });
    }, 5000);
    return () => window.clearInterval(timer);
  }, [refresh, setError, state.bankPosition, state.offers]);

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

  if (state.error === 'closed_beta' && !state.profile) {
    return (
      <main className="fatal-screen closed-screen">
        <img className="fatal-mark" src="/assets/loop-loader.webp" alt="" />
        <h1>Ещё пилю</h1>
        <p>Приложение закрыто, пока идёт разработка. Открытие скорее всего на выходных.</p>
        <a
          className="closed-source-link"
          href="https://github.com/rub1kub/loop"
          target="_blank"
          rel="noreferrer"
        >
          КОД ОТКРЫТ ЦЕЛИКОМ
        </a>
      </main>
    );
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
            state.setError(
              error instanceof Error ? error.message : 'Не удалось изменить настройку',
            );
          }
        }}
      />
    ),
  }[state.activeTab];

  return (
    <main className="app-shell">
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
              try {
                await state.markResultSeen(active.id);
              } catch {
                state.setError('Результат закрыт. При следующем входе он может появиться снова.');
              }
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
