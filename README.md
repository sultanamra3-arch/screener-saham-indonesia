# Screener Saham Indonesia

Semua saham Bursa Efek Indonesia yang tersedia di Yahoo Finance (±840 saham), disaring dengan 7 metode sesuai aturan aslinya: Value (Graham), Growth (Lynch), Quality (Terry Smith), Dividen, CAN SLIM (O'Neil/Minervini), Momentum (Jegadeesh & Titman), dan Swing (Connors RSI-2). Setiap sinyal punya harga patokan (dibulatkan ke fraksi BEI) dan alasannya.

Website: `https://sultanamra3-arch.github.io/screener-saham-indonesia/`

## Jadwal

- **Senin–Jumat ±17.45 WIB**: data diperbarui setelah BEI tutup, ringkasan dikirim ke Telegram 🇮🇩.
- **Senin–Jumat 08.15 WIB**: pengingat order sebelum pra-pembukaan, hanya bila ada sinyal beli.
- Tidak ada pesan di hari libur BEI (daftar libur 2026 di `scripts/notify_telegram.py`, perbarui tiap akhir tahun).

## Sumber data (gratis)

| Data | Sumber |
|---|---|
| Daftar saham, harga, volume | Yahoo Finance (`yfinance`) |
| Rasio, laporan keuangan ±4 tahun, riwayat dividen ±20 tahun | Yahoo Finance |
| Label syariah | Daftar Efek Syariah OJK (file Excel terbaru) |
| IPO baru | e-IPO (otomatis) dan `data/tambahan.txt` (manual) |

Situs BEI memblokir akses otomatis, jadi tidak dipakai.

## Penyesuaian pasar Indonesia

- **Likuiditas**: likuid ≥ Rp5 miliar/hari, kurang likuid Rp1–5 miliar, tidak likuid < Rp1 miliar (rata-rata 3 bulan). Website menampilkan saham likuid secara default; Telegram hanya saham likuid. RS rating dan peringkat momentum hanya dihitung di antara saham ≥ Rp1 miliar/hari.
- **Biaya transaksi** (beli 0,15%, jual 0,25%) masuk ke uji mundur dan hasil posisi.
- **Fraksi harga BEI** untuk semua harga patokan; 1 lot = 100 lembar.
- **IHSG** sebagai arah pasar (huruf M di CAN SLIM).
- **Bank**: syarat yang tidak relevan (current ratio, margin kotor, arus kas, utang/ekuitas) ditandai tidak berlaku; Quality memakai ROE dan P/B.
- **Value**: market cap ≥ Rp10 triliun; riwayat laba Yahoo hanya ±4 tahun (Graham aslinya 10 tahun); dividen tanpa putus 20 tahun dihitung penuh.
- **Dividen**: yield minimal 4% (di atas bunga deposito), plus Chowder rule.

## Pemasangan

1. Settings → Secrets and variables → Actions: `TELEGRAM_BOT_TOKEN` dan `TELEGRAM_CHAT_ID` (sama dengan repo screener AS).
2. Settings → Pages: Deploy from a branch, `main`, `/ (root)`.
3. Actions → **Update data saham Indonesia** → Run workflow (±30 menit).

Alat penyaring, bukan rekomendasi investasi.

## Siklus & Fibonacci (tab "Siklus")

Analisis waktu dan harga dari teknik yang terbuka untuk umum: titik balik ZigZag, zona konfluensi Fibonacci (retracement, proyeksi, SMA50/200, angka bulat), kalender fase bulan, stasiun planet (Merkurius, Venus, Mars), Fibonacci time zone dan pola musiman, tanggal rawan pembalikan, rentang pergerakan mingguan, dan kesehatan pasar (breadth). Setiap unsur diuji terhadap tanggal acak pada riwayat indeks sejak 2005, dan setiap ramalan dicatat di papan skor sebelum terjadi. Kalender mingguan dikirim ke Telegram setiap Senin pagi.
