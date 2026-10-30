// frontend/src/components/PrdDocument.jsx
import React, { useEffect, useMemo, useRef, useState } from 'react';
import axios from 'axios';
import { Download } from 'lucide-react';
import { apiErrorMessage, downloadFile } from '../drawio';

// The finished PRD as a document: contents on the left, the text on the right, and a
// version picker. The page shows the same Markdown that "Unduh PRD.md" saves, rendered
// here by a small reader of the subset api/prd.py writes (no HTML is injected).

const SECONDARY = 'inline-flex items-center gap-2 min-h-[44px] px-4 rounded-md border border-edge text-sm font-medium hover:bg-desk';
const PRIMARY = 'inline-flex items-center gap-2 min-h-[44px] px-4 rounded-md bg-accent text-on-accent text-sm font-semibold hover:bg-accent-hover';

// ── Markdown → blocks ────────────────────────────────────────────────────────

function cells(line) {
  return line.trim().replace(/^\||\|$/g, '').replace(/\\\|/g, '\uE000').split('|').map((c) => c.trim().replace(/\uE000/g, '|'));
}

function parseMarkdown(md) {
  const lines = md.replace(/\r/g, '').split('\n');
  const blocks = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (!line.trim()) { i += 1; continue; }
    const fence = line.match(/^```(\w*)/);
    if (fence) {
      const body = [];
      i += 1;
      while (i < lines.length && !lines[i].startsWith('```')) body.push(lines[i++]);
      blocks.push({ type: 'code', lang: fence[1], text: body.join('\n') });
      i += 1;
      continue;
    }
    const heading = line.match(/^(#{1,4})\s+(.*)$/);
    if (heading) {
      blocks.push({ type: `h${heading[1].length}`, text: heading[2] });
      i += 1;
      continue;
    }
    if (line.trim().startsWith('|')) {
      const rows = [];
      while (i < lines.length && lines[i].trim().startsWith('|')) rows.push(lines[i++]);
      const [head, , ...body] = rows;
      blocks.push({ type: 'table', head: cells(head), rows: body.map(cells) });
      continue;
    }
    const list = line.match(/^(-|\d+\.)\s+/);
    if (list) {
      const ordered = list[1] !== '-';
      const items = [];
      while (i < lines.length && (ordered ? /^\d+\.\s+/ : /^-\s+/).test(lines[i])) {
        items.push(lines[i].replace(/^(-|\d+\.)\s+/, ''));
        i += 1;
      }
      blocks.push({ type: ordered ? 'ol' : 'ul', items });
      continue;
    }
    const text = [];
    while (i < lines.length && lines[i].trim() && !/^(```|#{1,4}\s|\||-\s|\d+\.\s)/.test(lines[i])) text.push(lines[i++]);
    blocks.push({ type: 'p', text: text.join(' ') });
  }
  return blocks;
}

function Inline({ text }) {
  const parts = text.split(/(\*\*[^*]+\*\*|`[^`]+`|_[^_\s][^_]*_)/g).filter(Boolean);
  return parts.map((part, i) => {
    if (part.startsWith('**')) return <strong key={i}>{part.slice(2, -2)}</strong>;
    if (part.startsWith('`')) return <code key={i} className="rounded bg-desk px-1 font-mono text-[0.9em]">{part.slice(1, -1)}</code>;
    if (part.startsWith('_') && part.endsWith('_')) return <em key={i} className="text-muted">{part.slice(1, -1)}</em>;
    return <React.Fragment key={i}>{part}</React.Fragment>;
  });
}

function Block({ block, id }) {
  switch (block.type) {
    case 'h1':
      return <h1 className="m-0 text-2xl sm:text-3xl font-semibold tracking-tight"><Inline text={block.text} /></h1>;
    case 'h2':
      return <h2 id={id} className="mt-10 mb-3 scroll-mt-6 text-xl font-semibold"><Inline text={block.text} /></h2>;
    case 'h3':
      return <h3 className="mt-6 mb-2 text-base font-semibold"><Inline text={block.text} /></h3>;
    case 'h4':
      return <h4 className="mt-5 mb-1 text-[15px] font-semibold"><Inline text={block.text} /></h4>;
    case 'p':
      return <p className="my-3 leading-7"><Inline text={block.text} /></p>;
    case 'ul':
      return <ul className="my-3 list-disc space-y-1.5 pl-6 leading-7">{block.items.map((t, i) => <li key={i}><Inline text={t} /></li>)}</ul>;
    case 'ol':
      return <ol className="my-3 list-decimal space-y-1.5 pl-6 leading-7">{block.items.map((t, i) => <li key={i}><Inline text={t} /></li>)}</ol>;
    case 'code':
      return (
        <pre tabIndex={0} className="my-3 max-h-[28rem] overflow-auto rounded-md border border-line bg-desk p-3 font-mono text-xs leading-5">
          {block.text}
        </pre>
      );
    case 'table':
      return (
        <div className="my-3 overflow-x-auto rounded-md border border-line">
          <table className="w-full border-collapse text-left text-sm">
            <thead><tr className="bg-desk">{block.head.map((h, i) => <th key={i} scope="col" className="border-b border-line px-3 py-2 font-semibold"><Inline text={h} /></th>)}</tr></thead>
            <tbody>
              {block.rows.map((row, r) => (
                <tr key={r} className="border-b border-line last:border-b-0 align-top">
                  {/* Short codes (FR-01, T02, PK) stay on one line */}
                  {row.map((c, i) => <td key={i} className={`px-3 py-2 ${c.length <= 6 ? 'whitespace-nowrap' : ''}`}><Inline text={c} /></td>)}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      );
    default:
      return null;
  }
}

// ── The document view ────────────────────────────────────────────────────────

function stamp(iso) {
  try {
    return new Date(iso).toLocaleString('id-ID', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });
  } catch {
    return '';
  }
}

export default function PrdDocument({ versions, onBack, onReuse, busy }) {
  const latest = versions[versions.length - 1];
  // A choice only holds while no newer version exists; a new version is shown straight away
  const [choice, setChoice] = useState(null);
  const picked = choice && choice.latest === latest.n ? choice.n : latest.n;
  const [docs, setDocs] = useState({});               // version → { markdown, file_name } or { error }
  const [note, setNote] = useState('');
  const [active, setActive] = useState(0);
  const article = useRef(null);

  const version = versions.find((v) => v.n === picked) || latest;
  const loaded = docs[version.n];
  const doc = loaded && !loaded.error ? loaded : null;
  const error = loaded?.error || '';

  useEffect(() => {
    if (docs[version.n]) return undefined;
    let live = true;
    axios.post('/api/prd/markdown', version.state)
      .then(({ data }) => { if (live) setDocs((d) => ({ ...d, [version.n]: data })); })
      .catch((err) => { if (live) setDocs((d) => ({ ...d, [version.n]: { error: apiErrorMessage(err) } })); });
    return () => { live = false; };
  }, [version, docs]);

  const blocks = useMemo(() => (doc ? parseMarkdown(doc.markdown) : []), [doc]);
  // The n-th section heading gets id prd-doc-sec-n, which the contents list links to
  const headingIds = useMemo(() => blocks.map((b, i) => (b.type === 'h2'
    ? `prd-doc-sec-${blocks.slice(0, i).filter((x) => x.type === 'h2').length}` : undefined)), [blocks]);
  const sections = blocks.filter((b) => b.type === 'h2').map((b) => b.text);
  const issues = version.state.issues || [];

  // Highlight the section being read: the last heading that has scrolled past the top of the screen
  useEffect(() => {
    const heads = article.current ? [...article.current.querySelectorAll('h2[id]')] : [];
    if (!heads.length) return undefined;
    let frame = 0;
    const update = () => {
      frame = 0;
      const passed = heads.filter((h) => h.getBoundingClientRect().top <= 140);
      setActive(passed.length ? Number(passed[passed.length - 1].id.split('-').pop()) : 0);
    };
    const onScroll = () => { if (!frame) frame = requestAnimationFrame(update); };
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => {
      window.removeEventListener('scroll', onScroll);
      if (frame) cancelAnimationFrame(frame);
    };
  }, [blocks]);

  const save = async (how) => {
    if (!doc) return;
    setNote('');
    if (how === 'download') {
      setNote(`${downloadFile(doc.markdown, doc.file_name, 'text/markdown')} diunduh.`);
      return;
    }
    try {
      await navigator.clipboard.writeText(doc.markdown);
      setNote('Markdown tersalin.');
    } catch {
      setNote('Browser menolak menyalin. Pakai tombol unduh.');
    }
  };

  return (
    <div className="mx-auto w-full max-w-[1180px]">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <button type="button" onClick={onBack} className="inline-flex min-h-[44px] items-center px-3 rounded-md text-sm text-muted hover:text-ink hover:bg-desk">
          Kembali ke PRD
        </button>
        <div className="flex flex-wrap items-center gap-2">
          {versions.length > 1 ? (
            <>
              <label htmlFor="prd-version" className="sr-only">Versi dokumen</label>
              <select id="prd-version" value={version.n} onChange={(e) => setChoice({ n: Number(e.target.value), latest: latest.n })}
                className="min-h-[44px] rounded-md border border-edge bg-panel px-3 text-sm text-ink">
                {[...versions].reverse().map((v) => (
                  <option key={v.n} value={v.n}>Versi {v.n}{v.n === latest.n ? ' (terbaru)' : ''}, {stamp(v.at)}</option>
                ))}
              </select>
              {version.n !== latest.n && onReuse && (
                <button type="button" disabled={busy} onClick={() => onReuse(version)} className={SECONDARY}
                  title="Salin versi ini menjadi versi terbaru; versi lain tetap ada">
                  {busy ? 'Menyimpan…' : 'Pakai versi ini'}
                </button>
              )}
            </>
          ) : (
            <span className="px-1 text-sm text-muted">Versi {version.n}, {stamp(version.at)}</span>
          )}
          <button type="button" onClick={() => save('copy')} disabled={!doc} className={SECONDARY}>Salin Markdown</button>
          <button type="button" onClick={() => save('download')} disabled={!doc} className={PRIMARY}>
            <Download size={16} aria-hidden="true" /> Unduh PRD.md
          </button>
        </div>
      </div>
      <div aria-live="polite">
        {note && <p className="m-0 mb-3 text-sm text-muted">{note}</p>}
        {error && <p role="alert" className="m-0 mb-3 rounded-md bg-danger-bg px-3 py-2 text-sm text-danger">{error}</p>}
      </div>

      <div className="grid gap-6 rounded-[10px] border border-line bg-panel p-4 sm:p-6 lg:grid-cols-[230px_minmax(0,1fr)] lg:gap-10">
        <nav aria-label="Daftar isi PRD" className="lg:sticky lg:top-4 lg:self-start">
          <p className="m-0 mb-2 text-sm font-semibold">{doc ? blocks.find((b) => b.type === 'h1')?.text.replace(/^PRD:\s*/, 'PRD: ') : 'PRD'}</p>
          <ol className="m-0 list-none space-y-0.5 p-0 text-sm">
            {sections.map((s, i) => (
              <li key={s}>
                <a href={`#prd-doc-sec-${i}`} aria-current={active === i ? 'location' : undefined}
                  onClick={() => setActive(i)}
                  className={`flex min-h-[36px] items-center rounded-md border-l-2 px-3 ${active === i
                    ? 'border-accent bg-desk font-medium text-ink' : 'border-transparent text-muted hover:text-ink'}`}>
                  {s}
                </a>
              </li>
            ))}
          </ol>
          <p className={`m-0 mt-4 rounded-md px-3 py-2 text-xs ${issues.length ? 'bg-danger-bg text-danger' : 'bg-desk text-muted'}`}>
            {issues.length
              ? `${issues.length} hal belum sinkron antar-bagian; lihat bagian Asumsi.`
              : 'Aktor, use case, skema data, API, dan task sudah diperiksa: semuanya sinkron.'}
          </p>
        </nav>

        <article ref={article} className="min-w-0 max-w-[760px] text-[15px]">
          {!doc && !error && <p className="m-0 text-sm text-muted">Menyiapkan dokumen…</p>}
          {blocks.map((block, i) => <Block key={i} block={block} id={headingIds[i]} />)}
        </article>
      </div>
    </div>
  );
}
