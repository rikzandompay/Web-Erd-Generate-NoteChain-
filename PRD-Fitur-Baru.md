# PRD — Penambahan Fitur Software Engineering: Use Case Diagram, Kamus Data SQL & AI Chatbot

| Metadata | Keterangan |
|---|---|
| **Dokumen** | Product Requirements Document (PRD) — Ekstensi Fitur v2 |
| **Status** | Ready for Implementation |
| **Tanggal** | 23 Oktober 2026 |
| **Pemilik Proyek** | Rikzan |
| **Stack** | Python (FastAPI, Layout Engine, Parser) + React (Vite, Tailwind, Draw.io Viewer) |
| **Target Output** | File `.drawio` multi-page (Chen ERD, Use Case, Sequence, Activity, Class) & Kamus Data |

---

## 1. Latar Belakang & Rasional

Aplikasi **ERD Generator by Rikzan** saat ini telah berhasil mengimplementasikan:
1. **ERD Notasi Chen** dari file SQL DDL.
2. **Sequence Diagram**, **Activity Diagram (Swimlane)**, dan **Class Diagram** dari sintaks teks berbasis halaman (`=== Nama Halaman`).

Dalam standar dokumentasi Software Engineering (RPL/SDLC, SRS IEEE 830, maupun skripsi informatika/sistem informasi), ada 2 artefak esensial yang masih kurang:
1. **Use Case Diagram**: Diagram fungsional utama yang wajib ada sebelum melangkah ke Sequence & Activity Diagram.
2. **Kamus Data (Data Dictionary)**: Tabel rincian atribut basis data yang selalu menyertai ERD dalam bab perancangan basis data.
3. **AI Prompt-to-Diagram (`/api/chat`)**: Memungkinkan pengguna mengetik deskripsi sistem dalam bahasa Indonesia sehari-hari, lalu otomatis di-generate menjadi teks diagram UML dan langsung ter-render di canvas draw.io.

---

## 2. Ruang Lingkup Fitur Baru

```
┌────────────────────────────────────────────────────────────────────────┐
│                          FITUR BARU v2                                 │
├──────────────────────────────┬─────────────────────────────────────────┤
│ 1. Use Case Diagram          │ Input teks ➔ Draw.io System Boundary    │
│ 2. Kamus Data Generator      │ File .sql  ➔ Tabel Draw.io & Markdown   │
│ 3. AI Natural Language       │ Chat teks  ➔ Auto Generate UML/ERD      │
│ 4. Ekspor Vektor SVG & PNG   │ Canvas     ➔ Download Gambar Tanpa Pecah│
└──────────────────────────────┴─────────────────────────────────────────┘
```

---

## 3. Spesifikasi Fitur 1: Use Case Diagram Generator

### 3.1 Format Input Teks
Sintaks menggunakan format ringkas ramah teks dan PlantUML-compatible:

```text
=== Sistem Informasi Perpustakaan
system Perpustakaan {
  (Login Petugas)
  (Kelola Anggota)
  (Peminjaman Buku)
  (Pengembalian Buku)
  (Katalog Pencarian)
  (Hitung Denda)
  (Cetak Laporan)
}

actor Petugas
actor Anggota

Petugas --> (Login Petugas)
Petugas --> (Kelola Anggota)
Petugas --> (Peminjaman Buku)
Petugas --> (Pengembalian Buku)
Petugas --> (Cetak Laporan)

Anggota --> (Katalog Pencarian)
Anggota --> (Peminjaman Buku)

(Peminjaman Buku) ..> (Login Petugas) : <<include>>
(Pengembalian Buku) ..> (Hitung Denda) : <<extend>>
```

### 3.2 Aturan Sintaks & Elemen
* `system <Nama Sistem> { ... }`: Membungkus use case ke dalam *System Boundary* (kotak persegi panjang dengan judul di atas).
* `(Nama Use Case)`: Dibuat sebagai elips (`shape=ellipse;whiteSpace=wrap;html=1;`).
* `actor <Nama Aktor>`: Dibuat sebagai ikon aktor UML (`shape=umlActor;verticalLabelPosition=bottom;...`).
* Relasi:
  * Asosiasi biasa: `Aktor --> (Use Case)` (garis lurus solid tanpa panah atau panah terbuka tipis).
  * `<<include>>`: `(UC 1) ..> (UC 2) : <<include>>` (garis putus-putus berarah + label `<<include>>`).
  * `<<extend>>`: `(UC 1) ..> (UC 2) : <<extend>>` (garis putus-putus berarah + label `<<extend>>`).
  * Generalisasi aktor/UC: `Admin <|-- SuperAdmin` (garis panah segitiga kosong).

