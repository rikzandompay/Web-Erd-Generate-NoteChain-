import React, { useState } from 'react';
import axios from 'axios';
import { apiErrorMessage } from '../drawio';

export default function AiFixerPanel({ type, text, errors, onApplyFix }) {
  const [status, setStatus] = useState('idle');
  const [result, setResult] = useState(null);
  const [fixError, setFixError] = useState('');

  const handleFix = async () => {
    setStatus('loading');
    setFixError('');
    try {
      const { data } = await axios.post('/api/fix', { type, text, errors });
      setResult(data);
      setStatus('done');
    } catch (err) {
      setFixError(apiErrorMessage(err));
      setStatus('error');
    }
  };

  const handleApply = () => {
    if (result?.fixed_text) {
      onApplyFix(result.fixed_text);
      setStatus('applied');
    }
  };

  if (status === 'idle') {
    return (
      <div className="mt-3 rounded-md border border-accent/30 bg-panel px-4 py-3">
        <p className="text-sm font-semibold">Perbaikan otomatis tersedia</p>
        <p className="mt-1 text-sm text-muted">
          Ada {errors.length} baris bermasalah. Coba perbaiki otomatis berdasarkan aturan sintaks?
        </p>
        <button
          type="button"
          onClick={handleFix}
          className="mt-2 min-h-[44px] px-5 rounded-md bg-accent text-on-accent text-sm font-semibold hover:bg-accent-hover transition-colors"
        >
          Perbaiki otomatis
        </button>
      </div>
    );
  }

  if (status === 'loading') {
    return (
      <div className="mt-3 rounded-md border border-line bg-panel px-4 py-3">
        <p className="text-sm text-muted flex items-center gap-2">
          <span className="inline-block w-4 h-4 border-2 border-accent border-t-transparent rounded-full animate-spin" aria-hidden="true" />
          Menganalisis dan memperbaiki teks…
        </p>
      </div>
    );
  }

  if (status === 'error') {
    return (
      <div className="mt-3 rounded-md border border-danger/30 bg-danger-bg px-4 py-3">
        <p className="text-sm text-danger font-semibold">Gagal memperbaiki</p>
        <p className="mt-1 text-sm text-danger">{fixError}</p>
        <button
          type="button"
          onClick={() => setStatus('idle')}
          className="mt-2 min-h-[44px] px-4 text-sm font-medium rounded-md border border-edge hover:bg-desk"
        >
          Coba lagi
        </button>
      </div>
    );
  }

  if (status === 'applied') {
    return (
      <div className="mt-3 rounded-md border border-accent/30 bg-panel px-4 py-3">
        <p className="text-sm font-semibold text-accent">Perbaikan diterapkan</p>
        <p className="mt-1 text-sm text-muted">Teks di editor sudah diperbarui. Tekan "Buat diagram" untuk melihat hasilnya.</p>
      </div>
    );
  }

  // status === 'done'
  const { changes = [], unfixed = [] } = result || {};
  const hasChanges = changes.length > 0;

  return (
    <div className="mt-3 rounded-md border border-line bg-panel px-4 py-3 space-y-3">
      <p className="text-sm font-semibold">
        Hasil perbaikan: {changes.length} baris diperbaiki{unfixed.length > 0 ? `, ${unfixed.length} tidak bisa diperbaiki otomatis` : ''}
      </p>

      {hasChanges ? (
        <div className="space-y-2">
          <p className="text-xs font-semibold text-muted uppercase tracking-wide">Perubahan yang disarankan</p>
          <ul className="space-y-2 text-sm">
            {changes.map((c, i) => (
              <li key={i} className="rounded-md border border-line p-3 space-y-1">
                <p className="text-xs text-muted">Baris {c.line}: {c.reason}</p>
                <div className="font-mono text-xs leading-relaxed">
                  <div className="text-danger line-through opacity-70">{c.before}</div>
                  <div className="text-accent font-medium">
                    {c.after === '(dihapus)' || !c.after ? (
                      <span className="italic text-muted font-sans">(baris dihapus)</span>
                    ) : (
                      c.after
                    )}
                  </div>
                </div>
              </li>
            ))}
          </ul>
        </div>
      ) : (
        <p className="text-sm text-muted">
          Tidak ada baris yang bisa diperbaiki secara otomatis. Silakan periksa pesan kesalahan dan sesuaikan manual.
        </p>
      )}

      {unfixed.length > 0 && (
        <div className="space-y-2">
          <p className="text-xs font-semibold text-muted uppercase tracking-wide">Perlu diperbaiki manual</p>
          <ul className="space-y-1 text-sm">
            {unfixed.map((u, i) => (
              <li key={i} className="text-muted">
                Baris {u.line}: {u.reason || u.message}
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="flex flex-wrap gap-2 pt-1">
        {hasChanges && (
          <button
            type="button"
            onClick={handleApply}
            className="min-h-[44px] px-5 rounded-md bg-accent text-on-accent text-sm font-semibold hover:bg-accent-hover transition-colors"
          >
            Terapkan perbaikan
          </button>
        )}
        <button
          type="button"
          onClick={() => { setStatus('idle'); setResult(null); }}
          className="min-h-[44px] px-4 text-sm font-medium rounded-md border border-edge hover:bg-desk"
        >
          {hasChanges ? 'Batal' : 'Tutup'}
        </button>
      </div>
    </div>
  );
}
