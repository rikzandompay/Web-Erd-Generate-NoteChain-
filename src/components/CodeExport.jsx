// frontend/src/components/CodeExport.jsx
import React, { useState } from 'react';
import axios from 'axios';
import { Download } from 'lucide-react';
import { apiErrorMessage, downloadFile } from '../drawio';

// Starter code from a .sql schema (api/codegen.py): rule based, no AI, so it is
// instant and the same schema always gives the same files.

const TARGETS = [
  { id: 'laravel', label: 'Laravel', note: 'Migration dan model Eloquent' },
  { id: 'prisma', label: 'Prisma', note: 'schema.prisma untuk Next.js atau Node.js' },
  { id: 'sqlalchemy', label: 'SQLAlchemy', note: 'models.py untuk FastAPI atau Flask' },
];
const DATABASES = [['postgresql', 'PostgreSQL'], ['mysql', 'MySQL'], ['sqlite', 'SQLite']];

const SECONDARY = 'inline-flex items-center gap-2 min-h-[44px] px-4 rounded-md border border-edge text-sm font-medium hover:bg-desk disabled:cursor-not-allowed disabled:opacity-60';

export default function CodeExport({ file, idPrefix, defaultTarget = 'laravel', defaultDatabase = 'postgresql' }) {
  const [target, setTarget] = useState(defaultTarget);
  const [database, setDatabase] = useState(defaultDatabase);
  const [state, setState] = useState({ status: 'idle', files: [], zipName: '', error: '', made: null });
  const [picked, setPicked] = useState(0);
  const [note, setNote] = useState('');

  // A result belongs to one file and one choice; anything else shows the button again
  const current = state.made && state.made.file === file && state.made.target === target && state.made.database === database;

  const form = () => {
    const data = new FormData();
    data.append('file', file);
    data.append('target', target);
    data.append('database', database);
    return data;
  };

  const make = async () => {
    setState((s) => ({ ...s, status: 'loading', error: '' }));
    setNote('');
    try {
      const { data } = await axios.post('/api/code', form());
      setState({ status: 'done', files: data.files, zipName: data.zip_name, error: '', made: { file, target, database } });
      setPicked(0);
    } catch (err) {
      setState({ status: 'error', files: [], zipName: '', error: apiErrorMessage(err), made: null });
    }
  };

  const downloadZip = async () => {
    setNote('');
    try {
      const { data } = await axios.post('/api/code/zip', form(), { responseType: 'blob' });
      setNote(`${downloadFile(data, state.zipName, 'application/zip')} diunduh.`);
    } catch (err) {
      setState((s) => ({ ...s, error: err.response ? 'File .zip belum bisa dibuat. Coba lagi.' : apiErrorMessage(err) }));
    }
  };

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(state.files[picked].content);
      setNote(`${state.files[picked].path} tersalin.`);
    } catch {
      setNote('Browser menolak menyalin. Pakai tombol unduh.');
    }
  };

  const shown = current && state.status === 'done' ? state.files : [];

  return (
    <div className="space-y-3">
      <div role="radiogroup" aria-labelledby={`${idPrefix}-label`}>
        <p id={`${idPrefix}-label`} className="m-0 mb-2 text-sm font-medium">Framework</p>
        <div className="flex flex-wrap gap-2">
          {TARGETS.map((t) => (
            <button key={t.id} type="button" role="radio" aria-checked={target === t.id} onClick={() => setTarget(t.id)}
              className={`min-h-[44px] rounded-md border px-4 text-left text-sm ${
                target === t.id ? 'border-accent bg-accent text-on-accent' : 'border-edge hover:bg-desk'}`}>
              <span className="font-medium">{t.label}</span>
            </button>
          ))}
        </div>
        <p className="m-0 mt-1 text-xs text-muted">{TARGETS.find((t) => t.id === target).note}</p>
      </div>

      {target === 'prisma' && (
        <div>
          <label htmlFor={`${idPrefix}-db`} className="block text-sm font-medium">Database</label>
          <select id={`${idPrefix}-db`} value={database} onChange={(e) => setDatabase(e.target.value)}
            className="mt-1 min-h-[44px] rounded-md border border-edge bg-panel px-3 text-sm text-ink">
            {DATABASES.map(([v, label]) => <option key={v} value={v}>{label}</option>)}
          </select>
        </div>
      )}

      <button type="button" onClick={make} disabled={!file || state.status === 'loading'} className={SECONDARY}>
        {state.status === 'loading' ? 'Membuat kode…' : 'Buat kode'}
      </button>

      <div aria-live="polite">
        {state.error && <p role="alert" className="m-0 rounded-md bg-danger-bg px-3 py-2 text-sm text-danger">{state.error}</p>}
        {note && <p className="m-0 text-sm text-muted">{note}</p>}
      </div>

      {shown.length > 0 && (
        <div className="space-y-2">
          <div className="flex flex-wrap items-end gap-2">
            <div className="min-w-0 flex-1">
              <label htmlFor={`${idPrefix}-file`} className="block text-sm font-medium">File ({shown.length})</label>
              <select id={`${idPrefix}-file`} value={picked} onChange={(e) => setPicked(Number(e.target.value))}
                className="mt-1 min-h-[44px] w-full rounded-md border border-edge bg-panel px-3 font-mono text-sm text-ink">
                {shown.map((f, i) => <option key={f.path} value={i}>{f.path}</option>)}
              </select>
            </div>
            <button type="button" onClick={copy} className={SECONDARY}>Salin file ini</button>
            <button type="button" onClick={downloadZip} className={SECONDARY}>
              <Download size={16} aria-hidden="true" /> Unduh semua (.zip)
            </button>
          </div>
          <pre tabIndex={0} aria-label={`Isi ${shown[picked]?.path}`}
            className="m-0 max-h-96 overflow-auto rounded-md border border-line bg-desk p-3 font-mono text-xs leading-5">
            {shown[picked]?.content}
          </pre>
        </div>
      )}
    </div>
  );
}
