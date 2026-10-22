# PRD — Generator UML ke draw.io: Sequence, Activity & Class Diagram

| | |
|---|---|
| Status | Draft v1 |
| Tanggal | 23 Oktober 2026 |
| Referensi visual | `SPEC.md` + gambar `01`–`05` di folder `uml-reference/` |
| Output | File `.drawio` (XML mxGraph) yang bisa langsung dibuka di app.diagrams.net |

---

## 1. Latar belakang

Web generator saat ini sudah bisa mengubah input menjadi XML draw.io, tetapi hasilnya **belum rapi**: elemen saling menimpa, garis miring/menembus kotak, jarak tidak konsisten, sehingga masih harus dirapikan manual di draw.io.

Target pengguna adalah mahasiswa/penyedia jasa dokumentasi UML (skripsi, tugas, laporan sistem) yang butuh **banyak diagram sekaligus** (satu per fitur/use case) dengan gaya seragam, seperti contoh di video referensi.

## 2. Tujuan

1. Menambah / memperbaiki tiga jenis diagram: **Sequence Diagram**, **Activity Diagram**, **Class Diagram**.
2. Hasil generate **langsung rapi** saat dibuka di draw.io — tanpa perlu Arrange/geser manual.
3. Satu kali generate bisa menghasilkan **banyak halaman (page/tab)** dalam satu file `.drawio`, satu diagram per halaman (contoh: `login`, `logout`, `tambah stok bahan`, `edit data stok bahan`, …).

### Bukan tujuan (v1)
- Editor diagram visual di web (cukup preview + download).
- Diagram lain (use case, ERD, deployment). ERD Chen boleh menyusul di v2 — aturannya sudah ada di `SPEC.md`.
- Generate otomatis dari source code (reverse engineering).

## 3. Alur pengguna

1. Pengguna memilih jenis diagram: Sequence / Activity / Class.
2. Pengguna menulis/menempel input teks (format di §5). Bisa berisi **beberapa diagram sekaligus**.
3. Klik **Generate** → muncul preview + daftar halaman yang terbentuk + pesan error per baris jika ada sintaks salah.
4. Klik **Download .drawio** atau **Buka di draw.io**.
5. Opsi tema: **Terang** (default) / **Gelap**.

## 4. Arsitektur yang diharapkan

```
Input teks ──► Parser ──► Model (JSON) ──► Layout engine ──► Renderer XML draw.io ──► .drawio
```

- **Parser** per jenis diagram, menghasilkan model JSON yang bersih (tanpa koordinat).
- **Layout engine** terpisah dari renderer: hanya menghitung `x, y, width, height` dan titik garis. Semua angka **dibulatkan ke grid 10**.
- **Renderer** hanya menerjemahkan model + koordinat menjadi `<mxCell>`. Style disimpan sebagai konstanta (lihat §6–§8), bukan ditulis berulang-ulang.
- Jika web sudah punya format input sendiri, **pertahankan** dan cukup sesuaikan parser ke model JSON di bawah.

## 5. Format input (usulan)

Sintaks dibuat mirip PlantUML agar mudah ditulis tangan maupun dihasilkan AI. Beberapa diagram dipisah dengan baris `=== Nama Halaman`.

### 5.1 Sequence

```
=== Edit Data Stok Bahan
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
```

- `->` = pesan (garis solid), `-->` = balasan (garis putus-putus), `A -> A : x` = self-call.
- Opsional: `alt kondisi` / `else` / `end` dan `loop kondisi` / `end` (fragment).
- Nomor pesan (`1.`, `2.`, …) **ditambahkan otomatis**.

Model JSON:
```json
{ "type": "sequence", "title": "Edit Data Stok Bahan",
  "participants": [{ "id": "Admin", "kind": "actor" }, { "id": "Sistem", "kind": "boundary" }],
  "messages": [{ "from": "Admin", "to": "Sistem", "label": "Mengklik Tombol Edit", "kind": "sync" },
               { "from": "Sistem", "to": "Admin", "label": "Menampilkan Form Edit", "kind": "return" }],
  "fragments": [] }
```

