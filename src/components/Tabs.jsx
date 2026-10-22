// frontend/src/components/Tabs.jsx
import React, { useRef } from 'react';

// A row of page tabs, the product's identity motif: it echoes the page tabs
// of the draw.io files it makes. Arrow keys, Home and End move between tabs
// (WAI-ARIA tabs pattern).
export default function Tabs({ items, value, onChange, label, idPrefix }) {
  const refs = useRef([]);
  const index = items.findIndex((t) => t.id === value);

  const handleKeyDown = (e) => {
    const next = { ArrowRight: index + 1, ArrowLeft: index - 1, Home: 0, End: items.length - 1 }[e.key];
    if (next === undefined) return;
    e.preventDefault();
    const target = (next + items.length) % items.length;
    onChange(items[target].id);
    refs.current[target]?.focus();
  };

  return (
    <div role="tablist" aria-label={label} onKeyDown={handleKeyDown} className="flex overflow-x-auto border-b border-line">
      {items.map((t, i) => {
        const selected = t.id === value;
        return (
          <button
            key={t.id}
            ref={(el) => { refs.current[i] = el; }}
            type="button"
            role="tab"
            id={`${idPrefix}-tab-${t.id}`}
            aria-selected={selected}
            aria-controls={`${idPrefix}-panel`}
            tabIndex={selected ? 0 : -1}
            onClick={() => onChange(t.id)}
            className={`shrink-0 min-h-[44px] -mb-px px-4 text-sm rounded-t-md border
              ${selected
                ? 'bg-panel text-ink font-semibold border-line border-t-2 border-t-accent border-b-panel'
                : 'border-transparent text-muted hover:text-ink'}`}
          >
            {t.label}
          </button>
        );
      })}
    </div>
  );
}
