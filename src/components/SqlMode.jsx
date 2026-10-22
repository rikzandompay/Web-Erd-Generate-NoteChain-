// frontend/src/components/SqlMode.jsx
import React, { useState } from 'react';
import axios from 'axios';
import DragDropArea from './DragDropArea';
import OutputPanel from './OutputPanel';
import { apiErrorMessage, drawioUrl, pageNames } from '../drawio';

export default function SqlMode() {
  const [file, setFile] = useState(null);
  const [status, setStatus] = useState('idle');
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');

  const handleGenerate = async () => {
    setStatus('loading');
    setError('');
    const formData = new FormData();
    formData.append('file', file);
    try {
      const response = await axios.post('/api/generate', formData, { responseType: 'text' });
      const xml = response.data;
      const match = (response.headers['content-disposition'] || '').match(/filename="?([^"]+)"?/);
      const fileName = match ? match[1] : file.name.replace(/\.sql$/i, '_erd.drawio');
      setResult({ xml, pages: pageNames(xml), errors: [], fileName, openUrl: null });
      setStatus('done');
      // The draw.io link is packed in the browser; it shows up once ready
      const openUrl = await drawioUrl(xml);
      setResult((prev) => (prev?.xml === xml ? { ...prev, openUrl } : prev));
    } catch (err) {
      setResult(null);
      setError(apiErrorMessage(err));
      setStatus('error');
    }
  };

  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)] lg:items-start">
      <section aria-labelledby="sql-input-heading" className="min-w-0 rounded-[10px] border border-line bg-panel p-4 sm:p-5">
        <h2 id="sql-input-heading" className="text-base font-semibold">File SQL</h2>
        <p className="mt-1 mb-4 text-sm text-muted max-w-prose">
          File .sql berisi CREATE TABLE, boleh dengan ALTER TABLE untuk foreign key. Hasilnya dua halaman: ERD notasi Chen dan Class Diagram.
        </p>

        <DragDropArea
          onFileSelected={(picked) => { setFile(picked); setError(''); }}
          isLoading={status === 'loading'}
          file={file}
        />

        <button
          type="button"
          onClick={handleGenerate}
          disabled={!file || status === 'loading'}
          className="mt-4 w-full sm:w-auto min-h-[44px] px-6 rounded-md bg-accent text-on-accent font-semibold hover:bg-accent-hover disabled:cursor-not-allowed disabled:opacity-60"
        >
          {status === 'loading' ? 'Membuat diagram…' : 'Buat diagram'}
        </button>
      </section>

      <OutputPanel
        idPrefix="sql-output"
        status={status}
        result={result}
        error={error}
        emptyText="Belum ada diagram. Pilih file .sql, lalu tekan Buat diagram."
      />
    </div>
  );
}