### 5.2 Activity (dengan swimlane)

```
=== Login
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
```

- `|Nama|` = pindah swimlane, `start` / `stop`, `:aksi;`, `if/else/endif` (decision + merge), `fork` / `fork again` / `end fork` (paralel).
- `-> Nama aksi` = panah kembali ke aksi sebelumnya (loop).

### 5.3 Class

```
=== Class Diagram
class bahan {
  - id : int
  - nama_bahan : varchar
  - satuan : varchar
  - created_at : timestamp
  + create()
  + update()
  + delete()
}
class stok_masuk { ... }

bahan "1" -- "0..*" stok_masuk
menu "1" -- "0..*" menu_bahan
bahan <|-- bahan_kering      ' inheritance
order *-- order_item         ' komposisi
order o-- customer           ' agregasi
order ..> payment            ' dependency
```

## 6. Kebutuhan — Sequence Diagram

Referensi: `03-sequence-edit.png`, `04-sequence-other.png`, `05-sequence-closeup.png`.

| ID | Kebutuhan |
|---|---|
| SEQ-1 | Semua diagram dibungkus **frame** (`shape=umlFrame`) dengan label kiri atas `sd <Judul>`. Padding frame sama di semua sisi (≥ 30px). |
| SEQ-2 | Participant tampil sebagai header kotak (atau ikon aktor untuk `actor`), **sejajar satu baris di atas**. |
| SEQ-3 | Jarak antar lifeline dihitung dari **label pesan terpanjang** di antara dua lifeline bersebelahan (min 160px), supaya label tidak terpotong / menimpa lifeline lain. |
| SEQ-4 | Garis lifeline putus-putus memanjang sampai bawah pesan terakhir + 40px. |
| SEQ-5 | **Activation bar** (kotak tipis, lebar 10px) pada participant yang sedang aktif: mulai saat menerima pesan, selesai saat mengirim balasan terakhirnya. Participant `actor` tidak diberi activation bar. |
| SEQ-6 | Pesan **dinomori otomatis** dan jarak vertikal antar pesan **sama** (default 40px; tambah 16px per baris tambahan jika label di-wrap). |
| SEQ-7 | Pesan biasa: garis solid, kepala panah penuh (`endArrow=block`). Balasan: garis putus-putus, kepala panah terbuka (`dashed=1;endArrow=open`). |
| SEQ-8 | Semua panah **lurus horizontal** (y awal = y akhir), mulai/berakhir tepat di tepi activation bar, **tidak menembus** lifeline yang dilewati. |
| SEQ-9 | Label pesan di atas garis, rata tengah, maksimal lebar = jarak dua lifeline − 20px; selebihnya wrap ke baris baru. |
| SEQ-10 | Self-call: panah berbentuk kotak kecil ke kanan lalu kembali ke lifeline yang sama, dengan activation bar bertingkat. |
| SEQ-11 | Fragment `alt` / `loop`: kotak `shape=umlFrame` dengan label (`alt`, `loop`) dan kondisi `[kondisi]`, garis pemisah putus-putus antar cabang `alt`. |

Style draw.io yang disarankan:
```
lifeline : shape=umlLifeline;perimeter=lifelinePerimeter;whiteSpace=wrap;html=1;container=1;dropTarget=0;collapsible=0;recursiveResize=0;outlineConnect=0;portConstraint=eastwest;size=40;
actor    : shape=umlLifeline;participant=umlActor;perimeter=lifelinePerimeter;whiteSpace=wrap;html=1;container=1;dropTarget=0;collapsible=0;recursiveResize=0;outlineConnect=0;portConstraint=eastwest;verticalAlign=top;spacingTop=36;labelBackgroundColor=none;size=40;
activasi : html=1;points=[];perimeter=orthogonalPerimeter;outlineConnect=0;targetShapes=umlLifeline;portConstraint=eastwest;
pesan    : html=1;verticalAlign=bottom;endArrow=block;curved=0;rounded=0;
balasan  : html=1;verticalAlign=bottom;endArrow=open;dashed=1;endSize=8;curved=0;rounded=0;
frame    : shape=umlFrame;whiteSpace=wrap;html=1;pointerEvents=0;width=160;height=30;
```

