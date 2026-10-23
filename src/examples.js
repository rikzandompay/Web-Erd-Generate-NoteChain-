// frontend/src/examples.js
// Example texts and syntax notes per diagram type, shared by the editor and the guide.

export const EXAMPLES = {
  usecase: `=== Sistem Informasi Perpustakaan
system Perpustakaan <<subsystem>> {
  (Login Petugas)
  (Input Data Buku)
  (Proses Peminjaman)
  (Proses Pengembalian)
  (Cari Katalog Buku)
  (Pinjam Buku Online)
  (Bayar Denda)
}

actor Petugas
actor Anggota
actor Bank <<sekunder>>

Petugas --> (Login Petugas)
Petugas --> (Input Data Buku)
Petugas --> (Proses Peminjaman)
Petugas --> (Proses Pengembalian)
Anggota --> (Cari Katalog Buku)
Anggota --> (Pinjam Buku Online)
Anggota --> (Bayar Denda)
Bank --> (Bayar Denda)
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
    ['system Nama { ... }', 'kotak sistem (proses) berisi use case, satu per baris'],
    ['system Nama <<subsystem>> {', 'sama, dengan tulisan «subsystem» di atas nama'],
    ['(Tarik Tunai)', 'use case, 2 sampai 3 kata diawali kata kerja'],
    ['actor Nasabah', 'aktor utama (input), digambar di kiri'],
    ['actor Bank <<sekunder>>', 'aktor sekunder (output), digambar di kanan'],
    ['Nasabah --> (Tarik Tunai)', 'hubungan aktor dengan use case, juga untuk aktor sekunder'],
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
