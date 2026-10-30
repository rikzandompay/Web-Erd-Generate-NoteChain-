# backend/relation_names.py
"""
The verb in an ERD relationship diamond, in Indonesian, read as
"<parent> <verb> <child>": the referenced table acts on the table that holds
the foreign key (supplier memasok barang_masuk, pengguna menulis artikel).

Most specific evidence first:
  1. A name the author gave in the SQL (`-- @rel: memasok` on the FK column).
  2. What the FK column says about the parent's role: penulis_id → menulis,
     diverifikasi_oleh → memverifikasi, created_by → membuat.
  3. The child is a part of the parent: foto_kegiatan → kegiatan dilengkapi,
     detail_pemesanan → pemesanan terdiri atas.
  4. What kind of table the parent is (a person, a category, a supplier, a
     product, a transaction, …) together with what the child is.
  5. 'memiliki', only when none of the above says more.
"""

import html
import re

_VOWELS = 'aeiou'

# Tokens in a column name that only say "this is a key"
_KEY_TOKENS = {'id', 'fk', 'kode', 'no', 'nomor', 'key', 'ref'}


def _tokens(name: str) -> list[str]:
    """`diverifikasi_oleh` → ['diverifikasi', 'oleh'], `createdBy` → ['created', 'by']."""
    name = re.sub(r'([a-z0-9])([A-Z])', r'\1_\2', name or '')
    return [t for t in re.split(r'[^a-zA-Z0-9]+', name.lower()) if t]


def _has(tokens: list[str], joined: str, keywords: tuple[str, ...]) -> bool:
    """A keyword matches the start of a token (user → users), or the name itself when it has '_'."""
    return any(k in joined if '_' in k else any(t.startswith(k) for t in tokens) for k in keywords)


# ── Active verbs from Indonesian roots (meN- prefix) ─────────────────────────

def active_verb(root: str) -> str:
    """verifikasi → memverifikasi, catat → mencatat, setujui → menyetujui, kirim → mengirim."""
    r = root.lower()
    if not r:
        return r
    syllables = len(re.findall(r'[aeiou]', r)) - len(re.findall(r'ai|au|oi|ei', r))
    if syllables == 1:                                       # one syllable: cek → mengecek (bu-at is two)
        return 'menge' + r
    if r[0] in _VOWELS:
        return 'meng' + r
    if r.startswith(('ny', 'ng')):
        return 'me' + r
    if r.startswith('per') and len(r) > 3 and r[3] not in _VOWELS:
        return 'memper' + r[3:]                              # perbarui → memperbarui
    cluster = len(r) > 1 and r[1] not in _VOWELS             # proses, transfer, klik, syukuri
    first = r[0]
    if first in 'pbfv':
        return 'mem' + (r if cluster or first != 'p' else r[1:])
    if first in 'tdcjzs':
        if cluster:
            return 'men' + r
        if first == 't':
            return 'men' + r[1:]
        if first == 's':
            return 'meny' + r[1:]
        return 'men' + r
    if first in 'kghqx':
        return 'meng' + (r if cluster or first != 'k' else r[1:])
    return 'me' + r                                          # l, m, n, r, w, y


# ── 2. What the FK column says ───────────────────────────────────────────────

# English `<verb>_by` / `<verb>_to` columns
_BY_EN = {
    'created': 'membuat', 'updated': 'memperbarui', 'modified': 'mengubah', 'edited': 'mengubah',
    'verified': 'memverifikasi', 'validated': 'memvalidasi', 'approved': 'menyetujui',
    'rejected': 'menolak', 'recorded': 'mencatat', 'reviewed': 'menilai', 'checked': 'memeriksa',
    'inspected': 'memeriksa', 'handled': 'menangani', 'assigned': 'menangani',
    'processed': 'memproses', 'uploaded': 'mengunggah', 'published': 'menerbitkan',
    'posted': 'menerbitkan', 'written': 'menulis', 'deleted': 'menghapus',
    'confirmed': 'mengonfirmasi', 'paid': 'membayar', 'sent': 'mengirim', 'received': 'menerima',
    'owned': 'memiliki', 'managed': 'mengelola', 'signed': 'menandatangani', 'added': 'menambahkan',
    'requested': 'mengajukan', 'submitted': 'mengajukan', 'cancelled': 'membatalkan',
    'canceled': 'membatalkan', 'closed': 'menutup',
}

