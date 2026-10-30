// frontend/src/account.js
import axios from 'axios';

// Signing in with Google and the browser's copy of the PRD wizard. The session itself is an
// HttpOnly cookie set by the backend (api/auth.py); this page never sees it.

export const DRAFT_KEY = 'erdgen-prd-wizard-v1';

export async function fetchAccount() {
  try {
    const { data } = await axios.get('/api/auth/me');
    return { status: 'done', user: data.user, ready: data.login_ready };
  } catch {
    return { status: 'done', user: null, ready: false };
  }
}

// After Google, the browser comes back to the PRD tab
export const loginHref = () => `/api/auth/google/login?next=${encodeURIComponent('/?tab=prd')}`;

// A draft saved for another account, or for an account that has signed out, is not shown
// to whoever uses this browser now. A draft made before signing in is kept and moved into the account.
export function keepOnlyOwnDraft(account) {
  if (!account.ready) return;
  try {
    const saved = JSON.parse(localStorage.getItem(DRAFT_KEY) || 'null');
    if (saved?.owner && saved.owner !== account.user?.id) localStorage.removeItem(DRAFT_KEY);
  } catch {
    // Storage blocked: nothing kept to clear
  }
}

export function forgetLocalDraft() {
  try {
    localStorage.removeItem(DRAFT_KEY);
  } catch {
    // Storage blocked: nothing kept to clear
  }
}
