// frontend/src/components/OutputPanel.jsx
import React, { useState } from 'react';
import { Download, ExternalLink } from 'lucide-react';
import AiFixerPanel from './AiFixerPanel';
import DiagramPreview from './DiagramPreview';
import Tabs from './Tabs';
import { downloadFile } from '../drawio';
import { downloadPng, downloadSvg } from '../exportImage';


const ACTION = 'inline-flex items-center gap-2 min-h-[44px] px-4 rounded-md border border-edge text-sm font-medium hover:bg-desk disabled:cursor-not-allowed disabled:opacity-60';

// Copy a text to the clipboard and say so; `note` is read out by screen readers too
function CopyButton({ label, text }) {
  const [done, setDone] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setDone(true);
      setTimeout(() => setDone(false), 2000);
    } catch {
      // Clipboard blocked by the browser: nothing to report, the user can still download the file
    }
  };
  return (
    <button type="button" onClick={copy} className={ACTION}>
      {done ? 'Tersalin' : label}
    </button>
  );
}

// Picture of the page being shown: SVG for slides, PNG (2x or 3x) for a report
function ExportBar({ xml, page, name }) {
  const [busy, setBusy] = useState('');
  const [failed, setFailed] = useState('');

  const run = async (key, job) => {
    setBusy(key);
    setFailed('');
    try {
      await job();
    } catch (err) {
      setFailed(err.message || 'Gambar belum bisa dibuat.');
    } finally {
      setBusy('');
    }
  };

  return (
    <div className="mt-4">
      <p className="mb-1 text-sm text-muted">Simpan halaman ini sebagai gambar</p>
      <div className="flex flex-wrap gap-2">
        <button type="button" disabled={!!busy} className={ACTION} onClick={() => run('png2', () => downloadPng(xml, page, name, 2))}>
          {busy === 'png2' ? 'Membuat PNG…' : 'PNG 2x'}
        </button>
        <button type="button" disabled={!!busy} className={ACTION} onClick={() => run('png3', () => downloadPng(xml, page, name, 3))}>
          {busy === 'png3' ? 'Membuat PNG…' : 'PNG 3x'}
        </button>
        <button type="button" disabled={!!busy} className={ACTION} onClick={() => run('svg', () => downloadSvg(xml, page, name))}>
          {busy === 'svg' ? 'Membuat SVG…' : 'SVG'}
        </button>
      </div>
      {failed && <p role="alert" className="mt-2 rounded-md bg-danger-bg px-3 py-2 text-sm text-danger">{failed}</p>}
    </div>
  );
}

// The right-hand side of the workbench: what came out of the last run.
// status: 'idle' (nothing made yet), 'loading', 'error' (request failed), 'done'
export default function OutputPanel({ idPrefix, status, result, error, emptyText, onJumpToLine, diagramType, diagramText, onApplyFix }) {
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
          <>
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

            {diagramType && diagramText && onApplyFix && (
              <AiFixerPanel
                type={diagramType}
                text={diagramText}
                errors={lineErrors}
                onApplyFix={onApplyFix}
              />
            )}
          </>
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

            {result.dictionary && (
              <div>
                <p className="mb-1 text-sm text-muted">Kamus Data untuk laporan ({result.dictionary.tables} tabel)</p>
                <div className="flex flex-wrap gap-2">
                  <CopyButton label="Salin Markdown" text={result.dictionary.markdown} />
                  <CopyButton label="Salin CSV" text={result.dictionary.csv} />
                </div>
              </div>
            )}

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
                <ExportBar xml={result.xml} page={page} name={result.pages[page]} />
              </div>
            </div>
          </>
        )}
      </div>
    </section>
  );
}
