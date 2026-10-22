// frontend/src/components/OutputPanel.jsx
import React, { useState } from 'react';
import { Download, ExternalLink } from 'lucide-react';
import DiagramPreview from './DiagramPreview';
import Tabs from './Tabs';
import { downloadFile } from '../drawio';

// The right-hand side of the workbench: what came out of the last run.
// status: 'idle' (nothing made yet), 'loading', 'error' (request failed), 'done'
export default function OutputPanel({ idPrefix, status, result, error, emptyText, onJumpToLine }) {
  const [picked, setPicked] = useState({ xml: null, page: 0 });
  const page = picked.xml === result?.xml ? picked.page : 0;
  const lineErrors = result?.errors || [];

  return (
    <section aria-labelledby={`${idPrefix}-heading`} className="min-w-0 rounded-[10px] border border-line bg-panel p-4 sm:p-5">
      <h2 id={`${idPrefix}-heading`} className="text-base font-semibold">Hasil</h2>

      <div aria-live="polite" className="mt-3 space-y-4">
        {status === 'idle' && <p className="text-sm text-muted max-w-prose">{emptyText}</p>}

        {status === 'loading' && <p className="text-sm text-muted">Membuat diagram…</p>}

        {status === 'error' && (
          <div role="alert" className="rounded-md bg-danger-bg px-4 py-3 text-sm text-danger">
            <p className="font-semibold">Diagram belum bisa dibuat</p>
            <p className="mt-1">{error}</p>
          </div>
        )}

        {status === 'done' && lineErrors.length > 0 && (
          <div className="rounded-md bg-danger-bg px-4 py-3 text-sm text-danger">
            <p className="font-semibold">
              {lineErrors.length} baris perlu diperbaiki.{result.xml ? ' Halaman lain tetap dibuat.' : ''}
            </p>
            <ul className="mt-2 space-y-1">
              {lineErrors.map((e) => (
                <li key={`${e.line}-${e.message}`}>
                  <button
                    type="button"
                    onClick={() => onJumpToLine?.(e.line)}
                    className="text-left underline underline-offset-2 hover:no-underline"
                  >
                    Baris {e.line}, halaman {e.page}: {e.message}
                  </button>
                </li>
              ))}
            </ul>
          </div>
        )}

        {status === 'done' && !result.xml && (
          <p className="text-sm text-muted">Belum ada halaman yang bisa dibuat. Perbaiki baris di atas, lalu buat ulang.</p>
        )}

        {status === 'done' && result.xml && (
          <>
            <div className="flex flex-wrap items-center gap-2">
              <button
                type="button"
                onClick={() => downloadFile(result.xml, result.fileName)}
                className="inline-flex items-center gap-2 min-h-[44px] px-4 rounded-md border border-edge text-sm font-medium hover:bg-desk"
              >
                {/* Download glyph: tells this saves a file instead of opening a page */}
                <Download size={16} aria-hidden="true" /> Unduh .drawio
              </button>
              {result.openUrl && (
                <a
                  href={result.openUrl}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-2 min-h-[44px] px-4 rounded-md border border-edge text-sm font-medium hover:bg-desk"
                >
                  {/* External-link glyph: warns that draw.io opens in a new tab */}
                  Buka di draw.io <ExternalLink size={16} aria-hidden="true" />
                  <span className="sr-only">(tab baru)</span>
                </a>
              )}
            </div>

            <div>
              <p className="mb-1 text-sm text-muted break-all">{result.fileName}, {result.pages.length} halaman</p>
              <Tabs
                items={result.pages.map((name, i) => ({ id: i, label: name }))}
                value={page}
                onChange={(i) => setPicked({ xml: result.xml, page: i })}
                label="Halaman di file hasil"
                idPrefix={`${idPrefix}-page`}
              />
              <div role="tabpanel" id={`${idPrefix}-page-panel`} aria-labelledby={`${idPrefix}-page-tab-${page}`} className="pt-4">
                <DiagramPreview xml={result.xml} page={page} pageName={result.pages[page]} />
              </div>
            </div>
          </>
        )}
      </div>
    </section>
  );
}
