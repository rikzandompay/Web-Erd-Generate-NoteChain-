// frontend/src/components/AccountMenu.jsx
import React, { useEffect, useRef, useState } from 'react';
import axios from 'axios';
import { apiErrorMessage } from '../drawio';
import { forgetLocalDraft, loginHref } from '../account';

// The header's sign-in link, or the signed-in user with "Keluar" and "Hapus akun".
// Signing out also clears this browser's copy of the PRD, so the next person sees nothing.

const ITEM = 'flex w-full min-h-[44px] items-center rounded-md px-3 text-left text-sm hover:bg-desk';

export default function AccountMenu({ account }) {
  const [open, setOpen] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const box = useRef(null);

  useEffect(() => {
    if (!open) return undefined;
    const close = (e) => {
      if (e.type === 'keydown' ? e.key === 'Escape' : !box.current?.contains(e.target)) {
        setOpen(false);
        setConfirming(false);
      }
    };
    document.addEventListener('mousedown', close);
    document.addEventListener('keydown', close);
    return () => {
      document.removeEventListener('mousedown', close);
      document.removeEventListener('keydown', close);
    };
  }, [open]);

  if (account.status !== 'done' || !account.ready) return null;
  if (!account.user) {
    return (
      <a href={loginHref()} className="inline-flex min-h-[44px] items-center px-3 rounded-md border border-edge text-sm font-medium hover:bg-desk">
        Masuk dengan Google
      </a>
    );
  }

  const leave = async (how) => {
    setBusy(true);
    setError('');
    try {
      if (how === 'delete') await axios.delete('/api/account');
      else await axios.post('/api/auth/logout');
      forgetLocalDraft();
      window.location.assign('/');
    } catch (err) {
      setError(apiErrorMessage(err));
      setBusy(false);
    }
  };

  const { user } = account;
  return (
    <div ref={box} className="relative">
      <button type="button" aria-expanded={open} aria-haspopup="true" onClick={() => setOpen((v) => !v)}
        className="inline-flex min-h-[44px] items-center gap-2 px-2 rounded-md text-sm hover:bg-desk">
        {user.picture
          ? <img src={user.picture} alt="" referrerPolicy="no-referrer" className="h-7 w-7 rounded-full" />
          : <span aria-hidden="true" className="flex h-7 w-7 items-center justify-center rounded-full bg-desk font-semibold">{(user.name || user.email)[0].toUpperCase()}</span>}
        <span className="hidden sm:inline max-w-[160px] truncate">{user.name || user.email}</span>
      </button>
      {open && (
        <div className="absolute right-0 z-20 mt-1 w-72 rounded-[10px] border border-line bg-panel p-2 shadow-lg">
          <p className="m-0 px-3 py-2 text-xs text-muted break-all">Masuk sebagai {user.email}</p>
          {!confirming ? (
            <>
              <button type="button" disabled={busy} onClick={() => leave('logout')} className={ITEM}>Keluar</button>
              <button type="button" disabled={busy} onClick={() => setConfirming(true)} className={`${ITEM} text-danger`}>Hapus akun…</button>
            </>
          ) : (
            <div className="px-3 py-2">
              <p className="m-0 text-sm">Hapus akun beserta semua PRD dan versinya? Ini tidak bisa dibatalkan.</p>
              <div className="mt-3 flex flex-wrap gap-2">
                <button type="button" disabled={busy} onClick={() => leave('delete')}
                  className="inline-flex min-h-[44px] items-center px-4 rounded-md border border-danger bg-danger-bg text-sm font-semibold text-danger">
                  {busy ? 'Menghapus…' : 'Hapus permanen'}
                </button>
                <button type="button" disabled={busy} onClick={() => setConfirming(false)}
                  className="inline-flex min-h-[44px] items-center px-3 rounded-md text-sm text-muted hover:bg-desk">Batal</button>
              </div>
            </div>
          )}
          {error && <p role="alert" className="m-0 mt-2 rounded-md bg-danger-bg px-3 py-2 text-sm text-danger">{error}</p>}
        </div>
      )}
    </div>
  );
}