# Role nouns used as FK column names (penulis_id, author_id)
_AGENT = {
    'penulis': 'menulis', 'author': 'menulis', 'writer': 'menulis',
    'pembuat': 'membuat', 'creator': 'membuat', 'maker': 'membuat',
    'pemilik': 'memiliki', 'owner': 'memiliki',
    'pengirim': 'mengirim', 'sender': 'mengirim',
    'penerima': 'menerima', 'receiver': 'menerima', 'recipient': 'menerima',
    'pembeli': 'membeli', 'buyer': 'membeli',
    'penjual': 'menjual', 'seller': 'menjual',
    'peminjam': 'meminjam', 'borrower': 'meminjam',
    'pemesan': 'memesan',
    'penyewa': 'menyewa', 'tenant': 'menyewa',
    'pelapor': 'melaporkan', 'reporter': 'melaporkan',
    'penyetuju': 'menyetujui', 'approver': 'menyetujui',
    'verifikator': 'memverifikasi', 'verifier': 'memverifikasi', 'validator': 'memvalidasi',
    'pemeriksa': 'memeriksa', 'inspector': 'memeriksa',
    'penilai': 'menilai', 'reviewer': 'menilai',
    'penguji': 'menguji', 'examiner': 'menguji',
    'pengajar': 'mengajar', 'instructor': 'mengajar', 'teacher': 'mengajar',
    'pembimbing': 'membimbing', 'supervisor': 'membimbing', 'advisor': 'membimbing', 'mentor': 'membimbing',
    'pengelola': 'mengelola', 'manager': 'mengelola',
    'penanggung': 'menangani', 'pic': 'menangani', 'teknisi': 'menangani', 'technician': 'menangani',
    'dokter': 'menangani', 'doctor': 'menangani',
    'pendaftar': 'mendaftar', 'registrant': 'mendaftar',
    'pemohon': 'mengajukan', 'pengaju': 'mengajukan', 'applicant': 'mengajukan', 'requester': 'mengajukan',
    'penyedia': 'menyediakan', 'provider': 'menyediakan',
    'atasan': 'membawahi', 'induk': 'membawahi', 'parent': 'membawahi',
    'pencatat': 'mencatat', 'recorder': 'mencatat',
    'kurir': 'mengantar', 'courier': 'mengantar',
    'editor': 'menyunting', 'penyunting': 'menyunting',
}


def _from_column(column: str) -> str:
    tokens = [t for t in _tokens(column) if t not in _KEY_TOKENS]
    if 'oleh' in tokens:                                     # diverifikasi_oleh, dicatat_oleh
        passive = [t for t in tokens if t.startswith('di') and len(t) > 4]
        if passive:
            return active_verb(passive[0][2:])
    for marker in ('by', 'to'):                              # created_by, assigned_to
        if marker in tokens:
            i = tokens.index(marker)
            if i and tokens[i - 1] in _BY_EN:
                return _BY_EN[tokens[i - 1]]
    for t in tokens:
        if t in _AGENT:
            return _AGENT[t]
    return ''


# ── 3. The child is a part of the parent ─────────────────────────────────────

_PART_OF = [
    (('detail', 'rincian', 'item', 'baris', 'line'), 'terdiri atas'),
    (('foto', 'gambar', 'galeri', 'image', 'photo', 'media', 'lampiran', 'dokumen', 'berkas', 'file'),
     'dilengkapi'),
    (('riwayat', 'histori', 'history', 'log', 'jejak'), 'tercatat dalam'),
    (('komentar', 'comment', 'ulasan', 'review', 'rating', 'penilaian'), 'menerima'),
    (('jadwal', 'schedule'), 'dijadwalkan pada'),
    (('anggota', 'member', 'peserta'), 'beranggotakan'),
    (('stok', 'stock', 'persediaan'), 'tersimpan dalam'),
]


def _singular(token: str) -> str:
    return token[:-1] if len(token) > 3 and token.endswith('s') and not token.endswith('ss') else token


def _part_of(child: list[str], parent: list[str]) -> str:
    """foto_kegiatan is a part of kegiatan: the parent's name sits inside the child's."""
    c, p = [_singular(t) for t in child], [_singular(t) for t in parent]
    for i in range(len(c) - len(p) + 1):
        if c[i:i + len(p)] == p:
            extra = c[:i] + c[i + len(p):]
            for keywords, verb in _PART_OF:
                if extra and any(t.startswith(k) for t in extra for k in keywords):
                    return verb
    return ''


# ── 4. Kind of parent × kind of child ────────────────────────────────────────

