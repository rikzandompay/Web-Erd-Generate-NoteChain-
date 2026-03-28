-- 1. Membuat Tabel Pelanggan
CREATE TABLE pelanggan (
    id_pelanggan INT AUTO_INCREMENT PRIMARY KEY,
    nama VARCHAR(100) NOT NULL,
    email VARCHAR(100) NOT NULL UNIQUE,
    no_telepon VARCHAR(20) NOT NULL,
    password VARCHAR(255) NOT NULL
);

-- 2. Membuat Tabel Studio
CREATE TABLE studio (
    id_studio INT AUTO_INCREMENT PRIMARY KEY,
    nama_studio VARCHAR(100) NOT NULL,
    jenis_studio ENUM('Podcast', 'Foto') NOT NULL,
    harga_per_jam DECIMAL(10, 2) NOT NULL,
    kapasitas INT NOT NULL,
    deskripsi TEXT
);

-- 3. Membuat Tabel Fasilitas (Opsional/Add-ons)
CREATE TABLE fasilitas (
    id_fasilitas INT AUTO_INCREMENT PRIMARY KEY,
    nama_fasilitas VARCHAR(100) NOT NULL,
    harga DECIMAL(10, 2) NOT NULL,
    satuan VARCHAR(50) NOT NULL -- Contoh: 'Per Jam', 'Per Sesi', 'Per Item'
);

-- 4. Membuat Tabel Pemesanan
CREATE TABLE pemesanan (
    id_pemesanan INT AUTO_INCREMENT PRIMARY KEY,
    id_pelanggan INT NOT NULL,
    tanggal_pesan DATETIME DEFAULT CURRENT_TIMESTAMP,
    total_harga DECIMAL(12, 2) DEFAULT 0.00,
    status_pesanan ENUM('Pending', 'Sukses', 'Batal') DEFAULT 'Pending',
    FOREIGN KEY (id_pelanggan) REFERENCES pelanggan(id_pelanggan) ON DELETE RESTRICT ON UPDATE CASCADE
);

-- 5. Membuat Tabel Detail Studio (Sewa Ruangan)
CREATE TABLE detail_studio (
    id_detail_studio INT AUTO_INCREMENT PRIMARY KEY,
    id_pemesanan INT NOT NULL,
    id_studio INT NOT NULL,
    tanggal_sewa DATE NOT NULL,
    waktu_mulai TIME NOT NULL,
    waktu_selesai TIME NOT NULL,
    subtotal_studio DECIMAL(10, 2) NOT NULL,
    FOREIGN KEY (id_pemesanan) REFERENCES pemesanan(id_pemesanan) ON DELETE CASCADE ON UPDATE CASCADE,
    FOREIGN KEY (id_studio) REFERENCES studio(id_studio) ON DELETE RESTRICT ON UPDATE CASCADE
);

-- 6. Membuat Tabel Detail Fasilitas (Sewa Alat/Jasa Tambahan)
CREATE TABLE detail_fasilitas (
    id_detail_fasilitas INT AUTO_INCREMENT PRIMARY KEY,
    id_pemesanan INT NOT NULL,
    id_fasilitas INT NOT NULL,
    kuantitas INT DEFAULT 1,
    subtotal_fasilitas DECIMAL(10, 2) NOT NULL,
    FOREIGN KEY (id_pemesanan) REFERENCES pemesanan(id_pemesanan) ON DELETE CASCADE ON UPDATE CASCADE,
    FOREIGN KEY (id_fasilitas) REFERENCES fasilitas(id_fasilitas) ON DELETE RESTRICT ON UPDATE CASCADE
);

-- 7. Membuat Tabel Pembayaran
CREATE TABLE pembayaran (
    id_pembayaran INT AUTO_INCREMENT PRIMARY KEY,
    id_pemesanan INT NOT NULL,
    waktu_bayar DATETIME DEFAULT CURRENT_TIMESTAMP,
    metode_pembayaran ENUM('Transfer Bank', 'E-Wallet', 'Kartu Kredit', 'Cash') NOT NULL,
    jumlah_bayar DECIMAL(12, 2) NOT NULL,
    status_pembayaran ENUM('Belum Dibayar', 'Lunas', 'Gagal') DEFAULT 'Belum Dibayar',
    FOREIGN KEY (id_pemesanan) REFERENCES pemesanan(id_pemesanan) ON DELETE CASCADE ON UPDATE CASCADE
);