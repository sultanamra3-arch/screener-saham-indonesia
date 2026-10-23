# Uji coba kedua (2026-10-23T16:45:48+00:00)

## 1. Daftar semua saham BEI

- **Yahoo screener (bursa JKT)**: 839 kode
- **Wikipedia id 'Daftar perusahaan yang tercatat di Bursa Efek Indonesia'**: 1 tabel, 0 kode
- Wikipedia id 'Daftar emiten di Bursa Efek Indonesia': tidak ada (The page you specified doesn't exist.)
- Wikipedia en 'List of companies listed on the Indonesia Stock Exchange': tidak ada (The page you specified doesn't exist.)
- **Gabungan semua sumber**: 839 kode
  - hanya di Yahoo: 839 · hanya di Wikipedia: 0 · di keduanya: 0
  - contoh hanya di Yahoo: ['AADI', 'AALI', 'ABDA', 'ABMM', 'ACES', 'ACRO', 'ACST', 'ADES', 'ADMF', 'ADMG', 'ADMR', 'ADRO', 'AEGS', 'AGAR', 'AGII']
  - contoh hanya di Wikipedia: []

## 2. Harga semua saham dari Yahoo dan sebaran likuiditas

- Waktu unduh harga 839 saham: 55 detik
- Ada data harga: 839 · masih aktif diperdagangkan seminggu terakhir: 839
- Riwayat < 200 hari (baru/IPO atau bolong): 7
- Sebaran rata-rata nilai transaksi harian (3 bulan):
  - >= Rp50 M: 55 saham
  - Rp10–50 M: 107 saham
  - Rp5–10 M: 74 saham
  - Rp1–5 M: 213 saham
  - Rp0,1–1 M: 284 saham
  - < Rp0,1 M: 106 saham
- Saham dengan > 20 hari tanpa transaksi dalam 3 bulan: 11
- Nilai transaksi saham ke-150: Rp11.0 M/hari · ke-250: Rp4.5 M/hari

## 3. Uji beban fundamental Yahoo (info + laporan laba + dividen)

- 180 saham (60 paling likuid, 60 menengah, 60 paling sepi) dalam 186 detik (±1.0 detik per saham → semua saham ±14 menit)
- Berhasil: info 180, laporan laba 150, dividen 180 dari 180
- Error: 0
- Tanda dibatasi (429/Too Many Requests): 0

## 4. e-IPO dan file Daftar Efek Syariah

- e-ipo: HTTP 200, 33,070 karakter, judul: `Find IPO | e-IPO`
- e-ipo_id: HTTP 200, 33,174 karakter, judul: `IPO | e-IPO`
- OJK halaman DES: 0 tautan file. Contoh: []
- Tautan halaman DES lain: ['/id/kanal/syariah/data-dan-statistik/daftar-efek-syariah/Pages/-Keputusan-Dewan-Komisioner-OJK-Nomor-KEP--81.D.04.2022-tentang-Daftar-Efek-Syariah.aspx', '/id/kanal/syariah/data-dan-statistik/daftar-efek-syariah/Pages/Daftar-Efek-Syariah-KEP21D042026.aspx', '/id/kanal/syariah/data-dan-statistik/daftar-efek-syariah/Pages/Daftar-Efek-Syariah-KEP28D042025.aspx', '/id/kanal/syariah/data-dan-statistik/daftar-efek-syariah/Pages/Daftar-Efek-Syariah-KEP59D042025.aspx', '/id/kanal/syariah/data-dan-statistik/daftar-efek-syariah/Pages/Keputusan-Dewan-Komisioner-OJK-Nomor-KEP-20D.042024-tentang-Daftar-Efek--Syariah.aspx', '/id/kanal/syariah/data-dan-statistik/daftar-efek-syariah/Pages/Keputusan-Dewan-Komisioner-OJK-Nomor-KEP-38.D-04.2022-tentang-Daftar-Efek-Syariah.aspx', '/id/kanal/syariah/data-dan-statistik/daftar-efek-syariah/Pages/Keputusan-Dewan-Komisioner-OJK-Nomor-KEP-51D042024-tentang-Daftar-Efek-Syariah.aspx', '/id/kanal/syariah/data-dan-statistik/daftar-efek-syariah/Pages/Keputusan-Dewan-Komisioner-OJK-Nomor-KEP-52-D.04-2023-tentang-Daftar-Efek-Syariah.aspx']