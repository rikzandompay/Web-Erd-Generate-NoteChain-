// frontend/src/components/UmlTextMode.jsx
import React, { useRef, useState } from 'react';
import axios from 'axios';
import OutputPanel from './OutputPanel';
import Tabs from './Tabs';
import { apiErrorMessage } from '../drawio';

const DIAGRAM_TYPES = [
  { id: 'sequence', label: 'Sequence' },
  { id: 'activity', label: 'Activity' },
  { id: 'class', label: 'Class' },
];

const EXAMPLES = {
  sequence: `=== Edit Data Stok Bahan
actor Admin
boundary Sistem
control BahanController
entity Bahan

Admin -> Sistem : Mengklik Tombol Edit
Sistem --> Admin : Menampilkan Form Edit
Admin -> Sistem : Mengisi Data
Admin -> Sistem : Mengklik Tombol Simpan
Sistem -> BahanController : Menjalankan Function update()
BahanController -> Bahan : Menyimpan Data
Bahan --> BahanController : Data Berhasil Diperbarui
BahanController --> Sistem : Redirect ke Halaman Stok Bahan dengan Pesan Sukses
Sistem --> Admin : Menampilkan Pesan Sukses dan Data Stok Bahan yang Diperbarui

=== Login
actor Admin
boundary Sistem
control AuthController
entity User

Admin -> Sistem : Mengisi email dan password
Sistem -> AuthController : login(request)
AuthController -> User : Mencari data user
User --> AuthController : Data user
alt Data valid
  AuthController --> Sistem : Redirect ke dashboard
  Sistem --> Admin : Menampilkan dashboard
else Data tidak valid
  AuthController --> Sistem : Pesan error
  Sistem --> Admin : Menampilkan pesan error
end
`,
  activity: `=== Login
|Admin|
start
:Membuka halaman login;
|Sistem|
:Menampilkan form login;
|Admin|
:Mengisi email dan password;
:Klik tombol masuk;
|Sistem|
:Validasi data;
if (Data valid?) then (ya)
  :Redirect ke dashboard;
else (tidak)
  :Menampilkan pesan error;
  -> Mengisi email dan password
endif
stop
`,
  class: `=== Class Diagram
class bahan {
  - id : int
  - nama_bahan : varchar
  - satuan : varchar
  + create()
  + update()
  + delete()
}
class stok_masuk {
  - id : int
  - jumlah : decimal
  - tanggal : date
}
class bahan_kering {
  - kadar_air : decimal
}

bahan "1" -- "0..*" stok_masuk : memiliki
bahan <|-- bahan_kering
`,
};

// Syntax guide per type: [what you write, what it does]
const SYNTAX = {
  sequence: [
    ['=== Nama Halaman', 'mulai diagram baru di halaman sendiri'],
    ['actor Admin', 'peserta; juga boundary, control, entity'],
    ['A -> B : pesan', 'pesan, garis penuh'],
    ['A --> B : balasan', 'balasan, garis putus-putus'],
    ['alt kondisi / else kondisi / end', 'cabang; juga loop … end dan opt … end'],
  ],
  activity: [
    ['=== Nama Halaman', 'mulai diagram baru di halaman sendiri'],
    ['|Admin|', 'pindah swimlane'],
    ['start / stop', 'titik mulai dan selesai'],
    [':Mengisi data;', 'aksi'],
    ['if (valid?) then (ya) / else (tidak) / endif', 'keputusan'],
    ['fork / fork again / end fork', 'langkah paralel'],
    ['-> Mengisi data', 'panah kembali ke aksi sebelumnya'],
  ],
  class: [
    ['=== Nama Halaman', 'mulai diagram baru di halaman sendiri'],
    ['class Nama { - id : int  + simpan() }', 'kelas dengan atribut dan method'],
    ['A "1" -- "0..*" B : nama', 'asosiasi dengan multiplicity'],
    ['A <|-- B', 'B turunan dari A'],
    ['A *-- B  /  A o-- B', 'komposisi / agregasi'],
    ['A ..> B', 'dependency'],
  ],
};

const LINE_PX = 20;   // editor line height (leading-5)

