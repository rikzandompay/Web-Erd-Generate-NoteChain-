// frontend/src/components/PrdMode.jsx
import React, { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import axios from 'axios';
import { ArrowRight, Download } from 'lucide-react';
import CodeExport from './CodeExport';
import OutputPanel from './OutputPanel';
import PrdDocument from './PrdDocument';
import { apiErrorMessage, drawioUrl, pageNames } from '../drawio';

// A guided wizard, one question per screen: Ide (idea → questions → technology → feature map)
// → PRD → Task. Each AI step runs on the backend (api/prd.py). A step is only asked again when
// what it was made from has changed, so going back and forward costs nothing.

const DRAFT_KEY = 'erdgen-prd-wizard-v1';

const TEMPLATES = [
  { id: 'next', name: 'Starter Next.js', note: 'Aplikasi fullstack dalam satu proyek',
    stack: { frontend: 'Next.js', backend: 'Node.js', database: 'PostgreSQL', deployment: 'Docker' } },
  { id: 'react-fastapi', name: 'React + FastAPI', note: 'Frontend React, API Python, gratis di Vercel',
    stack: { frontend: 'React', backend: 'FastAPI', database: 'PostgreSQL', deployment: 'Vercel' } },
  { id: 'laravel', name: 'Laravel + MySQL', note: 'Pilihan umum untuk aplikasi web kampus dan kantor',
    stack: { frontend: 'Blade + Tailwind', backend: 'Laravel', database: 'MySQL', deployment: 'VPS' } },
  { id: 'flutter', name: 'Flutter + Supabase', note: 'Aplikasi mobile dengan backend siap pakai',
    stack: { frontend: 'Flutter', backend: 'Supabase', database: 'PostgreSQL', deployment: 'Supabase Cloud' } },
  { id: 'custom', name: 'Atur sendiri', note: 'Pilih teknologi satu per satu', stack: null },
];
const STACK_OPTIONS = {
  frontend: ['Next.js', 'React', 'Vue', 'Flutter'],
  backend: ['Node.js', 'Laravel', 'Go', 'FastAPI', 'Supabase'],
  database: ['PostgreSQL', 'MySQL', 'SQLite', 'Redis'],
  deployment: ['Vercel', 'Railway', 'VPS', 'Coolify', 'Docker'],
};
const STACK_LABELS = { frontend: 'Frontend', backend: 'Backend', database: 'Database', deployment: 'Deployment' };
// Starter code that fits each template (CodeExport); 'custom' is read from the backend's name
const CODE_TARGET = { next: 'prisma', 'react-fastapi': 'sqlalchemy', laravel: 'laravel', flutter: 'prisma' };
function codeTarget(input) {
  if (CODE_TARGET[input.template]) return CODE_TARGET[input.template];
  const backend = input.stack.backend.toLowerCase();
  if (backend.includes('laravel') || backend.includes('php')) return 'laravel';
  if (/fastapi|flask|django|python/.test(backend)) return 'sqlalchemy';
  return 'prisma';
}
function codeDatabase(input) {
  const db = input.stack.database.toLowerCase();
  return db.includes('mysql') || db.includes('maria') ? 'mysql' : db.includes('sqlite') ? 'sqlite' : 'postgresql';
}

const SKILLS = [['pemula', 'Pemula'], ['menengah', 'Menengah'], ['pro', 'Pro']];
const BUDGETS = [['zero cost', 'Zero cost'], ['free tier', 'Free tier'], ['paid', 'Berbayar']];

// Screens, and the step of the progress bar each belongs to
const SCREENS = ['start', 'questions', 'tech', 'structure', 'prd', 'tasks'];
const STEP_OF = { start: 0, questions: 0, tech: 0, structure: 0, prd: 1, tasks: 2 };
const STEPS = ['Ide', 'PRD', 'Task'];

const EMPTY = {
  screen: 'start',
  input: {
    idea_text: '', language: 'Bahasa Indonesia', template: 'next',
    stack: { ...TEMPLATES[0].stack },
    constraints: { skill: 'pemula', budget: 'free tier' },
    context: { text: '', sql_text: '', sql_name: '' },
  },
  questions: null, replies: [],           // replies[i]: { skipped, picked: [], other, otherOn, text }
  idea: null, plan: null, checks: null, tasks: null, problems: [],
  assumptions: { idea: [], plan: [], tasks: [] },
  made: { questions: '', idea: '', plan: '', tasks: '' },   // what each result was made from
  versions: [],                           // finished PRDs, newest last: { n, at, state }
};

const FIELD = 'w-full rounded-md border border-edge bg-panel px-3 py-2 text-sm leading-6 text-ink';
const PRIMARY = 'inline-flex items-center justify-center gap-2 min-h-[44px] px-6 rounded-md bg-accent text-on-accent font-semibold hover:bg-accent-hover disabled:cursor-not-allowed disabled:opacity-60';
const SECONDARY = 'inline-flex items-center gap-2 min-h-[44px] px-4 rounded-md border border-edge text-sm font-medium hover:bg-desk disabled:cursor-not-allowed disabled:opacity-60';
const QUIET = 'inline-flex items-center min-h-[44px] px-3 rounded-md text-sm text-muted hover:text-ink hover:bg-desk';

function loadDraft() {
  try {
    const saved = JSON.parse(localStorage.getItem(DRAFT_KEY) || 'null');
    if (saved?.input && SCREENS.includes(saved.screen)) {
      return { ...EMPTY, ...saved, input: { ...EMPTY.input, ...saved.input }, made: { ...EMPTY.made, ...saved.made } };
    }
  } catch {
    // Storage blocked or a broken draft: start fresh
  }
  return EMPTY;
}

const emptyReply = () => ({ skipped: false, picked: [], other: '', otherOn: false, text: '' });

function replyText(question, reply) {
  if (!reply || reply.skipped) return '';
  if (question.type === 'text') return reply.text.trim();
  return [...reply.picked, ...(reply.otherOn && reply.other.trim() ? [reply.other.trim()] : [])].join(', ');
}

// ── Small pieces ─────────────────────────────────────────────────────────────

function Stepper({ step }) {
  return (
    <ol aria-label="Langkah" className="m-0 flex list-none items-center gap-2 p-0 text-sm">
      {STEPS.map((label, i) => (
        <li key={label} className="flex items-center gap-2" aria-current={i === step ? 'step' : undefined}>
          {i > 0 && <span aria-hidden="true" className={`h-px w-8 sm:w-16 ${i <= step ? 'bg-accent' : 'bg-line'}`} />}
          <span aria-hidden="true" className={`h-2 w-2 rounded-full ${i <= step ? 'bg-accent' : 'bg-edge'}`} />
          <span className={i === step ? 'font-semibold text-ink' : i < step ? 'text-ink' : 'text-muted'}>{label}</span>
        </li>
      ))}
    </ol>
  );
}

function Screen({ title, lead, children, wide }) {
  return (
    <div className={`mx-auto w-full ${wide ? 'max-w-[1180px]' : 'max-w-[760px]'}`}>
      <h2 className="m-0 text-2xl sm:text-3xl font-semibold tracking-tight">{title}</h2>
      {lead && <p className="mt-2 mb-0 text-base text-muted max-w-prose">{lead}</p>}
      <div className="mt-6">{children}</div>
    </div>
  );
}

function Actions({ onBack, children, error, note }) {
  return (
    <div className="mt-8">
      <div aria-live="polite">
        {note && <p className="m-0 mb-3 text-sm text-muted">{note}</p>}
        {error && <p role="alert" className="m-0 mb-3 rounded-md bg-danger-bg px-3 py-2 text-sm text-danger">{error}</p>}
      </div>
      <div className="flex flex-wrap items-center justify-end gap-3">
        {onBack && <button type="button" onClick={onBack} className={QUIET}>Kembali</button>}
        {children}
      </div>
    </div>
  );
}

function Chip({ pressed, onClick, children, dashed }) {
  return (
    <button
      type="button"
      aria-pressed={pressed}
      onClick={onClick}
      className={`min-h-[44px] px-4 rounded-md border text-sm ${dashed ? 'border-dashed' : ''} ${
        pressed ? 'border-accent bg-accent text-on-accent font-medium' : 'border-edge hover:bg-desk'}`}
    >
      {children}
    </button>
  );
}

// ── The feature map: idea → features (with phase) → their sub-features ──────

function FeatureMap({ name, features }) {
  const wrap = useRef(null);
  const rootRef = useRef(null);
  const featRefs = useRef([]);
  const subRefs = useRef([]);
  const [wide, setWide] = useState(false);
  const [paths, setPaths] = useState([]);

  useLayoutEffect(() => {
    const media = window.matchMedia('(min-width: 1024px)');
    const draw = () => {
      setWide(media.matches);
      const box = wrap.current?.getBoundingClientRect();
      if (!box || !media.matches || !rootRef.current) {
        setPaths([]);
        return;
      }
      const at = (el, side) => {
        const r = el.getBoundingClientRect();
        return [side === 'r' ? r.right - box.left : r.left - box.left, r.top - box.top + r.height / 2];
      };
      const curve = ([x1, y1], [x2, y2]) => {
        const mx = (x1 + x2) / 2;
        return `M${x1},${y1} C${mx},${y1} ${mx},${y2} ${x2},${y2}`;
      };
      const out = [];
      features.forEach((_, i) => {
        const f = featRefs.current[i];
        const s = subRefs.current[i];
        if (f) out.push(curve(at(rootRef.current, 'r'), at(f, 'l')));
        if (f && s) out.push(curve(at(f, 'r'), at(s, 'l')));
      });
      setPaths(out);
    };
    draw();
    const observer = new ResizeObserver(draw);
    observer.observe(wrap.current);
    media.addEventListener('change', draw);
    return () => {
      observer.disconnect();
      media.removeEventListener('change', draw);
    };
  }, [features]);

  const n = features.length;
  return (
    <div ref={wrap} className="relative rounded-[10px] border border-line bg-desk p-4 sm:p-6">
      {wide && (
        <svg aria-hidden="true" className="pointer-events-none absolute inset-0 h-full w-full">
          {paths.map((d, i) => <path key={i} d={d} fill="none" stroke="var(--edge)" strokeWidth="1.5" />)}
        </svg>
      )}
      <div
        className="relative grid gap-y-4 lg:grid-cols-[200px_minmax(0,1fr)_minmax(0,1fr)] lg:gap-x-20"
        style={wide ? { gridTemplateRows: `repeat(${n}, auto)` } : undefined}
      >
        <div ref={rootRef} className="rounded-md border border-edge bg-panel px-4 py-3 self-center"
          style={wide ? { gridColumn: 1, gridRow: `1 / span ${n}` } : undefined}>
          <p className="m-0 font-semibold">{name}</p>
          <p className="m-0 text-xs text-muted">Ide produk</p>
        </div>
        {features.map((f, i) => (
          <React.Fragment key={`${f.name}-${i}`}>
            <div ref={(el) => { featRefs.current[i] = el; }} className="rounded-md border border-edge bg-panel px-4 py-3 self-center"
              style={wide ? { gridColumn: 2, gridRow: i + 1 } : undefined}>
              <div className="flex items-start justify-between gap-2">
                <p className="m-0 font-semibold">{f.name}</p>
                <span className="shrink-0 rounded border border-accent px-1.5 text-[11px] font-semibold text-accent">FASE {f.phase}</span>
              </div>
              <p className="m-0 text-xs text-muted">{f.phase === 1 ? 'MVP, dikerjakan pertama' : 'Pengembangan berikutnya'}</p>
            </div>
            <div ref={(el) => { subRefs.current[i] = el; }} className="ml-6 lg:ml-0 rounded-md border border-line bg-panel px-3 py-2"
              style={wide ? { gridColumn: 3, gridRow: i + 1 } : undefined}>
              <p className="m-0 mb-1 text-[11px] font-semibold tracking-wide text-muted">SUB FITUR</p>
              <ul className="m-0 list-none space-y-1 p-0 text-sm">
                {f.sub_features.map((s) => <li key={s} className="rounded bg-desk px-2 py-1">{s}</li>)}
              </ul>
            </div>
          </React.Fragment>
        ))}
      </div>
    </div>
  );
}

function Notes({ title, items }) {
  const shown = (items || []).filter((i) => i && String(i).trim());
  if (!shown.length) return null;
  return (
    <div className="rounded-md border border-line px-3 py-2 text-sm">
      <p className="m-0 font-medium">{title}</p>
      <ul className="m-0 mt-1 list-disc space-y-1 pl-5 text-muted">{shown.map((a, i) => <li key={i}>{a}</li>)}</ul>
    </div>
  );
}

function DocSection({ title, children }) {
  return (
    <section className="border-t border-line pt-5">
      <h3 className="m-0 mb-3 text-base font-semibold">{title}</h3>
      <div className="space-y-2 text-sm leading-6">{children}</div>
    </section>
  );
}

// ── The wizard ───────────────────────────────────────────────────────────────

export default function PrdMode() {
  const [draft, setDraft] = useState(loadDraft);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [showRef, setShowRef] = useState(false);
  const [diagram, setDiagram] = useState({ status: 'idle', result: null, error: '' });
  const top = useRef(null);

  const { screen, input, questions, replies, idea, plan, tasks, made } = draft;

  useEffect(() => {
    try {
      localStorage.setItem(DRAFT_KEY, JSON.stringify(draft));
    } catch {
      // Storage full or blocked: the draft only lives until the page closes
    }
  }, [draft]);

  const update = (patch) => setDraft((d) => ({ ...d, ...(typeof patch === 'function' ? patch(d) : patch) }));
  const setInput = (key, value) => update((d) => ({ input: { ...d.input, [key]: value } }));
  const go = (next) => {
    setError('');
    update({ screen: next });
    top.current?.scrollIntoView({ block: 'start' });
  };

  // What each AI step is made from; a step runs again only when this changes
  const answers = (questions || []).map((q, i) => ({ question: q.question, answer: replyText(q, replies[i]) }))
    .filter((a) => a.answer);
  const payload = { ...input, answers };
  const source = {
    questions: JSON.stringify([input.idea_text.trim(), input.language]),
    idea: JSON.stringify(payload),
    plan: JSON.stringify([payload, idea]),
    tasks: JSON.stringify([payload, idea, plan]),
  };

  const call = async (stage, body) => {
    setBusy(true);
    setError('');
    try {
      const { data } = await axios.post(`/api/prd/${stage}`, body);
      return data;
    } catch (err) {
      setError(apiErrorMessage(err));
      return null;
    } finally {
      setBusy(false);
    }
  };

  // ── Screen actions ─────────────────────────────────────────────────────
  const startNext = async () => {
    if (input.idea_text.trim().length < 10) {
      setError('Ceritakan idenya minimal satu kalimat.');
      return;
    }
    if (made.questions !== source.questions || !questions) {
      const data = await call('questions', { input: payload });
      if (!data) return;
      update({ questions: data.questions, replies: data.questions.map(emptyReply), made: { ...made, questions: source.questions } });
    }
    go('questions');
  };

  const buildStructure = async () => {
    if (made.idea !== source.idea || !idea) {
      const data = await call('idea', { input: payload });
      if (!data) return;
      update((d) => ({ idea: data.idea, assumptions: { ...d.assumptions, idea: data.assumptions },
                       made: { ...d.made, idea: source.idea } }));
    }
    go('structure');
  };

  const buildPlan = async () => {
    if (made.plan !== source.plan || !plan) {
      const data = await call('plan', { input: payload, idea });
      if (!data) return;
      update((d) => ({ plan: data.plan, checks: data.checks, assumptions: { ...d.assumptions, plan: data.assumptions },
                       made: { ...d.made, plan: JSON.stringify([payload, idea]) } }));
      setDiagram({ status: 'idle', result: null, error: '' });
    }
    go('prd');
  };

  const buildTasks = async () => {
    if (made.tasks !== source.tasks || !tasks) {
      const data = await call('tasks', { input: payload, idea, plan });
      if (!data) return;
      update((d) => {
        const assumptions = { ...d.assumptions, tasks: data.assumptions };
        const checks = d.checks || {};
        // Every finished PRD is kept as a version, so an earlier one can be read again
        const version = {
          n: (d.versions?.[d.versions.length - 1]?.n || 0) + 1,
          at: new Date().toISOString(),
          state: {
            input: payload, idea, plan, tasks: data.tasks,
            assumptions: [...assumptions.idea, ...assumptions.plan, ...assumptions.tasks],
            issues: [...(checks.ddl_errors || []), ...(checks.usecase_errors || []), ...(checks.consistency || []), ...data.problems],
          },
        };
        return { tasks: data.tasks, problems: data.problems, assumptions,
                 made: { ...d.made, tasks: JSON.stringify([payload, idea, plan]) },
                 versions: [...(d.versions || []), version].slice(-10) };
      });
    }
    go('tasks');
  };

  const setReply = (i, change) => update((d) => {
    const next = [...d.replies];
    next[i] = { ...(next[i] || emptyReply()), ...change(next[i] || emptyReply()) };
    return { replies: next };
  });

  const togglePick = (i, q, option) => setReply(i, (r) => {
    if (q.type === 'single') return { picked: r.picked[0] === option ? [] : [option], otherOn: false, skipped: false };
    const picked = r.picked.includes(option) ? r.picked.filter((p) => p !== option) : [...r.picked, option];
    return { picked, skipped: false };
  });

  const readSql = (file) => {
    if (!file) return;
    if (!/\.sql$/i.test(file.name)) {
      setError('Pilih file berakhiran .sql.');
      return;
    }
    const reader = new FileReader();
    reader.onload = () => setInput('context', { ...input.context, sql_text: String(reader.result), sql_name: file.name });
    reader.onerror = () => setError('File tidak bisa dibaca.');
    reader.readAsText(file);
  };

  const slugName = (idea?.product_name || 'prd').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'prd';

  const buildErd = async () => {
    setDiagram({ status: 'loading', result: null, error: '' });
    const form = new FormData();
    form.append('file', new File([plan.ddl], `${slugName}.sql`, { type: 'text/plain' }));
    try {
      const { data: xml } = await axios.post('/api/generate', form, { responseType: 'text' });
      setDiagram({ status: 'done', error: '', result: { xml, pages: pageNames(xml), errors: [], fileName: `${slugName}_erd.drawio`, openUrl: await drawioUrl(xml) } });
    } catch (err) {
      setDiagram({ status: 'error', result: null, error: apiErrorMessage(err) });
    }
  };

  // The whole diagram set: ERD, class, data dictionary, use case, and a sequence and activity per MVP feature.
  // Kept for this PRD in memory, so opening it again costs no AI call.
  const bundleCache = useRef({ source: '', result: null });
  const bundleSource = JSON.stringify([payload, idea, plan]);
  const mvpCount = (idea?.features || []).filter((f) => f.phase === 1).length || Math.min(3, (idea?.features || []).length);

  const buildBundle = async () => {
    if (bundleCache.current.source === bundleSource && bundleCache.current.result) {
      setDiagram({ status: 'done', error: '', result: bundleCache.current.result });
      return;
    }
    setDiagram({ status: 'loading', result: null, error: '' });
    try {
      const { data } = await axios.post('/api/prd/diagrams', { input: payload, idea, plan });
      const result = { ...data, openUrl: data.open_url, fileName: data.file_name };
      bundleCache.current = { source: bundleSource, result };
      setDiagram({ status: 'done', error: '', result });
    } catch (err) {
      setDiagram({ status: 'error', result: null, error: apiErrorMessage(err) });
    }
  };

  const ddlFile = useMemo(() => (plan?.ddl ? new File([plan.ddl], `${slugName}.sql`, { type: 'text/plain' }) : null),
    [plan?.ddl, slugName]);

  const buildUseCase = async () => {
    setDiagram({ status: 'loading', result: null, error: '' });
    try {
      const { data } = await axios.post('/api/uml', { type: 'usecase', text: plan.usecase_text });
      setDiagram({ status: 'done', error: '', result: { ...data, openUrl: data.open_url, fileName: `${slugName}_usecase.drawio` } });
    } catch (err) {
      setDiagram({ status: 'error', result: null, error: apiErrorMessage(err) });
    }
  };

  const editPlan = (key, value) => update((d) => ({ plan: { ...d.plan, [key]: value }, checks: null }));

  const restart = () => {
    setDraft(EMPTY);
    setError('');
    setDiagram({ status: 'idle', result: null, error: '' });
  };

  const furthest = tasks ? 'tasks' : plan ? 'prd' : idea ? 'structure' : questions ? 'questions' : null;
  const answered = (questions || []).filter((q, i) => replies[i]?.skipped || replyText(q, replies[i])).length;
  const template = TEMPLATES.find((t) => t.id === input.template) || TEMPLATES[0];
  const checkList = draft.checks
    ? [...draft.checks.ddl_errors, ...draft.checks.usecase_errors, ...(draft.checks.consistency || [])] : [];
  // Drafts saved before versions existed still open as version 1
  const versions = draft.versions?.length ? draft.versions : tasks ? [{
    n: 1, at: new Date().toISOString(),
    state: { input: payload, idea, plan, tasks,
             assumptions: [...draft.assumptions.idea, ...draft.assumptions.plan, ...draft.assumptions.tasks],
             issues: [...checkList, ...(draft.problems || [])] },
  }] : [];

  // ── Render ─────────────────────────────────────────────────────────────
  return (
    <div ref={top} className="scroll-mt-4">
      <div className="mb-8 flex flex-wrap items-center justify-between gap-3">
        <Stepper step={STEP_OF[screen]} />
        {screen !== 'start' && <button type="button" onClick={restart} className={QUIET}>Mulai PRD baru</button>}
      </div>

      {screen === 'start' && (
        <Screen title="Mau bikin apa?" lead="Ceritakan ide aplikasimu. Kami bantu ubah jadi PRD dan task yang siap dikerjakan AI coding agent.">
          <div className="rounded-[10px] border border-edge bg-panel p-3 focus-within:outline focus-within:outline-2 focus-within:outline-offset-2 focus-within:outline-accent">
            <label htmlFor="prd-idea" className="sr-only">Ide aplikasi</label>
            <textarea id="prd-idea" rows={5} maxLength={2000} value={input.idea_text}
              onChange={(e) => setInput('idea_text', e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) startNext(); }}
              placeholder="Contoh: aplikasi pencatatan donasi yayasan, admin memverifikasi bukti transfer, donatur bisa melihat laporan penyaluran setiap bulan"
              className="w-full resize-y bg-transparent px-1 py-1 text-base leading-7 text-ink focus-visible:outline-none" />
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <button type="button" aria-expanded={showRef} onClick={() => setShowRef((v) => !v)} className={SECONDARY}>
                Referensi{input.context.text || input.context.sql_name ? ' (terisi)' : ''}
              </button>
              <label htmlFor="prd-language" className="sr-only">Bahasa dokumen</label>
              <select id="prd-language" value={input.language} onChange={(e) => setInput('language', e.target.value)}
                className="min-h-[44px] rounded-md border border-edge bg-panel px-3 text-sm text-ink">
                <option>Bahasa Indonesia</option>
                <option>English</option>
              </select>
              <button type="button" onClick={startNext} disabled={busy} aria-label="Lanjut ke pertanyaan"
                className={`${PRIMARY} ml-auto px-4`}>
                {busy ? 'Menyiapkan pertanyaan…' : <ArrowRight size={20} aria-hidden="true" />}
              </button>
            </div>
            {showRef && (
              <div className="mt-3 space-y-3 border-t border-line pt-3">
                <div>
                  <label htmlFor="prd-context" className="block text-sm font-medium">Konteks yang sudah ada (opsional)</label>
                  <p className="m-0 text-xs text-muted">Aturan bisnis, API lama, atau catatan lain</p>
                  <textarea id="prd-context" rows={3} maxLength={8000} value={input.context.text}
                    onChange={(e) => setInput('context', { ...input.context, text: e.target.value })} className={`${FIELD} mt-1`} />
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <label className={`${SECONDARY} cursor-pointer`}>
                    {input.context.sql_name ? 'Ganti skema .sql' : 'Unggah skema database lama (.sql)'}
                    <input type="file" accept=".sql" className="sr-only" onChange={(e) => { readSql(e.target.files[0]); e.target.value = ''; }} />
                  </label>
                  {input.context.sql_name && (
                    <>
                      <span className="text-sm text-muted break-all">{input.context.sql_name}</span>
                      <button type="button" className={QUIET}
                        onClick={() => setInput('context', { ...input.context, sql_text: '', sql_name: '' })}>Hapus</button>
                    </>
                  )}
                </div>
              </div>
            )}
          </div>
          <Actions error={error}>
            {furthest && <button type="button" onClick={() => go(furthest)} className={QUIET}>Lanjutkan PRD terakhir</button>}
          </Actions>
        </Screen>
      )}

      {screen === 'questions' && questions && (
        <Screen title="Beberapa pertanyaan" lead="Biar PRD-nya lebih akurat. Jawab atau lewati setiap pertanyaan.">
          <p className="m-0 mb-2 text-right text-sm text-muted" aria-live="polite">{answered}/{questions.length}</p>
          <ol className="m-0 list-none space-y-0 p-0">
            {questions.map((q, i) => {
              const r = replies[i] || emptyReply();
              return (
                <li key={i} className={`border-t border-line py-5 first:border-t-0 first:pt-0 ${r.skipped ? 'opacity-60' : ''}`}>
                  <div className="flex items-start justify-between gap-4">
                    <p id={`prd-q-${i}`} className="m-0 font-medium">
                      <span className="text-muted">{i + 1}.</span> {q.question}
                      {q.type === 'multi' && !/pilih/i.test(q.question) && <span className="font-normal text-muted"> (boleh pilih beberapa)</span>}
                    </p>
                    <button type="button" onClick={() => setReply(i, (x) => ({ skipped: !x.skipped }))} className={QUIET}>
                      {r.skipped ? 'Jawab' : 'Lewati'}
                    </button>
                  </div>
                  {!r.skipped && (q.type === 'text' ? (
                    <textarea aria-labelledby={`prd-q-${i}`} rows={2} value={r.text} placeholder="Ketik jawaban…"
                      onChange={(e) => setReply(i, () => ({ text: e.target.value }))} className={`${FIELD} mt-3`} />
                  ) : (
                    <div role="group" aria-labelledby={`prd-q-${i}`} className="mt-3 flex flex-wrap gap-2">
                      {q.options.map((o) => (
                        <Chip key={o} pressed={r.picked.includes(o)} onClick={() => togglePick(i, q, o)}>{o}</Chip>
                      ))}
                      <Chip dashed pressed={r.otherOn}
                        onClick={() => setReply(i, (x) => ({ otherOn: !x.otherOn, picked: q.type === 'single' && !x.otherOn ? [] : x.picked }))}>
                        + Lainnya
                      </Chip>
                      {r.otherOn && (
                        <input aria-label={`Jawaban lain untuk pertanyaan ${i + 1}`} value={r.other} autoFocus
                          onChange={(e) => setReply(i, () => ({ other: e.target.value }))}
                          className={`${FIELD} min-h-[44px] sm:max-w-xs`} placeholder="Tulis jawabanmu" />
                      )}
                    </div>
                  ))}
                </li>
              );
            })}
          </ol>
          <Actions onBack={() => go('start')} error={error}
            note={answered < questions.length ? `Masih ada ${questions.length - answered} pertanyaan yang belum dijawab atau dilewati.` : ''}>
            <button type="button" onClick={() => go('tech')} disabled={answered < questions.length} className={PRIMARY}>Lanjutkan</button>
          </Actions>
        </Screen>
      )}

      {screen === 'tech' && (
        <Screen title="Teknologi" lead="Pilih template. PRD dan task akan memakai teknologi ini.">
          <div role="radiogroup" aria-label="Template teknologi" className="grid gap-3 sm:grid-cols-2">
            {TEMPLATES.map((t) => {
              const on = input.template === t.id;
              return (
                <button key={t.id} type="button" role="radio" aria-checked={on}
                  onClick={() => update((d) => ({ input: { ...d.input, template: t.id, stack: t.stack ? { ...t.stack } : d.input.stack } }))}
                  className={`rounded-[10px] border p-4 text-left ${on ? 'border-accent bg-panel outline outline-1 outline-accent' : 'border-line bg-panel hover:border-edge'}`}>
                  <span className="flex items-center justify-between gap-2">
                    <span className="font-semibold">{t.name}</span>
                    {on && <span className="text-xs font-semibold text-accent">Terpilih</span>}
                  </span>
                  <span className="mt-1 block text-sm text-muted">{t.note}</span>
                  {t.stack && (
                    <span className="mt-3 flex flex-wrap gap-1">
                      {Object.values(t.stack).map((s) => <span key={s} className="rounded border border-line px-2 py-0.5 text-xs">{s}</span>)}
                    </span>
                  )}
                </button>
              );
            })}
          </div>

          {template.id === 'custom' && (
            <div className="mt-5 grid gap-3 sm:grid-cols-2">
              {Object.keys(STACK_OPTIONS).map((f) => (
                <div key={f}>
                  <label htmlFor={`prd-stack-${f}`} className="block text-sm font-medium">{STACK_LABELS[f]}</label>
                  <input id={`prd-stack-${f}`} list={`prd-stack-list-${f}`} value={input.stack[f]}
                    onChange={(e) => setInput('stack', { ...input.stack, [f]: e.target.value })}
                    className={`${FIELD} mt-1 min-h-[44px]`} placeholder={STACK_OPTIONS[f].join(', ')} />
                  <datalist id={`prd-stack-list-${f}`}>{STACK_OPTIONS[f].map((o) => <option key={o} value={o} />)}</datalist>
                </div>
              ))}
            </div>
          )}

          <div className="mt-6 grid gap-5 sm:grid-cols-2">
            <div role="radiogroup" aria-labelledby="prd-skill-label">
              <p id="prd-skill-label" className="m-0 mb-2 text-sm font-medium">Tingkat keahlian</p>
              <div className="flex flex-wrap gap-2">
                {SKILLS.map(([v, label]) => (
                  <Chip key={v} pressed={input.constraints.skill === v}
                    onClick={() => setInput('constraints', { ...input.constraints, skill: v })}>{label}</Chip>
                ))}
              </div>
            </div>
            <div role="radiogroup" aria-labelledby="prd-budget-label">
              <p id="prd-budget-label" className="m-0 mb-2 text-sm font-medium">Budget server</p>
              <div className="flex flex-wrap gap-2">
                {BUDGETS.map(([v, label]) => (
                  <Chip key={v} pressed={input.constraints.budget === v}
                    onClick={() => setInput('constraints', { ...input.constraints, budget: v })}>{label}</Chip>
                ))}
              </div>
            </div>
          </div>

          <Actions onBack={() => go('questions')} error={error} note={busy ? 'AI sedang menyusun struktur fitur, biasanya 5 sampai 20 detik.' : ''}>
            <button type="button" onClick={buildStructure} disabled={busy || Object.values(input.stack).some((v) => !v.trim())} className={PRIMARY}>
              {busy ? 'Menyusun…' : 'Bikin Struktur'}
            </button>
          </Actions>
        </Screen>
      )}

      {screen === 'structure' && idea && (
        <Screen wide title={idea.product_name || 'Struktur fitur'} lead={idea.problem_statement}>
          <FeatureMap name={idea.product_name || 'Produk'} features={idea.features} />
          <div className="mt-4 grid gap-3 sm:grid-cols-2">
            <Notes title="Tidak dikerjakan di MVP" items={idea.non_goals} />
            <Notes title="Asumsi AI" items={draft.assumptions.idea} />
          </div>
          <Actions onBack={() => go('tech')} error={error} note={busy ? 'AI sedang menyusun PRD, biasanya 10 sampai 30 detik.' : ''}>
            <button type="button" onClick={buildPlan} disabled={busy} className={PRIMARY}>{busy ? 'Menyusun…' : 'Lanjutkan'}</button>
          </Actions>
        </Screen>
      )}

      {screen === 'prd' && idea && plan && (
        <Screen title={`PRD: ${idea.product_name || 'Produk'}`} lead="Periksa rencananya. Skema database dan use case bisa langsung dijadikan diagram.">
          <div className="space-y-5 rounded-[10px] border border-line bg-panel p-4 sm:p-6">
            <section>
              <p className="m-0 text-sm"><strong>Masalah.</strong> {idea.problem_statement}</p>
              <p className="mt-2 mb-0 text-sm"><strong>Solusi.</strong> {idea.solution}</p>
              <p className="mt-2 mb-0 text-sm"><strong>Core value.</strong> {idea.core_value}</p>
            </section>
            <DocSection title="User journey">
              <ol className="m-0 list-decimal space-y-1 pl-5">{plan.user_journey.map((s, i) => <li key={i}>{s}</li>)}</ol>
            </DocSection>
            <DocSection title="Arsitektur">
              <ul className="m-0 list-disc space-y-1 pl-5">
                {plan.architecture.map((a, i) => <li key={i}><strong>{a.layer}:</strong> {a.choice} <span className="text-muted">({a.reason})</span></li>)}
              </ul>
            </DocSection>
            <DocSection title="Data model dan diagram">
              {draft.checks && (
                checkList.length
                  ? <Notes title="Masih perlu diperbaiki" items={checkList} />
                  : <p className="m-0 text-muted">Sudah diperiksa: skema SQL dan use case benar, aktor sama dengan target pengguna, dan setiap fitur Fase 1 punya use case, tabel, serta endpoint.</p>
              )}
              <ul className="m-0 list-disc space-y-1 pl-5">
                {plan.entities.map((e) => <li key={e.name}><code className="font-mono">{e.name}</code> <span className="text-muted">{e.purpose}</span></li>)}
              </ul>
              <div className="flex flex-wrap gap-2 pt-1">
                <button type="button" onClick={buildBundle} disabled={diagram.status === 'loading'} className={PRIMARY}>
                  {diagram.status === 'loading' ? 'Membuat diagram…' : 'Buat paket diagram lengkap'}
                </button>
                <button type="button" onClick={buildErd} disabled={!plan.ddl.trim() || diagram.status === 'loading'} className={SECONDARY}>Buat ERD dari PRD</button>
                <button type="button" onClick={buildUseCase} disabled={!plan.usecase_text.trim() || diagram.status === 'loading'} className={SECONDARY}>Buat Use Case dari PRD</button>
              </div>
              <p className="m-0 text-muted">
                Paket lengkap berisi ERD, Class Diagram, Kamus Data, Use Case, serta Sequence dan Activity untuk {mvpCount} fitur
                Fase 1, dalam satu file .drawio. Sequence dan Activity ditulis AI, biasanya 15 sampai 60 detik.
              </p>
              <details>
                <summary className="flex min-h-[44px] cursor-pointer items-center text-muted hover:text-ink">Lihat atau ubah skema SQL</summary>
                <label htmlFor="prd-ddl" className="sr-only">Skema SQL</label>
                <textarea id="prd-ddl" rows={12} spellCheck={false} value={plan.ddl} onChange={(e) => editPlan('ddl', e.target.value)} className={`${FIELD} font-mono`} />
              </details>
              <details>
                <summary className="flex min-h-[44px] cursor-pointer items-center text-muted hover:text-ink">Lihat atau ubah teks use case</summary>
                <label htmlFor="prd-uc" className="sr-only">Teks use case</label>
                <textarea id="prd-uc" rows={10} spellCheck={false} value={plan.usecase_text} onChange={(e) => editPlan('usecase_text', e.target.value)} className={`${FIELD} font-mono`} />
              </details>
            </DocSection>
            {diagram.status !== 'idle' && (
              <OutputPanel idPrefix="prd-output" status={diagram.status} result={diagram.result} error={diagram.error} emptyText="" />
            )}
            <DocSection title="Kode awal dari skema">
              <p className="m-0 text-muted">Migration dan model dari skema SQL di atas, tanpa AI. Pilihan awal mengikuti template {template.name}.</p>
              <CodeExport file={ddlFile} idPrefix="prd-code" defaultTarget={codeTarget(input)} defaultDatabase={codeDatabase(input)} />
            </DocSection>
            <DocSection title={`API (${plan.api.length} endpoint)`}>
              <ul className="m-0 list-none space-y-1 p-0">
                {plan.api.map((a, i) => <li key={i}><code className="font-mono">{a.method} {a.path}</code> <span className="text-muted">{a.summary}</span></li>)}
              </ul>
              {plan.ai_tools.length > 0 && <p className="m-0"><strong>Tool-call AI:</strong> {plan.ai_tools.map((t) => t.name).join(', ')}</p>}
            </DocSection>
            <Notes title="Asumsi AI" items={draft.assumptions.plan} />
          </div>
          <Actions onBack={() => go('structure')} error={error} note={busy ? 'AI sedang memecah rencana jadi task, biasanya 10 sampai 30 detik.' : ''}>
            <button type="button" onClick={buildTasks} disabled={busy} className={PRIMARY}>{busy ? 'Menyusun…' : 'Lanjutkan ke Task'}</button>
          </Actions>
        </Screen>
      )}

      {screen === 'tasks' && versions.length > 0 && (
        <PrdDocument versions={versions} onBack={() => go('prd')} />
      )}
    </div>
  );
}
