// frontend/src/components/ChatPanel.jsx
import React, { useEffect, useRef, useState } from 'react';
import axios from 'axios';
import { apiErrorMessage } from '../drawio';

const SUGGESTIONS = {
  usecase: 'Buatkan use case diagram untuk sistem peminjaman buku perpustakaan dengan petugas dan anggota',
  sequence: 'Buatkan sequence diagram untuk admin menambah data donatur',
  activity: 'Buatkan activity diagram login admin dengan validasi',
  class: 'Buatkan class diagram untuk donatur dan transaksi keuangan',
};

// Chat that only asks the AI to write diagram text. The answer goes into the
// editor, so the person can edit it by hand or ask for a revision.
export default function ChatPanel({ type, editorText, onGenerated }) {
  // History per diagram type, so each editor keeps the conversation that produced it
  const [histories, setHistories] = useState({});
  const [draft, setDraft] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const logRef = useRef(null);

  const history = histories[type] || [];

  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
  }, [history.length, busy]);

  const send = async (text) => {
    const message = text.trim();
    if (!message || busy) return;
    const asked = [...history, { role: 'user', content: message }];
    setHistories((prev) => ({ ...prev, [type]: asked }));
    setDraft('');
    setError('');
    setBusy(true);
    try {
      const { data } = await axios.post('/api/chat', {
        type,
        messages: asked.map(({ role, content }) => ({ role, content })),
        editor_text: editorText,
      });
      if (data.text) onGenerated(data.text, data.result);
      setHistories((prev) => ({ ...prev, [type]: [...asked, { role: 'assistant', content: data.reply }] }));
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  const onSubmit = (e) => {
    e.preventDefault();
    send(draft);
  };

  const onKeyDown = (e) => {
    // Enter sends, Shift+Enter makes a new line
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      send(draft);
    }
  };

  return (
    <section aria-labelledby="chat-heading" className="mb-5 rounded-md border border-line p-3">
      <h3 id="chat-heading" className="m-0 text-sm font-semibold">Minta AI membuatkan</h3>
      <p className="mt-1 mb-3 text-sm text-muted">
        Ceritakan diagram yang kamu mau. AI menulis teksnya di editor, lalu diagram dibuat otomatis. Minta revisi dengan kalimat biasa.
      </p>

      {history.length > 0 && (
        <ol ref={logRef} aria-label="Percakapan" className="m-0 mb-3 max-h-48 list-none space-y-2 overflow-y-auto p-0">
          {history.map((m, i) => (
            <li
              key={i}
              className={`rounded-md px-3 py-2 text-sm leading-5 ${m.role === 'user' ? 'bg-desk' : 'border border-line'}`}
            >
              <span className="sr-only">{m.role === 'user' ? 'Kamu: ' : 'AI: '}</span>
              {m.content}
            </li>
          ))}
        </ol>
      )}

      <div aria-live="polite">
        {busy && <p className="m-0 mb-3 text-sm text-muted">AI sedang menulis diagram…</p>}
        {error && (
          <p role="alert" className="m-0 mb-3 rounded-md bg-danger-bg px-3 py-2 text-sm text-danger">{error}</p>
        )}
      </div>

      <form onSubmit={onSubmit}>
        <label htmlFor="chat-input" className="sr-only">Permintaan untuk AI</label>
        <textarea
          id="chat-input"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={onKeyDown}
          maxLength={1500}
          rows={2}
          placeholder={SUGGESTIONS[type]}
          className="w-full resize-y rounded-md border border-edge bg-panel px-3 py-2 text-sm leading-5 text-ink"
        />
        <div className="mt-2 flex flex-wrap items-center gap-3">
          <button
            type="submit"
            disabled={!draft.trim() || busy}
            className="min-h-[44px] rounded-md bg-accent px-5 font-semibold text-on-accent hover:bg-accent-hover disabled:cursor-not-allowed disabled:opacity-60"
          >
            Kirim
          </button>
          <span className="text-xs text-muted">Enter untuk kirim, Shift+Enter untuk baris baru</span>
        </div>
      </form>
    </section>
  );
}
