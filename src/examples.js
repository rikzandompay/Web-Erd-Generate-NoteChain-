// frontend/src/examples.js
// Example texts and syntax notes per diagram type, shared by the editor and the guide.

export const EXAMPLES = {
  usecase: `=== Sistem Informasi Perpustakaan
system Perpustakaan {
  [Input]
  (Login Petugas)
  (Input Data Anggota)
  (Input Data Buku)
  [Proses]
  (Proses Peminjaman Buku)
  (Proses Pengembalian Buku)
  (Hitung Denda)
  [Output]
  (Cetak Laporan Peminjaman)
  (Lihat Katalog Buku)
}

actor Petugas
actor Anggota
actor Pembayaran <<sekunder>>

Petugas --> (Login Petugas)
Petugas --> (Input Data Anggota)
Petugas --> (Input Data Buku)
Petugas --> (Proses Peminjaman Buku)
Petugas --> (Proses Pengembalian Buku)
Petugas --> (Cetak Laporan Peminjaman)
Anggota --> (Lihat Katalog Buku)
Pembayaran --> (Hitung Denda)
`,
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

export const SYNTAX = {
  usecase: [
    ['=== Nama Halaman', 'mulai diagram baru di halaman sendiri'],
    ['system Nama { ... }', 'batas sistem berisi use case, satu per baris'],
    ['[Input] [Proses] [Output]', 'label kelompok di dalam system; use case di bawahnya masuk kelompok itu'],
    ['(Input Data Buku)', 'use case, diawali kata kerja'],
    ['actor Admin', 'aktor utama, digambar di kiri'],
    ['actor Bank <<sekunder>>', 'aktor sekunder atau sistem eksternal, digambar di kanan'],
    ['Admin --> (Input Data Buku)', 'hubungan aktor dengan use case'],
  ],
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
