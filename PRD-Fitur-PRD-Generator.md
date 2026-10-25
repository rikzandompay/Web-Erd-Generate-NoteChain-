# PRD: Fitur PRD Generator (Ide → PRD → Task)

| Metadata | Keterangan |
|---|---|
| Dokumen | Product Requirements Document, ekstensi fitur v3 |
| Status | Diimplementasikan 25 Oktober 2026 dengan keputusan default di bagian 10 |
| Tanggal | 25 Oktober 2026 |
| Pemilik | Rikzan |
| Stack saat ini | FastAPI (Python, `api/`) + React 19 + Vite + Tailwind (`src/`), deploy Vercel |
| AI | Endpoint OpenAI-compatible lewat `AI_BASE_URL`, `AI_API_KEY`, `AI_MODEL` (sekarang Google AI Studio, `gemini-flash-lite-latest`) |

---

## 1. Latar Belakang

ERD Generator sekarang mengubah **SQL** dan **teks UML** menjadi file draw.io (ERD Chen, Class, Use Case, Sequence, Activity, Kamus Data), ditambah chatbot AI yang menulis teks UML.

Yang belum ada: tahap **sebelum** diagram. Pengguna (mahasiswa, developer pemula) sering mulai dari ide mentah dan belum punya dokumen rencana. Fitur ini menambah alur tiga tahap mengikuti workflow PRD Pro:

```
1. IDE (Struktur)   →   2. PRD (Rencana)   →   3. TASK (Fitur)
problem & solusi        arsitektur, journey,     task atomik siap
inti                    skema data, API          dikerjakan AI agent
```

Nilai tambah dibanding generator PRD biasa: **skema data di PRD langsung bisa dijadikan ERD, Class Diagram, dan Kamus Data**, dan **user journey langsung bisa dijadikan Use Case Diagram**, memakai generator yang sudah ada di aplikasi ini.

---

## 2. Tujuan dan Non-Goals

### Tujuan (MVP)
1. Pengguna mengisi formulir input wajib (bagian 4), lalu mendapat PRD Pro dalam tiga tahap yang bisa ditinjau dan diedit satu per satu.
2. Output akhir berupa **satu file Markdown** (`PRD-<nama>.md`) yang siap ditempel ke repo dan dibaca AI coding agent.
3. Bagian Data Model berisi **SQL DDL valid** yang lolos `parse_sql()`, dengan tombol "Buat ERD dari PRD".
4. Bagian User Journey berisi teks use case valid (format aplikasi ini, pola kiri ke kanan), dengan tombol "Buat Use Case dari PRD".
5. Daftar task atomik terurut dengan dependensi yang tervalidasi (tidak ada siklus, tidak ada rujukan ke task yang tidak ada).

### Non-Goals
- Tidak ada login, akun, atau penyimpanan PRD di server. Semua stateless, sama seperti fitur lain.
- Tidak membuat issue GitHub, Linear, atau Trello secara otomatis.
- Tidak ada kolaborasi real-time atau riwayat versi.
- Tidak mengeksekusi task (aplikasi ini tidak menulis kode untuk pengguna).
- Tidak mendukung ekspor .docx atau .pdf di MVP (Markdown saja).

---

## 3. User Journey

1. Pengguna membuka tab baru **PRD** (di samping File SQL, Teks UML, Panduan).
2. **Tahap 1 Ide:** mengisi deskripsi ide, lalu menekan **Rumuskan**. AI mengembalikan problem statement, solusi inti, target pengguna, core value, scope MVP, dan non-goals. Semua bisa diedit di tempat.
3. **Tahap 2 Rencana:** mengisi atau memilih tech stack, batasan, dan konteks eksisting (opsional: tempel teks atau unggah `.sql`). Menekan **Buat PRD**. AI mengembalikan user journey, arsitektur, data model (DDL), API spec, dan daftar tool-call AI (kalau aplikasinya berbasis agent).
   - Tombol **Buat ERD dari PRD** mengirim DDL ke `/api/generate` dan menampilkan hasilnya di panel Hasil yang sudah ada.
   - Tombol **Buat Use Case dari PRD** mengirim teks use case ke `/api/uml`.
4. **Tahap 3 Task:** menekan **Pecah jadi Task**. AI mengembalikan task atomik terurut, masing-masing dengan id, dependensi, file yang disentuh, dan kriteria selesai.
5. Pengguna menekan **Unduh PRD.md** atau **Salin Markdown**.