# First match wins, so the more specific kinds come first
_KINDS = [
    ('category', ('kategori', 'categor', 'jenis', 'golongan', 'klasifikasi', 'kelompok', 'genre', 'tipe', 'type')),
    ('supplier', ('supplier', 'pemasok', 'vendor', 'distributor')),
    ('donor', ('donatur', 'donor', 'penyumbang', 'muzakki')),
    ('cashier', ('kasir', 'cashier')),
    ('teacher', ('dosen', 'guru', 'pengajar', 'instruktur', 'mentor', 'pembimbing', 'teacher', 'lecturer')),
    ('employee', ('karyawan', 'pegawai', 'employee', 'pekerja')),
    ('staff', ('user', 'pengguna', 'admin', 'petugas', 'operator', 'staf',
               'pustakawan', 'manajer', 'manager')),
    ('customer', ('pelanggan', 'customer', 'pembeli', 'konsumen', 'member', 'anggota', 'peminjam', 'siswa',
                  'mahasiswa', 'murid', 'pasien', 'peserta', 'penyewa', 'tamu', 'pengunjung', 'relawan',
                  'client', 'klien', 'student', 'patient')),
    ('account', ('rekening', 'bank', 'dompet', 'wallet', 'metode_pembayaran', 'payment_method', 'account')),
    ('program', ('program', 'layanan', 'proyek', 'project', 'kampanye', 'campaign')),
    ('org', ('jurusan', 'prodi', 'fakultas', 'departemen', 'department', 'divisi', 'cabang', 'branch',
             'unit', 'instansi', 'perusahaan', 'company', 'sekolah')),
    ('schedule', ('shift', 'jadwal', 'schedule', 'sesi')),
    ('room', ('kelas', 'ruang', 'kamar', 'studio', 'lapangan', 'room')),
    ('storage', ('gudang', 'rak', 'lokasi', 'warehouse')),
    ('region', ('wilayah', 'kota', 'daerah', 'provinsi', 'kecamatan', 'region')),
    ('content', ('artikel', 'article', 'berita', 'news', 'post', 'blog', 'konten', 'content', 'pengumuman')),
    ('activity', ('kegiatan', 'event', 'acara', 'ujian', 'seminar', 'pelatihan')),
    ('event', ('transaksi', 'transaction', 'keuangan', 'financ', 'jurnal', 'journal', 'mutasi',
               'pemesanan', 'pesanan', 'order', 'pembayaran', 'payment', 'penjualan', 'sale', 'pembelian',
               'purchase', 'peminjaman', 'loan', 'pengembalian', 'donasi', 'donation', 'reservasi',
               'booking', 'pendaftaran', 'registrasi', 'sewa', 'penyewaan', 'rental', 'pengiriman', 'shipment')),
    ('item', ('produk', 'product', 'barang', 'item', 'buku', 'book', 'obat', 'menu', 'snack', 'bahan',
              'aset', 'asset', 'paket', 'tiket', 'kendaraan', 'katalog')),
]

_FINANCE = ('transaksi', 'transaction', 'keuangan', 'financ', 'jurnal', 'journal', 'kas_', 'mutasi', 'ledger')
_CONTENT = ('artikel', 'article', 'berita', 'news', 'post', 'blog', 'konten', 'content', 'pengumuman')
# What staff record rather than manage
_RECORDS = _FINANCE + ('pemesanan', 'pesanan', 'order', 'pembayaran', 'payment', 'penjualan', 'sale',
                       'pembelian', 'purchase', 'peminjaman', 'loan', 'pengembalian', 'donasi', 'donation',
                       'reservasi', 'booking', 'masuk', 'keluar', 'stok', 'stock', 'log', 'riwayat',
                       'absensi', 'presensi', 'catatan', 'pengiriman', 'sewa', 'penyewaan')