Catatan implementasi: edge pesan sebaiknya menyimpan koordinat **absolut** lewat `<mxPoint as="sourcePoint">` dan `<mxPoint as="targetPoint">` (dengan `y` sama persis), supaya draw.io tidak membelokkan garis.

## 7. Kebutuhan — Activity Diagram

| ID | Kebutuhan |
|---|---|
| ACT-1 | Setiap aktor/sistem menjadi **swimlane vertikal** (kolom) bersebelahan, header di atas, lebar kolom sama (default 260px), tinggi kolom sama. Seluruh swimlane dibungkus satu pool dengan judul diagram. |
| ACT-2 | Node: **start** (lingkaran penuh), **stop** (lingkaran penuh dengan cincin), **aksi** (persegi panjang sudut membulat, lebar 180, tinggi min 40, teks wrap), **decision/merge** (belah ketupat 40×40), **fork/join** (batang tebal horizontal). |
| ACT-3 | Node diletakkan di **tengah kolom swimlane**-nya. Alur utama berjalan dari atas ke bawah, jarak vertikal antar node sama (default 30px celah). |
| ACT-4 | Setiap langkah mendapat **baris (rank) sendiri**, termasuk saat pindah swimlane, sehingga garis antar-kolom selalu turun, tidak naik/menyilang. |
| ACT-5 | Semua garis **orthogonal** (`edgeStyle=orthogonalEdgeStyle`), panah di ujung, tidak menembus node lain. |
| ACT-6 | Decision: label kondisi (`[ya]` / `[tidak]`) di dekat garis keluar. Cabang "ya" lurus ke bawah, cabang lain keluar dari sisi kanan/kiri. Cabang bertemu kembali di node merge sebelum lanjut. |
| ACT-7 | Panah loop (kembali ke aksi sebelumnya) keluar dari sisi samping dan naik melalui jalur di luar node, tidak menimpa garis lain. |
| ACT-8 | Fork/join: batang selebar cabang-cabangnya, cabang paralel diletakkan berdampingan. |

Style yang disarankan:
```
start    : ellipse;html=1;shape=startState;
stop     : ellipse;html=1;shape=endState;
aksi     : rounded=1;whiteSpace=wrap;html=1;arcSize=40;
decision : rhombus;whiteSpace=wrap;html=1;
fork     : shape=line;html=1;strokeWidth=6;
swimlane : swimlane;html=1;startSize=30;horizontal=1;
edge     : edgeStyle=orthogonalEdgeStyle;html=1;rounded=0;endArrow=open;endSize=8;
```

## 8. Kebutuhan — Class Diagram

Referensi: `01-class-diagram.png`.

| ID | Kebutuhan |
|---|---|
| CLS-1 | Setiap kelas = kotak 3 bagian: **nama** (tebal, tengah), **atribut**, garis pemisah, **method**. Dibuat sebagai `swimlane` dengan child per baris, supaya tetap bisa diedit per baris di draw.io. |
| CLS-2 | Lebar kelas = teks terpanjang + padding (min 160px), tinggi baris 26px, tinggi kelas mengikuti jumlah baris. |
| CLS-3 | Penempatan memakai **layout berbasis graf** (mis. layered/Sugiyama atau ELK/dagre): kelas dengan relasi terbanyak di tengah, kelas yang berelasi berdekatan. Kelas tanpa relasi dikumpulkan di kolom paling kanan. |
| CLS-4 | Jarak antar kelas konsisten (min 60px horizontal, 60px vertikal). **Tidak ada kelas yang bertumpuk.** |
| CLS-5 | Garis relasi **orthogonal**, keluar dari sisi kotak yang paling dekat ke target, titik keluar dibagi rata jika satu sisi punya beberapa garis (tidak menumpuk di satu titik). |
| CLS-6 | Multiplicity (`1`, `0..*`, `1..*`) ditampilkan kecil di dekat ujung garis masing-masing, tidak menimpa kotak. |
| CLS-7 | Jenis relasi: asosiasi (garis biasa), inheritance (`endArrow=block;endFill=0`), komposisi (`startArrow=diamondThin;startFill=1`), agregasi (`startArrow=diamondThin;startFill=0`), dependency (`dashed=1;endArrow=open`). |

