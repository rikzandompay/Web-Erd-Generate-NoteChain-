import React, { useEffect, useState } from 'react';
import { fetchAccount, keepOnlyOwnDraft } from './account';
import AccountMenu from './components/AccountMenu';
import GuideMode from './components/GuideMode';
import PrdMode from './components/PrdMode';
import SqlMode from './components/SqlMode';
import Tabs from './components/Tabs';
import ThemeToggle from './components/ThemeToggle';
import UmlTextMode from './components/UmlTextMode';
import UserGuideWalkthrough from './components/UserGuideWalkthrough';

const MODES = [
  { id: 'sql', label: 'File SQL' },
  { id: 'uml', label: 'Teks UML' },
  { id: 'prd', label: 'PRD' },
  { id: 'guide', label: 'Panduan' },
];

// Coming back from Google: ?tab=prd opens the PRD tab, ?login_error=… says why signing in failed
function readReturn() {
  const params = new URLSearchParams(window.location.search);
  const tab = params.get('tab');
  return { mode: MODES.some((m) => m.id === tab) ? tab : 'sql', loginError: params.get('login_error') || '' };
}

function App() {
  const [initial] = useState(readReturn);
  const [mode, setMode] = useState(initial.mode);
  const [loginError, setLoginError] = useState(initial.loginError);
  const [showWalkthrough, setShowWalkthrough] = useState(false);
  const [account, setAccount] = useState({ status: 'loading', user: null, ready: false });

  useEffect(() => {
    if (window.location.search) window.history.replaceState(null, '', window.location.pathname);
    let live = true;
    fetchAccount().then((found) => {
      if (!live) return;
      keepOnlyOwnDraft(found);
      setAccount(found);
    });
    return () => { live = false; };
  }, []);

  return (
    <div className="min-h-screen flex flex-col">
      <header className="border-b border-line">
        <div className="mx-auto w-full max-w-[1280px] px-4 sm:px-6 py-2 flex flex-wrap items-center justify-between gap-x-4 gap-y-1">
          <h1 className="text-base sm:text-lg font-semibold">
            ERD Generator <span className="font-normal text-muted">by Rikzan</span>
          </h1>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setShowWalkthrough(true)}
              className="min-h-[44px] px-3 text-sm font-medium text-muted hover:text-ink rounded-md hover:bg-desk transition-colors"
              aria-label="Buka panduan pengguna interaktif"
            >
              Panduan
            </button>
            <ThemeToggle />
            <AccountMenu account={account} />
          </div>
        </div>
      </header>

      <main className="flex-1 mx-auto w-full max-w-[1280px] px-4 sm:px-6 py-6">
        <p className="mb-6 max-w-prose text-muted">
          Ubah file SQL atau teks UML menjadi file draw.io yang langsung rapi: ERD notasi Chen, class, sequence, dan activity diagram, satu diagram per halaman.
        </p>

        {loginError && (
          <div role="alert" className="mb-6 flex flex-wrap items-center justify-between gap-2 rounded-md bg-danger-bg px-3 py-2 text-sm text-danger">
            <span>Gagal masuk: {loginError}</span>
            <button type="button" onClick={() => setLoginError('')} className="min-h-[44px] px-3 rounded-md font-medium hover:underline">Tutup</button>
          </div>
        )}

        <Tabs items={MODES} value={mode} onChange={setMode} label="Sumber diagram" idPrefix="mode" />

        {/* Both modes stay mounted so switching keeps the chosen file and the typed text */}
        <div role="tabpanel" id="mode-panel" aria-labelledby={`mode-tab-${mode}`} className="pt-6">
          <div hidden={mode !== 'sql'}>
            <SqlMode />
          </div>
          <div hidden={mode !== 'uml'}>
            <UmlTextMode />
          </div>
          <div hidden={mode !== 'prd'}>
            {/* Mounted again once it is known who is signed in, so it reads the right draft */}
            <PrdMode key={account.status === 'done' ? account.user?.id || 'guest' : 'loading'} account={account} />
          </div>
          <div hidden={mode !== 'guide'}>
            <GuideMode onOpenMode={setMode} />
          </div>
        </div>
      </main>

      <footer className="border-t border-line">
        <p className="mx-auto w-full max-w-[1280px] px-4 sm:px-6 py-4 text-sm text-muted">
          Dibuat oleh Rikzan. File dan teks diproses langsung tanpa disimpan. Hanya PRD milik akun yang masuk dengan Google yang disimpan, dan bisa dihapus kapan saja.{' '}
          <a href="/privacy.html" className="underline hover:text-ink">Kebijakan privasi</a>
        </p>
      </footer>

      {showWalkthrough && (
        <UserGuideWalkthrough
          onClose={() => setShowWalkthrough(false)}
          onSwitchMode={setMode}
        />
      )}
    </div>
  );
}

export default App;