# For each parent kind: (child keywords, verb), the first match wins; () always matches
_BY_KIND: dict[str, list[tuple[tuple[str, ...], str]]] = {
    'category': [((), 'mengelompokkan')],
    'supplier': [((), 'memasok')],
    'donor': [(_FINANCE, 'bertransaksi'), ((), 'memberikan')],
    'cashier': [(('penjualan', 'transaksi', 'pembayaran', 'sale', 'order', 'pesanan'), 'melayani'),
                ((), 'mencatat')],
    'teacher': [(('bimbingan', 'skripsi', 'tugas_akhir', 'thesis'), 'membimbing'),
                (('nilai', 'grade', 'ujian'), 'menilai'), ((), 'mengajar')],
    'staff': [(_CONTENT, 'menulis'), (('laporan', 'report'), 'membuat'), (('jadwal', 'schedule'), 'mengatur'),
              (_RECORDS, 'mencatat'), ((), 'mengelola')],
    # An employee is the one who clocks in, asks for leave and is paid, not the one who manages them
    'employee': [(('absensi', 'presensi', 'kehadiran', 'attendance', 'checkin', 'check_in'), 'melakukan'),
                 (('cuti', 'izin', 'leave', 'lembur', 'overtime'), 'mengajukan'),
                 (('gaji', 'penggajian', 'payroll', 'upah', 'slip'), 'menerima'),
                 (('pelatihan', 'training', 'sertifikat'), 'mengikuti'),
                 (_CONTENT, 'menulis'), (('laporan', 'report'), 'membuat'),
                 (_RECORDS, 'mencatat'), ((), 'memiliki')],
    'schedule': [(('absensi', 'presensi', 'kehadiran', 'attendance'), 'digunakan dalam'), ((), 'digunakan dalam')],
    'customer': [(('pemesanan', 'pesanan', 'order', 'booking', 'reservasi'), 'memesan'),
                 (('pembayaran', 'payment'), 'membayar'), (('peminjaman', 'loan'), 'meminjam'),
                 (('pengembalian',), 'mengembalikan'), (('pendaftaran', 'registrasi', 'enrollment'), 'mendaftar'),
                 (('pembelian', 'purchase'), 'membeli'), (('sewa', 'penyewaan', 'rental'), 'menyewa'),
                 (('ulasan', 'review', 'komentar', 'comment'), 'menulis'), (('penilaian', 'rating'), 'menilai'),
                 (('absensi', 'presensi', 'attendance', 'keranjang', 'cart'), 'mengisi'),
                 ((), 'melakukan')],
    'account': [((), 'menerima')],
    'program': [(_CONTENT, 'memuat'), ((), 'menaungi')],
    'org': [((), 'menaungi')],
    'room': [(('pemesanan', 'pesanan', 'booking', 'reservasi', 'sewa', 'penyewaan'), 'dipesan dalam'),
             (('jadwal', 'schedule'), 'digunakan dalam'), ((), 'menampung')],
    'storage': [((), 'menyimpan')],
    'region': [((), 'mencakup')],
    'content': [(('komentar', 'comment', 'ulasan', 'review'), 'menerima'),
                (('foto', 'gambar', 'image', 'media', 'lampiran'), 'dilengkapi'), ((), 'memuat')],
    'activity': [(('foto', 'gambar', 'galeri', 'dokumentasi'), 'dilengkapi'),
                 (('peserta', 'participant', 'pendaftaran', 'registrasi'), 'diikuti'),
                 (('jadwal', 'schedule'), 'dijadwalkan pada'), (('nilai', 'hasil'), 'menghasilkan'),
                 ((), 'mencakup')],
    'event': [(_FINANCE, 'tercatat sebagai'), (('detail', 'rincian', 'item'), 'terdiri atas'),
              (('pembayaran', 'payment'), 'dibayar melalui'), (('pengiriman', 'shipment'), 'dikirim melalui'),
              (('pengembalian',), 'dikembalikan melalui'), (('foto', 'gambar', 'dokumentasi'), 'dilengkapi'),
              ((), 'menghasilkan')],
    'item': [(('peminjaman', 'loan'), 'dipinjam dalam'), (('penjualan', 'sale'), 'terjual dalam'),
             (('pemesanan', 'pesanan', 'order', 'keranjang', 'cart', 'booking'), 'dipesan dalam'),
             (('sewa', 'penyewaan', 'rental'), 'disewa dalam'),
             (('ulasan', 'review', 'rating', 'komentar'), 'menerima'),
             (('foto', 'gambar', 'image'), 'dilengkapi'), ((), 'tercatat pada')],
}


def _kind(tokens: list[str]) -> str:
    joined = '_'.join(tokens)
    for kind, keywords in _KINDS:
        if _has(tokens, joined, keywords):
            return kind
    return ''


def relation_label(child: str, parent: str, custom: str = '', column: str = '') -> str:
    """The verb for the diamond between `child` (holds the FK `column`) and `parent` (referenced)."""
    if custom.strip():
        return custom.strip()
    if verb := _from_column(column):
        return verb
    c, p = _tokens(child), _tokens(parent)
    if verb := _part_of(c, p):
        return verb

    # A column like kasir_id or pelanggan_id says which kind of person a generic `users` row is
    role = [t for t in _tokens(column) if t not in _KEY_TOKENS]
    kind = (_kind(role) if role and role != p else '') or _kind(p)
    joined = '_'.join(c)
    for keywords, verb in _BY_KIND.get(kind, []):
        if not keywords or _has(c, joined, keywords):
            return verb
    return 'memiliki'


def diamond_text(label: str) -> str:
    """HTML for the diamond: a long multi-word label goes on two lines so it stays inside the shape."""
    words = [html.escape(w) for w in label.split()]
    if len(label) > 10 and len(words) > 1:
        half = (len(words) + 1) // 2
        return ' '.join(words[:half]) + '<br>' + ' '.join(words[half:])
    return ' '.join(words)
