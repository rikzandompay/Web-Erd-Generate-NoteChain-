# DESIGN.md: ERD Generator by Rikzan

Arahan desain dari pemilik (Rikzan), dijawab pada 23 Oktober 2026. Nilai warna konkret di bagian "Implementasi" adalah terjemahan agen dari arahan ini dan boleh diganti pemilik.

## Arahan pemilik

- **Nama produk:** ERD Generator by Rikzan
- **Logo:** nama sebagai teks saja (wordmark), tanpa ikon
- **Suasana:** meja kerja yang tenang. Seperti alat kerja/editor: rapi, fokus ke teks input dan hasil diagram, tanpa hiasan. Cocok untuk dipakai berulang kali.
- **Warna aksen:** biru tinta pulpen, dipakai hemat di momen penting (misalnya tombol Buat diagram)
- **Tipografi:** IBM Plex Sans + IBM Plex Mono
- **Tema:** toggle terang dan gelap, default mengikuti setelan perangkat

## Dial

ENERGY 1 / RHYTHM 1 / MOTION 1 (diturunkan dari suasana "meja kerja yang tenang")

## Implementasi (terjemahan agen, kontras sudah dicek WCAG AA)

| Token | Terang | Gelap | Dipakai untuk |
|---|---|---|---|
| desk | #F2F1EC | #161719 | latar halaman (meja) |
| panel | #FCFCFA | #1E2023 | panel input dan hasil |
| ink | #1E1D1A | #E9E7E2 | teks utama |
| muted | #5C5951 | #A6A39C | teks sekunder |
| line | #DEDBD3 | #34373C | garis pemisah (bukan kontrol) |
| edge | #8B877E | #7A776F | batas kontrol (input, tombol sekunder), minimal 3:1 |
| accent | #24408E | #9DB0EE | tinta: tombol utama, tab aktif, fokus |
| on-accent | #FFFFFF | #131A31 | teks di atas tombol utama |
| danger | #A3261B di #FBECE9 | #F2A79C di #3A2220 | pesan error |
| paper | #FFFFFF | #FFFFFF | kertas preview diagram (kanvas draw.io memang terang) |

Motif identitas: **tab halaman**, meniru tab halaman di draw.io (hasil generate memang berupa beberapa halaman). Dipakai untuk pilihan mode, jenis diagram, dan daftar halaman hasil.
