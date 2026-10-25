// frontend/src/components/GuideMode.jsx
import React, { useState } from 'react';
import { EXAMPLES, SYNTAX } from '../examples';

const SECTIONS = [
  { id: 'mulai', label: 'Mulai cepat' },
  { id: 'sql', label: 'Dari file SQL' },
  { id: 'uml', label: 'Dari teks UML' },
  { id: 'prd', label: 'Membuat PRD' },
  { id: 'draw', label: 'Membuka hasilnya' },
  { id: 'error', label: 'Jika muncul pesan error' },
];

const TYPE_NOTES = {
  usecase: {
    title: 'Use case diagram',
    text: 'Use case dibaca dari kiri ke kanan, Input lalu Proses lalu Output: aktor utama di kiri, use case di dalam kotak sistem di tengah, dan aktor sekunder (ditandai <<sekunder>>, misalnya Bank atau Payment Gateway) di kanan. Use case diurutkan otomatis per aktor sehingga garis tidak bersilangan, dan nama use case dibagi dua baris. Setiap use case cukup dihubungkan ke aktornya; include dan extend tidak dipakai.',
  },
  sequence: {
    title: 'Sequence diagram',
    text: 'Pesan diberi nomor otomatis. Peserta bertipe actor tidak mendapat activation bar. Fragment alt, loop, dan opt boleh bersarang.',
  },
  activity: {
    title: 'Activity diagram',
    text: 'Setiap peserta (|Admin|, |Sistem|) menjadi swimlane. Perintah -> menarik panah kembali ke aksi yang namanya sama persis, untuk membuat loop.',
  },
  class: {
    title: 'Class diagram',
    text: 'Atribut dan method ditulis di dalam kurung kurawal. Awali dengan - atau + (private atau public). Garis bertanda panah segitiga kosong menunjukkan pewarisan.',
  },
};

// What the server says when something is wrong, and what to do about it
const ERRORS = [
  ['Invalid file type. Please upload a .sql file.', 'File yang diunggah bukan .sql. Ganti akhiran file atau pilih file lain.'],
  ['Unable to read file. Ensure it is a valid UTF-8 text file.', 'Simpan ulang file SQL dengan encoding UTF-8, lalu unggah lagi.'],
  ['The uploaded SQL file is empty.', 'File kosong. Isi dengan perintah CREATE TABLE.'],
  ['No valid CREATE TABLE statements found in SQL file.', 'Tidak ada CREATE TABLE yang terbaca. Perintah lain seperti SELECT atau INSERT diabaikan.'],
  ['Baris tidak dikenali', 'Satu baris teks UML salah tulis. Klik pesannya di panel Hasil, dan baris itu langsung terpilih di editor. Halaman lain tetap dibuat.'],
  ['belum ditutup dengan …', 'Ada alt, loop, opt, if, fork, atau class yang dibuka tapi tidak ditutup (end, endif, end fork, atau }).'],
  ['Aksi tujuan "…" tidak ditemukan', 'Panah -> di diagram activity menunjuk nama aksi yang tidak ada. Samakan tulisannya dengan aksi tujuan.'],
  ['Tidak bisa menghubungi server', 'Backend belum berjalan. Nyalakan dulu, lalu coba lagi.'],
];

function CodeSample({ code }) {
  const [copied, setCopied] = useState(false);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Clipboard blocked: the text is still selectable by hand
    }
  };

  return (
    <div className="rounded-md border border-edge">
      <div className="flex items-center justify-between gap-2 border-b border-line px-3">
        <span className="text-sm text-muted">Contoh</span>
        <button type="button" onClick={copy} className="min-h-[44px] px-3 text-sm font-medium hover:underline">
          {copied ? 'Tersalin' : 'Salin'}
        </button>
      </div>
      <pre tabIndex={0} className="m-0 max-h-72 overflow-auto p-3 font-mono text-sm leading-5">{code}</pre>
    </div>
  );
}

