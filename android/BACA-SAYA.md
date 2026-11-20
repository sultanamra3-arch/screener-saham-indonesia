# APK ChartFlow 2.0 (aplikasi WebView sendiri)

Sejak 21 Nov 2026 APK ChartFlow bukan lagi TWA (yang berjalan lewat Chrome, terlihat dari menu "Site Settings" saat ikon ditahan), melainkan aplikasi **WebView biasa** yang diadaptasi dari APK SiGuru (`sultanamra3-arch/web-guru`, folder `android/aplikasi`).

Ciri:
- Paket **`id.my.chartflow.app`**. Paket TWA lama `id.my.chartflow.twa` memakai kunci lain, jadi pengguna lama perlu menghapus versi lama dulu. Nama di HP "ChartFlow".
- Membuka `https://chartflow.my.id/app/id/` langsung di dalam aplikasi, tanpa Chrome dan tanpa bilah alamat. Semua alamat `*.chartflow.my.id` dibuka di dalam aplikasi; alamat lain (dan berkas `.apk`) dibuka di aplikasi luar.
- User agent ditambah `ChartFlowApp/<versi>`; halaman memakai ini untuk menyembunyikan tombol "Pasang aplikasi" dan tautan APK.
- Tanpa efek memantul (`OVER_SCROLL_NEVER`), tidak bisa dicubit-perbesar, tombol Kembali HP = kembali satu halaman.
- `navigator.share` diganti jembatan `ChartFlowApp.bagikan` → menu Bagikan Android; unduhan `blob:`/`data:` (mis. cadangan portofolio) disimpan lewat `ChartFlowApp.simpan` → Download/ChartFlow (gambar → Galeri/Pictures/ChartFlow).
- `window.print()` → layanan cetak Android. Pemilih berkas untuk memulihkan cadangan.
- Tanpa internet (dan halaman belum tersimpan oleh service worker): layar "Sinyal sedang terputus" dengan Flo tidur (`assets/flo-istirahat.webp`), terbuka ulang otomatis saat internet kembali.
- Tautan `https://chartflow.my.id/app/...` dari aplikasi lain (mis. Telegram) bisa dibuka di ChartFlow.
- APK 2.1 (versionCode 2): layar pembuka Android 12+ memakai kepala Flo (`values-v31/tema.xml`, `drawable/flo_splash.xml`), lalu layar pembuka Flo melambai + "ChartFlow" + garis memuat sampai halaman pertama selesai (minimal 1,4 detik, paling lama 12 detik).
- Bila aplikasi sempat tertutup sendiri, pesan galatnya tampil saat dibuka lagi.

Membuat ulang:
1. Android SDK (platform 35, build-tools 35), JDK 17+, Gradle 8.11+.
2. `cd aplikasi && ANDROID_HOME=... gradle assembleRelease`
3. `zipalign -p -f 4 app/build/outputs/apk/release/app-release-unsigned.apk al.apk`
4. `apksigner sign --ks chartflow.keystore --ks-key-alias chartflow --out ChartFlow.apk al.apk`
   (keystore + sandi disimpan Pak Sultan — JANGAN di-commit). Naikkan `versionCode`/`versionName` di `app/build.gradle` dan `VERSI` di `LauncherActivity.java` tiap rilis.
5. Salin ke `chartflow/public/download/ChartFlow.apk`, lalu tambahkan baris di `chartflow/public/changes.json`.

Sidik jari kunci (SHA-256): `AB:A4:AA:A4:BF:E1:EF:F0:B0:1A:85:8F:FE:8A:00:38:17:D3:80:84:87:D8:0F:E7:49:9A:AE:4F:BC:FC:8D:47`.

`/.well-known/assetlinks.json` hanya dipakai APK TWA lama; aman dibiarkan.