### 3.3 Layout Rules
* Aktor primer ditempatkan di sisi kiri di luar kotak sistem.
* Aktor sekunder / sistem eksternal ditempatkan di sisi kanan di luar kotak sistem.
* Use case disusun di dalam kotak sistem secara bertingkat vertikal dengan jarak seimbang (min 30px jarak antar elips).
* Lebar elips use case fleksibel mengikuti panjang teks (min 140px, tinggi min 60px).
* Garis asosiasi tidak boleh memotong teks use case lain.

---

## 4. Spesifikasi Fitur 2: Kamus Data (Data Dictionary) Generator dari SQL

Fitur ini memanfaatkan `sql_parser.py` yang sudah ada untuk mengekstrak metadata tabel dan menampilkannya dalam format tabel rapi.

### 4.1 Kolom Kamus Data
Setiap tabel SQL menghasilkan tabel dokumentasi dengan kolom:
1. **No** (Nomor urut kolom)
2. **Nama Kolom** (e.g. `user_id`, `created_at`)
3. **Tipe Data** (e.g. `VARCHAR(100)`, `BIGINT UNSIGNED`)
4. **Kunci (Key)**: `PK` (Primary Key), `FK -> tabel.kolom` (Foreign Key), atau kosong.
5. **Null**: `Ya` (NULL) atau `Tidak` (NOT NULL).
6. **Default**: Nilai bawaan jika ada.
7. **Keterangan**: Deskripsi/kegunaan field.

### 4.2 Output & Integrasi UI
* **Tab Halaman Baru di Draw.io**: Halaman draw.io tersendiri bernama `Kamus Data` dengan format tabel grid rapi.
* **Fitur Quick Copy**: Tombol di web untuk "Salin Markdown" atau "Salin CSV" agar bisa langsung ditempel ke laporan skripsi/dokumen Word.

---

## 5. Spesifikasi Fitur 3: AI Prompt-to-Diagram (`/api/chat`)

### 5.1 Alur Kerja
1. Pengguna membuka tab diagram (Sequence, Activity, Class, atau Use Case).
2. Terdapat panel asisten AI: *"Ketik skenario alur fitur Anda..."*.
3. Pengguna mengetik kalimat bahasa Indonesia:
   > *"Buatkan activity diagram untuk fitur pendaftaran relawan donor darah, ada validasi usia minimal 17 tahun dan cek HB darah."*
4. Backend mengirim instruksi terformat ke model AI yang terhubung ke 9Router / OpenRouter via `AI_BASE_URL` dan `AI_API_KEY`.
5. Model AI mengembalikan sintaks teks diagram yang valid.
6. Editor teks otomatis terisi, langsung diparse, dan diagram langsung muncul di preview.

### 5.2 Standar Konfigurasi Environment (`.env`)
Backend otomatis memuat variabel dari `.env` root:
```env
AI_BASE_URL=http://localhost:20128/v1
AI_API_KEY=isi-dengan-key-kamu-di-file-.env-bukan-di-sini
AI_MODEL=kr/auto
```

---

## 6. Spesifikasi Fitur 4: Ekspor Vektor SVG & PNG

* **Kebutuhan**: Mahasiswa/engineer sering kesulitan mengambil gambar berkualitas tinggi langsung dari draw.io.
* **Fitur**:
  * Tombol **"Unduh PNG (Resolusi Tinggi)"** (skala 2x atau 3x untuk laporan/skripsi).
  * Tombol **"Unduh SVG"** (vektor tanpa pecah untuk presentasi).
  * Tombol **"Salin Kode Mermaid"** (opsional untuk dokumentasi README GitHub).

---

## 7. Rencana Pengerjaan & Milestone

| Tahap | Aktivitas | Estimasi |
|---|---|---|
| **Milestone 1** | Aktifkan konfigurasi `.env` dan validasi endpoint `/api/chat` dengan model 9Router lokal. | Selesai / Siap |
| **Milestone 2** | Buat parser & renderer `api/usecase.py` untuk Use Case Diagram + registrasi di `DIAGRAM_BUILDERS`. | Sprint 1 |
| **Milestone 3** | Buat `api/data_dictionary.py` untuk mengekstrak kamus data dari SQL schema + generator tabel Draw.io. | Sprint 1 |
| **Milestone 4** | Update UI React (`Tabs`, `UmlTextMode`, opsi Kamus Data pada `SqlMode`). | Sprint 2 |
| **Milestone 5** | Tambahkan fitur export PNG/SVG dari renderer preview. | Sprint 2 |

---

## 8. Kriteria Penerimaan (Acceptance Criteria)

- [ ] Sintaks `system { (Use Case) }` dan `actor --> (Use Case)` ter-render sempurna di Draw.io dengan System Boundary dan elips rapi.
- [ ] File SQL yang diunggah menghasilkan halaman `Kamus Data` lengkap dengan kolom PK, FK, tipe data, dan NULL constraint.
- [ ] Endpoint `/api/chat` dapat memproses input natural language tanpa error 503 saat `.env` aktif.
- [ ] Semua koordinat visual tetap mematuhi aturan kelipatan grid 10px dan ramah dark/light mode draw.io.