Setiap tahap bisa diulang tanpa menghapus tahap sebelumnya. Mengulang tahap 1 menandai tahap 2 dan 3 sebagai "perlu dibuat ulang", tapi tidak menghapusnya.

---

## 4. Input Wajib

| Kelompok | Field | Bentuk | Wajib |
|---|---|---|---|
| Deskripsi ide | Masalah | teks, maks 1.500 karakter | ya |
| | Target pengguna | teks singkat | ya |
| | Core value | teks singkat | ya |
| Tech stack | Frontend | pilihan: Next.js, React, Vue, Flutter, Lainnya (isian) | ya |
| | Backend | pilihan: Node.js, Laravel, Go, FastAPI, Supabase, Lainnya | ya |
| | Database | pilihan: PostgreSQL, MySQL, SQLite, Redis, Lainnya | ya |
| | Deployment | pilihan: Vercel, Railway, VPS, Coolify, Docker, Lainnya | ya |
| Batasan | Tingkat keahlian | pemula / menengah / pro | ya |
| | Budget infra | zero cost / free tier / paid | ya |
| Konteks eksisting | Teks bebas (aturan bisnis, API spec lama) | teks, maks 8.000 karakter | tidak |
| | File `.sql` skema lama | unggah, diparse dengan `parse_sql()` | tidak |

Tingkat keahlian memengaruhi ukuran task (pemula: task lebih kecil dan lebih banyak penjelasan). Budget memengaruhi pilihan layanan di arsitektur (zero cost: tanpa layanan berbayar).

---

## 5. Output PRD Pro (Markdown)

Urutan bagian di file akhir:

1. **Ringkasan:** nama produk, problem statement, solusi inti, target pengguna, core value.
2. **Scope MVP** dan **Non-Goals** (daftar berpoin).
3. **User Journey:** langkah bernomor, ditambah blok teks use case (format aplikasi ini).
4. **Arsitektur:** tech stack terpilih, komponen, dan alasan singkat per pilihan.
5. **Data Model:** tabel entitas dan relasi, ditambah blok ` ```sql ` berisi DDL lengkap.
6. **API Spec:** per endpoint: method, path, deskripsi, contoh request JSON, contoh response JSON, kode error.
7. **Tool-call AI** (hanya kalau produk berbasis agent): nama tool, deskripsi, parameter JSON Schema.
8. **Atomic Tasks:** tabel `ID | Judul | Bergantung pada | File | Kriteria selesai`, urut topologis.
9. **Asumsi dan Pertanyaan Terbuka:** hal yang ditebak AI karena tidak disebut pengguna.

Bagian 9 wajib ada. AI tidak boleh diam-diam mengarang aturan bisnis; tebakan harus tertulis sebagai asumsi.

---

## 6. Data Model (internal fitur)

Fitur ini stateless, jadi tidak ada tabel database baru. Status disimpan di frontend dan dikirim utuh ke setiap endpoint. Bentuknya:

```jsonc
// PrdState: dikirim ke setiap tahap, dikembalikan dengan bagian tahap itu terisi
{
  "input": {
    "idea": { "problem": "", "target_users": "", "core_value": "" },
    "stack": { "frontend": "React", "backend": "FastAPI", "database": "PostgreSQL", "deployment": "Vercel" },
    "constraints": { "skill": "pemula", "budget": "free tier" },
    "context": { "text": "", "sql_schema": null }       // sql_schema: hasil parse_sql() bila ada .sql
  },
  "idea": {                                              // tahap 1
    "product_name": "", "problem_statement": "", "solution": "",
    "target_users": [""], "core_value": "", "mvp_scope": [""], "non_goals": [""]
  },
  "plan": {                                              // tahap 2
    "user_journey": [""], "usecase_text": "",
    "architecture": [{ "layer": "", "choice": "", "reason": "" }],
    "ddl": "", "entities": [{ "name": "", "purpose": "" }],
    "api": [{ "method": "POST", "path": "", "summary": "", "request": {}, "response": {}, "errors": [""] }],
    "ai_tools": [{ "name": "", "description": "", "parameters": {} }]
  },
  "tasks": [                                             // tahap 3
    { "id": "T01", "title": "", "description": "", "depends_on": [], "files": [""], "acceptance": [""] }
  ],
  "assumptions": [""]
}
```

Draf terakhir disimpan di `localStorage` browser (dibungkus try/catch) supaya tidak hilang saat halaman dimuat ulang. Tidak ada yang dikirim ke server selain saat menekan tombol tahap.

---

## 7. API Spec

Semua endpoint baru memakai `call_model()` dari `api/chat.py` (endpoint OpenAI-compatible yang sama dengan chatbot), batas pemakaian yang sama, dan mengembalikan error dengan pesan bahasa Indonesia seperti endpoint lain.

### 7.1 `POST /api/prd/idea`
- Request: `{ "input": PrdState.input }`
- Response 200: `{ "idea": PrdState.idea, "assumptions": [""] }`
- Error: 400 (field wajib kosong), 429 (batas pemakaian), 502/503/504 (masalah model AI).

### 7.2 `POST /api/prd/plan`
- Request: `{ "input": ..., "idea": ... }`
- Response 200: `{ "plan": PrdState.plan, "assumptions": [""], "checks": { "ddl_errors": [], "usecase_errors": [] } }`
- Validasi server sebelum membalas:
  - `ddl` diparse dengan `parse_sql()`. Kalau gagal, model diminta memperbaiki satu kali (pola yang sama dengan perbaikan sintaks di chatbot). Kalau tetap gagal, error dikembalikan di `checks.ddl_errors`, bukan disembunyikan.
  - `usecase_text` diparse dengan `generate_uml('usecase', ...)`. Kesalahan baris masuk `checks.usecase_errors`.

### 7.3 `POST /api/prd/tasks`
- Request: `{ "input": ..., "idea": ..., "plan": ... }`
- Response 200: `{ "tasks": [...], "assumptions": [""] }`
- Validasi server: id unik; setiap `depends_on` merujuk id yang ada; tidak ada siklus; hasil diurutkan topologis. Kalau ada siklus atau rujukan hilang, model diminta memperbaiki satu kali, lalu error dikembalikan.

### 7.4 `POST /api/prd/markdown`
- Request: `PrdState` lengkap (boleh sebagian; bagian kosong diberi catatan "belum dibuat").
- Response 200: `{ "markdown": "...", "file_name": "PRD-<slug>.md" }`
- Fungsi murni tanpa AI (`render_prd_markdown`), sehingga bisa dites dan dipakai ulang.

### 7.5 Format balasan model
Model diminta membalas **JSON saja** sesuai skema tahap itu. Backend membuang pagar kode, mem-parse JSON, dan memvalidasi tipe field. JSON tidak valid diperlakukan seperti sintaks UML yang salah: satu kali permintaan perbaikan, lalu error yang jelas.

### 7.6 Tool-call AI
Fitur ini tidak memakai tool-call; setiap tahap adalah satu permintaan model yang mengembalikan JSON. Bagian "Tool-call AI" di output hanya diisi untuk **produk pengguna** yang berbasis agent.

---

## 8. Batasan Teknis

- **Durasi:** batas waktu satu panggilan model tetap 90 detik (`TIMEOUT` di `chat.py`). Pembagian menjadi tiga tahap menjaga setiap panggilan tetap kecil dan di bawah batas fungsi Vercel.
- **Ukuran konteks:** konteks teks dipotong 8.000 karakter. Skema `.sql` dikirim sebagai ringkasan tabel dan kolom (bukan file mentah).
- **Batas pemakaian:** satu tahap dihitung satu permintaan pada limiter yang sama dengan chatbot (10 per jam per pengunjung, per instance).
- **Bahasa:** output mengikuti bahasa input pengguna; default bahasa Indonesia.
- **Keamanan:** isi formulir dan konteks adalah data, bukan instruksi untuk model (aturan yang sama dengan system instruction chatbot). Tidak ada API key di frontend.

---

## 9. Atomic Tasks (untuk membangun fitur ini)

Urut sesuai dependensi. Setiap task selesai bila test-nya lulus dan `npx eslint src` bersih.

| ID | Judul | Bergantung | File | Kriteria selesai |
|---|---|---|---|---|
| T01 | Skema dan validasi `PrdState` (dataclass atau Pydantic) | | `api/prd.py`, `api/test_prd.py` | Field wajib kosong ditolak dengan pesan per field |
| T02 | `render_prd_markdown(state)` | T01 | `api/prd.py`, `api/test_prd.py` | Semua 9 bagian keluar urut; bagian kosong bertanda "belum dibuat"; snapshot test |
| T03 | Validator task: id unik, rujukan ada, tanpa siklus, urut topologis | T01 | `api/prd.py`, `api/test_prd.py` | Siklus dan rujukan hilang terdeteksi; urutan topologis stabil |
| T04 | Helper `call_model_json()`: buang pagar kode, parse JSON, satu kali perbaikan | | `api/chat.py`, `api/test_chat.py` | Diuji dengan model palsu: JSON valid, JSON rusak lalu diperbaiki, JSON tetap rusak |
| T05 | System instruction per tahap (ide, plan, tasks) | T01 | `api/prd_instruction.py`, `api/test_prd.py` | Contoh JSON di instruksi lolos validasi T01; panjang < 8.000 karakter |
| T06 | Endpoint `POST /api/prd/idea` | T04, T05 | `api/index.py`, `api/test_prd.py` | 200 dengan model palsu; 400 untuk input kosong; 429 dari limiter |
| T07 | Endpoint `POST /api/prd/plan` dengan validasi DDL dan use case | T04, T05 | `api/index.py`, `api/prd.py` | DDL salah memicu satu perbaikan; error sisa muncul di `checks` |
| T08 | Endpoint `POST /api/prd/tasks` dengan validator T03 | T03, T04, T05 | `api/index.py` | Siklus memicu satu perbaikan; hasil urut topologis |
| T09 | Endpoint `POST /api/prd/markdown` | T02 | `api/index.py` | Mengembalikan markdown dan nama file ber-slug |
| T10 | Tab "PRD" dan formulir input wajib | | `src/App.jsx`, `src/components/PrdMode.jsx` | Validasi field di klien; draf tersimpan di localStorage dengan try/catch |
| T11 | Tampilan tahap 1 sampai 3 dengan edit di tempat | T06, T07, T08, T10 | `src/components/PrdMode.jsx`, `src/components/PrdStage.jsx` | Mengulang tahap 1 menandai tahap 2 dan 3 "perlu dibuat ulang" |
| T12 | Tombol "Buat ERD dari PRD" dan "Buat Use Case dari PRD" | T11 | `src/components/PrdMode.jsx` | Hasil tampil di `OutputPanel` yang sudah ada |
| T13 | Unduh dan salin Markdown | T09, T11 | `src/components/PrdMode.jsx` | File `PRD-<slug>.md` terunduh; isi sama dengan respons T09 |
| T14 | Halaman Panduan: bagian PRD | T11 | `src/components/GuideMode.jsx` | Menjelaskan alur tiga tahap dan batasannya |
| T15 | Uji klik di browser sungguhan (light, dark, 375px) | T12, T13 | (skrip uji di luar repo) | Semua langkah lulus; tanpa scroll horizontal; target sentuh 44px |
| T16 | Uji dengan model asli (Gemini lewat `.env`) untuk dua ide contoh | T12 | (manual) | DDL lolos `parse_sql()`, use case tanpa error, task tanpa siklus |

---

## 10. Keputusan yang Perlu Dikonfirmasi

Dipakai saat implementasi: tab baru PRD, bahasa ikut isian (default Indonesia), batas task 25/30/40 (pemula/menengah/pro), model sama dengan chatbot, ekspor Markdown saja.

1. **Letak fitur:** tab baru **PRD** (usulan dokumen ini), atau bagian dari tab Teks UML?
2. **Bahasa output:** selalu Indonesia, atau ikut bahasa input?
3. **Jumlah task:** batas atas per PRD, usulan 25 untuk pemula dan 40 untuk pro.
4. **Model:** pakai `AI_MODEL` yang sama dengan chatbot, atau variabel terpisah (`PRD_AI_MODEL`) supaya bisa memakai model yang lebih kuat untuk tahap 2 dan 3?
5. **Ekspor tambahan:** perlu .docx untuk laporan skripsi di versi berikutnya?

---

## 11. Kriteria Penerimaan

- [ ] Ketiga tahap berjalan dari formulir sampai file `PRD-<slug>.md` terunduh.
- [ ] DDL di PRD lolos `parse_sql()` dan menghasilkan ERD, Class Diagram, dan Kamus Data lewat tombol "Buat ERD dari PRD".
- [ ] Teks use case di PRD menghasilkan Use Case Diagram tanpa error baris.
- [ ] Task atomik tidak punya siklus maupun rujukan ke id yang tidak ada, dan urut topologis.
- [ ] Setiap PRD punya bagian "Asumsi dan Pertanyaan Terbuka".
- [ ] Semua test backend lulus, lint bersih, dan uji klik browser lulus di mode terang, gelap, dan lebar 375px.
