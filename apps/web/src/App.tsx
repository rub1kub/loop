import { useTonConnectUI, useTonWallet } from '@tonconnect/ui-react';
import { AnimatePresence, motion } from 'motion/react';
import { useCallback, useEffect, useRef } from 'react';

import { api } from './api';
import { BankScreen } from './components/BankScreen';
import { DuelScreen } from './components/DuelScreen';
import { InlineDuelPreview } from './components/InlineDuelPreview';
import { Loader } from './components/Loader';
import { Onboarding } from './components/Onboarding';
import { ProfileScreen } from './components/ProfileScreen';
import { TabBar } from './components/TabBar';
import {
  haptic,
  initializeTelegram,
  isMockTelegram,
  loadTelegramSdk,
  removeDuelSecret,
  toggleFullscreen,
} from './telegram';
import { useLoopStore } from './store';

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

  useEffect(() => {
    initializeTelegram();
    void loadTelegramSdk().then(() => initializeTelegram());
    void bootstrap();
    const onKey = (event: KeyboardEvent) => {
      if (event.key.toLowerCase() === 'f') toggleFullscreen();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
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
        setError(error instanceof Error ? error.message : 'Не удалось создать TON proof');
      });
  }, [setError, state.loading, state.profile, tonConnectUI]);

  useEffect(() => {
    if (!wallet || isMockTelegram() || state.profile?.wallet?.address === wallet.account.address)
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
        setError(error instanceof Error ? error.message : 'TON proof отклонён');
        void tonConnectUI.disconnect();
      });
  }, [refresh, setError, state.profile?.wallet?.address, tonConnectUI, wallet]);

  useEffect(() => {
    if (!state.offers.some((offer) => ['pending_funding', 'open', 'matched'].includes(offer.state)))
      return;
    const timer = window.setInterval(() => {
      void refresh().catch((error: unknown) => {
        setError(error instanceof Error ? error.message : 'Не удалось обновить дуэль');
      });
    }, 5000);
    return () => window.clearInterval(timer);
  }, [refresh, setError, state.offers]);

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
  if (state.showOnboarding) return <Onboarding onDone={() => void state.finishOnboarding()} />;

  const screen = {
    bank: (
      <BankScreen
        profile={state.profile}
        onStart={() => state.startCycle()}
        onContinue={() => state.setTab('duel')}
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
    profile: (
      <ProfileScreen
        profile={state.profile}
        duels={state.duels}
        onReplay={() => state.replayOnboarding()}
      />
    ),
  }[state.activeTab];

  return (
    <main className="app-shell">
      <div className="brand-bar">
        <span className="brand">LOOP</span>
      </div>

      <AnimatePresence mode="wait">
        <motion.div
          key={state.activeTab}
          className="screen-stage"
          initial={{ opacity: 0, x: 12 }}
          animate={{ opacity: 1, x: 0 }}
          exit={{ opacity: 0, x: -8 }}
          transition={{ duration: 0.18, ease: [0.2, 0.8, 0.2, 1] }}
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