export default function UmlTextMode() {
  const [type, setType] = useState('sequence');
  // Each diagram type keeps its own text, starting from its example
  const [texts, setTexts] = useState(EXAMPLES);
  const [status, setStatus] = useState('idle');
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');
  const textareaRef = useRef(null);
  const gutterRef = useRef(null);

  const text = texts[type];
  const lineCount = text.split('\n').length;

  const switchType = (next) => {
    setType(next);
    setStatus('idle');
    setResult(null);
    setError('');
  };

  const handleGenerate = async () => {
    setStatus('loading');
    setError('');
    try {
      const { data } = await axios.post('/api/uml', { type, text });
      const name = data.pages.length === 1 ? data.pages[0] : `${type}-diagram`;
      setResult({ ...data, openUrl: data.open_url, fileName: `${name}.drawio` });
      setStatus('done');
    } catch (err) {
      setResult(null);
      setError(apiErrorMessage(err));
      setStatus('error');
    }
  };

  // Select a line in the editor, e.g. when an error is clicked
  const jumpToLine = (line) => {
    const lines = text.split('\n');
    const start = lines.slice(0, line - 1).reduce((sum, l) => sum + l.length + 1, 0);
    const textarea = textareaRef.current;
    textarea.focus();
    textarea.setSelectionRange(start, start + (lines[line - 1] || '').length);
    textarea.scrollTop = Math.max(0, (line - 4) * LINE_PX);
  };

  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)] lg:items-start">
      <section aria-labelledby="uml-input-heading" className="min-w-0 rounded-[10px] border border-line bg-panel p-4 sm:p-5">
        <h2 id="uml-input-heading" className="text-base font-semibold">Teks UML</h2>
        <p className="mt-1 mb-4 text-sm text-muted max-w-prose">
          Tulis satu atau beberapa diagram. Setiap blok yang diawali === menjadi satu halaman di file draw.io.
        </p>

        <Tabs items={DIAGRAM_TYPES} value={type} onChange={switchType} label="Jenis diagram" idPrefix="uml-type" />

        <div role="tabpanel" id="uml-type-panel" aria-labelledby={`uml-type-tab-${type}`} className="pt-4">
          <label htmlFor="uml-editor" className="sr-only">Teks diagram {type}</label>
          {/* The focus ring goes around the whole editor box; on the textarea alone it would be clipped */}
          <div className="flex rounded-md border border-edge bg-panel overflow-hidden focus-within:outline focus-within:outline-2 focus-within:outline-offset-2 focus-within:outline-accent">
            <pre
              ref={gutterRef}
              aria-hidden="true"
              className="m-0 select-none py-3 pl-3 pr-2 text-right font-mono text-sm leading-5 text-muted overflow-hidden h-72 lg:h-[26rem] border-r border-line"
            >
              {Array.from({ length: lineCount }, (_, i) => i + 1).join('\n')}
            </pre>
            <textarea
              id="uml-editor"
              ref={textareaRef}
              value={text}
              onChange={(e) => setTexts((prev) => ({ ...prev, [type]: e.target.value }))}
              onScroll={(e) => { gutterRef.current.scrollTop = e.target.scrollTop; }}
              spellCheck={false}
              wrap="off"
              className="flex-1 min-w-0 h-72 lg:h-[26rem] py-3 px-3 bg-transparent font-mono text-sm leading-5 text-ink resize-none focus-visible:outline-none"
            />
          </div>

          <details className="mt-3 text-sm">
            <summary className="cursor-pointer min-h-[44px] flex items-center text-muted hover:text-ink">Panduan sintaks</summary>
            <dl className="mt-1 space-y-2">
              {SYNTAX[type].map(([code, meaning]) => (
                <div key={code} className="flex flex-wrap gap-x-3">
                  <dt className="font-mono text-ink break-words">{code}</dt>
                  <dd className="m-0 text-muted">{meaning}</dd>
                </div>
              ))}
            </dl>
          </details>
        </div>

        <button
          type="button"
          onClick={handleGenerate}
          disabled={!text.trim() || status === 'loading'}
          className="mt-4 w-full sm:w-auto min-h-[44px] px-6 rounded-md bg-accent text-on-accent font-semibold hover:bg-accent-hover disabled:cursor-not-allowed disabled:opacity-60"
        >
          {status === 'loading' ? 'Membuat diagram…' : 'Buat diagram'}
        </button>
      </section>

      <OutputPanel
        idPrefix="uml-output"
        status={status}
        result={result}
        error={error}
        emptyText="Belum ada diagram. Tulis atau tempel teks di editor, lalu tekan Buat diagram."
        onJumpToLine={jumpToLine}
      />
    </div>
  );
}
