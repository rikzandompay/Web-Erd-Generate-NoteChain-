// frontend/src/components/DragDropArea.jsx
import React, { useRef, useState } from 'react';

// Drop zone for the .sql file. The dashed edge is the usual "drop here" cue;
// the button inside makes it work by keyboard and touch too.
export default function DragDropArea({ onFileSelected, isLoading, file }) {
  const [isDragActive, setIsDragActive] = useState(false);
  const [error, setError] = useState('');
  const inputRef = useRef(null);

  const stop = (e) => {
    e.preventDefault();
    e.stopPropagation();
  };

  const processFile = (picked) => {
    setError('');
    if (!picked.name.toLowerCase().endsWith('.sql')) {
      setError(`"${picked.name}" bukan file .sql. Pilih file dengan akhiran .sql.`);
      return;
    }
    onFileSelected(picked);
  };

  const handleDrop = (e) => {
    stop(e);
    setIsDragActive(false);
    if (isLoading || !e.dataTransfer.files?.length) return;
    if (e.dataTransfer.files.length > 1) {
      setError('Tarik satu file saja.');
      return;
    }
    processFile(e.dataTransfer.files[0]);
  };

  const handleChange = (e) => {
    if (e.target.files?.length) processFile(e.target.files[0]);
  };

  return (
    <div>
      <div
        onDragEnter={(e) => { stop(e); if (!isLoading) setIsDragActive(true); }}
        onDragOver={stop}
        onDragLeave={(e) => { stop(e); setIsDragActive(false); }}
        onDrop={handleDrop}
        className={`rounded-md border-2 border-dashed px-4 py-8 text-center
          ${isDragActive ? 'border-accent bg-desk' : 'border-edge'}`}
      >
        {file ? (
          <>
            <p className="font-medium break-all">{file.name}</p>
            <p className="mt-1 text-sm text-muted">{(file.size / 1024).toFixed(1)} KB</p>
          </>
        ) : (
          <>
            <p className="font-medium">{isDragActive ? 'Lepas file di sini' : 'Tarik file .sql ke sini'}</p>
            <p className="mt-1 text-sm text-muted">atau</p>
          </>
        )}
        <button
          type="button"
          onClick={() => inputRef.current?.click()}
          disabled={isLoading}
          className="mt-3 min-h-[44px] px-4 rounded-md border border-edge text-sm font-medium hover:bg-desk disabled:cursor-not-allowed disabled:opacity-60"
        >
          {file ? 'Ganti file' : 'Pilih file .sql'}
        </button>
        <input ref={inputRef} type="file" accept=".sql" className="sr-only" tabIndex={-1} onChange={handleChange} />
      </div>

      {error && (
        <p role="alert" className="mt-3 rounded-md bg-danger-bg px-4 py-3 text-sm text-danger">{error}</p>
      )}
    </div>
  );
}
