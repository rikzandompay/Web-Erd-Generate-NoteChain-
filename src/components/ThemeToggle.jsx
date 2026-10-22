// frontend/src/components/ThemeToggle.jsx
import React, { useEffect, useState } from 'react';

const darkQuery = () => window.matchMedia('(prefers-color-scheme: dark)');

function currentTheme() {
  return document.documentElement.dataset.theme || (darkQuery().matches ? 'dark' : 'light');
}

// Switch between light and dark. Until the visitor flips it, the page follows the device.
export default function ThemeToggle() {
  const [dark, setDark] = useState(() => currentTheme() === 'dark');

  useEffect(() => {
    const query = darkQuery();
    const follow = () => {
      if (!document.documentElement.dataset.theme) setDark(query.matches);
    };
    query.addEventListener('change', follow);
    return () => query.removeEventListener('change', follow);
  }, []);

  const toggle = () => {
    const next = dark ? 'light' : 'dark';
    document.documentElement.dataset.theme = next;
    try {
      localStorage.setItem('theme', next);
    } catch {
      // Storage blocked (private window): the choice lasts for this visit only
    }
    setDark(!dark);
  };

  return (
    <button
      type="button"
      role="switch"
      aria-checked={dark}
      onClick={toggle}
      className="flex shrink-0 items-center gap-3 min-h-[44px] px-3 rounded-md text-sm text-ink whitespace-nowrap hover:bg-panel"
    >
      <span>Mode gelap</span>
      <span aria-hidden="true" className={`flex w-9 h-5 p-0.5 rounded-full border border-edge ${dark ? 'justify-end' : 'justify-start'}`}>
        <span className={`w-3.5 h-3.5 rounded-full ${dark ? 'bg-accent' : 'bg-edge'}`} />
      </span>
    </button>
  );
}