function Section({ id, title, children }) {
  return (
    <section id={id} aria-labelledby={`${id}-title`} className="scroll-mt-4 rounded-[10px] border border-line bg-panel p-4 sm:p-5">
      <h2 id={`${id}-title`} className="text-base font-semibold">{title}</h2>
      <div className="mt-3 space-y-3 text-sm leading-6 max-w-prose">{children}</div>
    </section>
  );
}

// Every statement here is something the app really does; the error table quotes its real messages.
export default function GuideMode({ onOpenMode }) {
  return (
    <div className="grid gap-6 lg:grid-cols-[14rem_minmax(0,1fr)] lg:items-start">
      <nav aria-label="Isi panduan" className="lg:sticky lg:top-4">
        <ul className="m-0 flex list-none flex-wrap gap-x-4 p-0 lg:block">
          {SECTIONS.map((s) => (
            <li key={s.id}>
              <a href={`#${s.id}`} className="flex min-h-[44px] items-center text-sm text-muted hover:text-ink hover:underline">
                {s.label}
              </a>
            </li>
          ))}
        </ul>
      </nav>

      <div className="min-w-0 space-y-6">
        <Section id="mulai" title="Mulai cepat">
          <ol className="m-0 list-decimal space-y-2 pl-5">
            <li>Pilih sumbernya: tab <strong>File SQL</strong> kalau sudah punya struktur database, atau tab <strong>Teks UML</strong> kalau ingin menulis diagram sendiri.</li>
            <li>Tekan <strong>Buat diagram</strong>. Hasilnya tampil di panel Hasil, satu tab untuk setiap halaman.</li>
            <li>Tekan <strong>Unduh .drawio</strong> untuk menyimpan file, atau <strong>Buka di draw.io</strong> untuk mengeditnya langsung di app.diagrams.net.</li>
          </ol>
          <p className="m-0 text-muted">File dan teks diproses saat itu juga dan tidak disimpan di server.</p>
          <div className="flex flex-wrap gap-2 pt-1">
            <button type="button" onClick={() => onOpenMode('sql')} className="min-h-[44px] rounded-md border border-edge px-4 font-medium hover:bg-desk">Buka tab File SQL</button>
            <button type="button" onClick={() => onOpenMode('uml')} className="min-h-[44px] rounded-md border border-edge px-4 font-medium hover:bg-desk">Buka tab Teks UML</button>
          </div>
        </Section>

        <Section id="sql" title="Dari file SQL">
          <p className="m-0">Unggah file <code className="font-mono">.sql</code> berencoding UTF-8. Hasilnya satu file dengan tiga halaman: ERD notasi Chen, Class Diagram, dan Kamus Data.</p>
          <p className="m-0 font-semibold">Yang dibaca dari file</p>
          <ul className="m-0 list-disc space-y-1 pl-5">
            <li>Setiap <code className="font-mono">CREATE TABLE</code>, lengkap dengan kolom dan tipenya.</li>
            <li>Primary key, baik yang ditulis di baris kolom maupun sebagai <code className="font-mono">PRIMARY KEY (...)</code>.</li>
            <li>Foreign key dalam tiga bentuk: <code className="font-mono">FOREIGN KEY ... REFERENCES</code> di dalam tabel, <code className="font-mono">REFERENCES</code> di baris kolom, dan <code className="font-mono">ALTER TABLE ... ADD CONSTRAINT</code> di bawah (format ekspor dbdiagram.io dan phpMyAdmin).</li>
            <li>Kolom yang bisa NULL, nilai <code className="font-mono">DEFAULT</code>, dan <code className="font-mono">COMMENT '...'</code>.</li>
            <li>Komentar <code className="font-mono">/* */</code> dan komentar <code className="font-mono">--</code> di baris sendiri diabaikan. Komentar <code className="font-mono">--</code> di <strong>samping</strong> kolom menjadi isi kolom Keterangan.</li>
          </ul>
          <p className="m-0 font-semibold">Halaman Kamus Data</p>
          <ul className="m-0 list-disc space-y-1 pl-5">
            <li>Satu tabel per tabel SQL dengan kolom No, Nama Kolom, Tipe Data, Kunci (PK atau FK ke tabel.kolom), Null, Default, dan Keterangan.</li>
            <li>Keterangan hanya berisi komentar yang kamu tulis di SQL. Kalau tidak ada komentar, kolomnya kosong, tidak diisi tebakan.</li>
            <li>Tombol <strong>Salin Markdown</strong> dan <strong>Salin CSV</strong> di panel Hasil menyalin semua tabel sekaligus, siap ditempel ke laporan.</li>
          </ul>
          <p className="m-0 font-semibold">Cara membaca hasilnya</p>
          <ul className="m-0 list-disc space-y-1 pl-5">
            <li>Persegi panjang adalah entitas, oval adalah atribut, belah ketupat adalah relasi.</li>
            <li>Atribut primary key digaris bawah, atribut foreign key dicetak miring.</li>
            <li>Nama di dalam belah ketupat dibuat dari dua petunjuk. Pertama, nama kolom foreign key: <code className="font-mono">penulis_id</code> menjadi <em>menulis</em>, <code className="font-mono">diverifikasi_oleh</code> menjadi <em>memverifikasi</em>, <code className="font-mono">created_by</code> menjadi <em>membuat</em>. Kalau kolomnya biasa saja, dari jenis kedua tabel: kategori <em>mengelompokkan</em> produk, supplier <em>memasok</em> barang masuk, donatur <em>memberikan</em> donasi, rekening <em>menerima</em> donasi, donasi <em>tercatat sebagai</em> transaksi, kegiatan <em>dilengkapi</em> foto kegiatan. <em>Memiliki</em> hanya dipakai kalau tidak ada petunjuk sama sekali. Untuk menentukan nama sendiri, tulis komentar di kolom foreign key: <code className="font-mono">id_supplier INT, -- @rel: memasok</code>.</li>
            <li>Label <strong>N</strong> ada di sisi tabel yang memegang foreign key, <strong>1</strong> di sisi tabel yang dirujuk. Semua relasi dibaca N ke 1; jenis 1 ke 1 tidak dideteksi.</li>
            <li>Di Class Diagram, setiap tabel menjadi kelas dengan method create, read, update, delete, dan satu method untuk tiap tabel yang berhubungan.</li>
          </ul>
        </Section>

        <Section id="uml" title="Dari teks UML">
          <p className="m-0">
            Satu teks boleh berisi banyak diagram. Setiap baris yang diawali <code className="font-mono">===</code> memulai halaman baru, dan namanya menjadi nama tab di draw.io. Baris yang diawali tanda kutip tunggal (<code className="font-mono">'</code>) adalah komentar.
          </p>
          {Object.keys(TYPE_NOTES).map((type) => (
            <div key={type} className="space-y-2 border-t border-line pt-3">
              <h3 className="m-0 text-sm font-semibold">{TYPE_NOTES[type].title}</h3>
              <p className="m-0">{TYPE_NOTES[type].text}</p>
              <dl className="m-0 space-y-1">
                {SYNTAX[type].map(([code, meaning]) => (
                  <div key={code} className="flex flex-wrap gap-x-3">
                    <dt className="font-mono break-words">{code}</dt>
                    <dd className="m-0 text-muted">{meaning}</dd>
                  </div>
                ))}
              </dl>
              <CodeSample code={EXAMPLES[type]} />
            </div>
          ))}
        </Section>

        <Section id="prd" title="Membuat PRD">
          <p className="m-0">Tab <strong>PRD</strong> memandu dari ide mentah sampai daftar task, satu layar per langkah. Penanda <strong>Ide, PRD, Task</strong> di atas menunjukkan posisimu.</p>
          <ol className="m-0 list-decimal space-y-2 pl-5">
            <li><strong>Mau bikin apa?</strong> Ceritakan idemu dalam beberapa kalimat dan pilih bahasa dokumen. Tombol <strong>Referensi</strong> untuk menambah aturan bisnis atau mengunggah skema database lama (.sql).</li>
            <li><strong>Beberapa pertanyaan.</strong> AI mengajukan 5 pertanyaan tentang idemu. Pilih jawaban yang ada, tambah sendiri lewat <strong>+ Lainnya</strong>, atau <strong>Lewati</strong>.</li>
            <li><strong>Teknologi.</strong> Pilih template (Next.js, React + FastAPI, Laravel, Flutter + Supabase, atau atur sendiri), tingkat keahlian, dan budget server, lalu tekan <strong>Bikin Struktur</strong>.</li>
            <li><strong>Struktur fitur.</strong> Peta fitur per fase (Fase 1 adalah MVP) beserta sub-fiturnya.</li>
            <li><strong>PRD.</strong> User journey, arsitektur, skema database, dan API. Skema dan use case diperiksa dengan parser aplikasi ini, dan bisa langsung dijadikan diagram lewat <strong>Buat ERD dari PRD</strong> dan <strong>Buat Use Case dari PRD</strong>.</li>
            <li><strong>Task.</strong> Task kecil berurutan sesuai dependensi, lalu <strong>Unduh PRD.md</strong> atau <strong>Salin Markdown</strong>.</li>
          </ol>
          <ul className="m-0 list-disc space-y-1 pl-5">
            <li><strong>Kembali</strong> dan maju lagi tidak memanggil AI ulang. AI baru dipanggil lagi kalau jawabanmu di langkah sebelumnya berubah.</li>
            <li>Draf tersimpan di browser ini; <strong>Mulai PRD baru</strong> menghapusnya. Bagian "Asumsi AI" berisi hal yang ditebak AI, jadi periksa sebelum dipakai.</li>
          </ul>
        </Section>

        <Section id="draw" title="Membuka hasilnya">
          <ul className="m-0 list-disc space-y-1 pl-5">
            <li>Di draw.io, setiap halaman muncul sebagai tab di bagian bawah jendela.</li>
            <li>Warna garis dan teks mengikuti tema draw.io, jadi diagram tetap terbaca di mode terang maupun gelap.</li>
            <li>Semua ukuran dan posisi mengikuti grid 10, sehingga tidak perlu menyusun ulang dengan Arrange.</li>
            <li>Garis yang berbelok menyimpan titik beloknya. Kalau sebuah kotak digeser, garis lurus ikut bergerak, sedangkan garis berbelok perlu disesuaikan sendiri.</li>
            <li>Di bawah preview ada tombol <strong>PNG 2x</strong>, <strong>PNG 3x</strong>, dan <strong>SVG</strong> untuk menyimpan halaman yang sedang tampil sebagai gambar. PNG cocok untuk laporan, SVG tidak pecah saat diperbesar. Gambar dibuat di browser dengan latar putih.</li>
            <li>Preview di halaman ini memakai viewer resmi draw.io dan butuh koneksi internet. Tanpa internet, file tetap bisa diunduh.</li>
          </ul>
        </Section>

        <Section id="error" title="Jika muncul pesan error">
          <p className="m-0">Pesan di bawah adalah yang benar-benar ditampilkan aplikasi.</p>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[32rem] border-collapse text-left">
              <thead>
                <tr className="border-b border-edge">
                  <th scope="col" className="py-2 pr-4 font-semibold">Pesan</th>
                  <th scope="col" className="py-2 font-semibold">Artinya dan cara memperbaiki</th>
                </tr>
              </thead>
              <tbody>
                {ERRORS.map(([message, fix]) => (
                  <tr key={message} className="border-b border-line align-top">
                    <td className="py-2 pr-4 font-mono">{message}</td>
                    <td className="py-2">{fix}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Section>
      </div>
    </div>
  );
}