Style yang disarankan:
```
kelas    : swimlane;fontStyle=1;align=center;verticalAlign=top;childLayout=stackLayout;horizontal=1;startSize=26;horizontalStack=0;resizeParent=1;resizeParentMax=0;resizeLast=0;collapsible=0;marginBottom=0;html=1;
baris    : text;strokeColor=none;fillColor=none;align=left;verticalAlign=top;spacingLeft=4;spacingRight=4;overflow=hidden;rotatable=0;points=[[0,0.5],[1,0.5]];portConstraint=eastwest;html=1;
pemisah  : line;strokeWidth=1;fillColor=none;align=left;verticalAlign=middle;spacingTop=-1;spacingLeft=3;spacingRight=3;rotatable=0;labelPosition=right;points=[];portConstraint=eastwest;
relasi   : edgeStyle=orthogonalEdgeStyle;html=1;rounded=0;endArrow=none;
```

## 9. Kebutuhan umum

| ID | Kebutuhan |
|---|---|
| GEN-1 | Satu file `.drawio` bisa berisi banyak `<diagram name="...">` (halaman), satu per blok `===`. |
| GEN-2 | Semua koordinat dan ukuran kelipatan 10. |
| GEN-3 | Urutan layer: garis di belakang, kotak di depan. |
| GEN-4 | Tema: **jangan hardcode warna hitam/putih** di style. Biarkan default draw.io agar otomatis cocok di mode terang maupun gelap. Opsi "Gelap" hanya mengatur `background` halaman. |
| GEN-5 | Font seragam (Helvetica 12, judul 14 tebal). |
| GEN-6 | Error parser menyebut **nomor baris** dan alasannya, dan tidak menghentikan halaman lain. |
| GEN-7 | Generate 30 halaman sekaligus selesai < 2 detik di browser. |

## 10. Kriteria penerimaan

Fitur dianggap selesai jika, untuk contoh input di §5:

- [ ] File terbuka di app.diagrams.net tanpa error, semua halaman muncul sebagai tab.
- [ ] **Tidak ada** kotak yang saling menimpa dan tidak ada garis yang menembus kotak (dicek otomatis lewat tes bounding box).
- [ ] Sequence: semua panah horizontal, nomor urut benar, balasan putus-putus, activation bar sesuai rentang pesan, semua di dalam frame.
- [ ] Activity: setiap node berada di swimlane yang benar, alur selalu turun, decision bercabang dan bertemu kembali.
- [ ] Class: 10 kelas dengan 12 relasi tersusun tanpa tumpang tindih, garis orthogonal, multiplicity terbaca.
- [ ] Tampilan terlihat rapi di mode terang **dan** gelap draw.io.
- [ ] Hasil visual sebanding dengan gambar referensi `01`–`05`.

## 11. Rencana pengerjaan

1. **Refactor**: pisahkan parser → model → layout → renderer (§4).
2. **Sequence Diagram** (paling sering dipakai): SEQ-1 s/d SEQ-9, lalu self-call dan fragment.
3. **Class Diagram**: integrasi layout graf + routing garis orthogonal.
4. **Activity Diagram**: swimlane + ranking + decision/merge, lalu fork/join dan loop.
5. Multi-halaman, tema, pesan error, tes otomatis "tidak ada overlap".

## 12. Pertanyaan terbuka

1. Format input yang dipakai web sekarang apa? Kalau sudah ada, parser di §5 disesuaikan, bukan diganti.
2. Web dibangun dengan stack apa (HTML/JS murni, React, PHP)? Ini menentukan library layout yang dipilih (mis. `elkjs` / `dagre` untuk class diagram).
3. Apakah perlu "generate dari deskripsi bahasa biasa" via AI (mis. "buat sequence edit stok bahan")? Bisa jadi fitur v2 yang menghasilkan teks format §5.
