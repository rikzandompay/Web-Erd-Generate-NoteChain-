import React, { useState } from 'react';
import SqlMode from './components/SqlMode';
import Tabs from './components/Tabs';
import ThemeToggle from './components/ThemeToggle';
import UmlTextMode from './components/UmlTextMode';

const MODES = [
  { id: 'sql', label: 'File SQL' },
  { id: 'uml', label: 'Teks UML' },
];

function App() {
  const [mode, setMode] = useState('sql');

  return (
    <div className="min-h-screen flex flex-col">
      <header className="border-b border-line">
        <div className="mx-auto w-full max-w-[1280px] px-4 sm:px-6 py-2 flex items-center justify-between gap-4">
          <h1 className="text-base sm:text-lg font-semibold">
            ERD Generator <span className="font-normal text-muted">by Rikzan</span>
          </h1>
          <ThemeToggle />
        </div>
      </header>

      <main className="flex-1 mx-auto w-full max-w-[1280px] px-4 sm:px-6 py-6">
        <p className="mb-6 max-w-prose text-muted">
          Ubah file SQL atau teks UML menjadi file draw.io yang langsung rapi: ERD notasi Chen, class, sequence, dan activity diagram, satu diagram per halaman.
        </p>

        <Tabs items={MODES} value={mode} onChange={setMode} label="Sumber diagram" idPrefix="mode" />

        {/* Both modes stay mounted so switching keeps the chosen file and the typed text */}
        <div role="tabpanel" id="mode-panel" aria-labelledby={`mode-tab-${mode}`} className="pt-6">
          <div hidden={mode !== 'sql'}>
            <SqlMode />
          </div>
          <div hidden={mode !== 'uml'}>
            <UmlTextMode />
          </div>
        </div>
      </main>

      <footer className="border-t border-line">
        <p className="mx-auto w-full max-w-[1280px] px-4 sm:px-6 py-4 text-sm text-muted">
          Dibuat oleh Rikzan. File dan teks diproses langsung, tidak disimpan di server.
        </p>
      </footer>
    </div>
  );
}

export default App;
