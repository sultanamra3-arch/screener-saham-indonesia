# Catatan untuk Claude

## Wajib: halaman depan ChartFlow ikut setiap perubahan fitur
Halaman depan **chartflow.my.id** ada di repo `screener-saham-indonesia`, folder `chartflow/public/`. Halaman itu ditulis manual, jadi tidak ikut berubah sendiri.

Setiap kali menambah, mengubah, atau menghapus fitur/tampilan di screener ID, US, atau Kripto (repo mana pun), di pekerjaan yang sama:
1. Perbarui `chartflow/public/index.html` (kartu fitur, galeri, FAQ, statistik) di repo `screener-saham-indonesia`.
2. Tambahkan satu baris di paling atas `chartflow/public/changes.json` (`d` tanggal, `t` judul singkat, `x` penjelasan satu kalimat). Bagian "✨ Yang baru" di halaman depan membaca file ini.
3. Perbarui `chartflow/features.json`: fitur baru masuk `active` (kata yang wajib disebut), fitur yang dihapus pindah ke `removed` (kata yang dilarang).
4. Bila tampilannya berubah, ambil ulang screenshot galeri (`chartflow/public/img/shot-*.webp`, 1440×900; `shot-mobile.webp` 600×1221) memakai data contoh dan bahasa aman (akun bukan pemilik).
5. Jalankan `python3 scripts/check_landing.py` (repo `screener-saham-indonesia`). Workflow "Pasang beranda & login chartflow.my.id" menahan pengiriman dan mengirim pesan Telegram bila pemeriksaan ini gagal.

Teks di halaman depan dibaca orang lain: pakai bahasa aman (keterangan aturan, bukan ajakan membeli/menjual), dan sebut risiko untuk kripto.

## Kebiasaan kerja
- Pemilik berkomunikasi dalam bahasa Indonesia. Usulkan rencana dulu; bangun setelah pemilik bilang "siap"/"ya"/"mau". Perbaikan bug yang jelas boleh langsung dikerjakan.
- Jangan pernah meminta atau menulis token, password FTP, atau kunci API di chat atau di repo; semuanya ada di GitHub Secrets.
- Jangan commit `signing.keystore` atau `signing-key-info.txt`.
