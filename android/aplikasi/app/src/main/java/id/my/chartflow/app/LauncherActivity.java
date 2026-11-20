package id.my.chartflow.app;

import android.app.Activity;
import android.app.AlertDialog;
import android.app.DownloadManager;
import android.content.ActivityNotFoundException;
import android.content.Intent;
import android.content.res.ColorStateList;
import android.graphics.Bitmap;
import android.net.ConnectivityManager;
import android.net.Network;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Environment;
import android.print.PrintAttributes;
import android.print.PrintDocumentAdapter;
import android.print.PrintManager;
import android.provider.MediaStore;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.webkit.CookieManager;
import android.webkit.JavascriptInterface;
import android.webkit.PermissionRequest;
import android.webkit.URLUtil;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.FrameLayout;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.TextView;
import android.animation.ObjectAnimator;
import android.animation.ValueAnimator;
import android.graphics.Typeface;
import android.os.SystemClock;
import android.widget.ProgressBar;
import android.widget.Toast;

import androidx.core.content.FileProvider;

import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileInputStream;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;

/**
 * ChartFlow: membuka chartflow.my.id langsung di dalam aplikasi (WebView sendiri,
 * tanpa Chrome, tanpa bilah alamat, tanpa efek memantul). Diadaptasi dari APK SiGuru.
 */
public class LauncherActivity extends Activity {

    static final String AWAL = "https://chartflow.my.id/app/id/";
    static final String DOMAIN = "chartflow.my.id";
    static final String VERSI = "2.3";
    static final int MINTA_BERKAS = 1;

    WebView web;
    ProgressBar bar;
    ValueCallback<Uri[]> tungguBerkas;
    WebChromeClient.FileChooserParams paramBerkas;
    String urlGagal = AWAL;
    /** Layar "Sinyal terputus" sedang tampil → buka ulang otomatis saat internet kembali. */
    volatile boolean layarGalat = false;
    ConnectivityManager.NetworkCallback pantauJaringan;
    /** APK 2.1: layar pembuka Flo, tampil sampai halaman pertama selesai dimuat. */
    View pembuka;
    long pembukaMulai;

    static final String SISIP_CETAK =
            "window.print=function(){try{ChartFlowApp.cetak(document.title||'ChartFlow')}catch(e){}};";

    /** Pengganti navigator.share (WebView tidak punya) dan unduhan berkas buatan halaman (blob:/data:). */
    static final String SISIP_BAGIKAN =
            "(function(){if(window.__cfApp)return;window.__cfApp=1;"
            + "function b64(b){return new Promise(function(ok,no){var r=new FileReader();"
            + "r.onload=function(){var s=String(r.result);ok(s.slice(s.indexOf(',')+1))};r.onerror=no;r.readAsDataURL(b)})}"
            + "try{navigator.canShare=function(d){return !!d};"
            + "navigator.share=function(d){d=d||{};var t=[d.text,d.url].filter(Boolean).join('\\n');"
            + "var f=d.files&&d.files[0];return (f?b64(f):Promise.resolve('')).then(function(s){"
            + "ChartFlowApp.bagikan(s,f?(f.type||'application/octet-stream'):'',f?(f.name||'berkas'):'',t,d.title||'')})};}catch(e){}"
            + "document.addEventListener('click',function(e){var a=e.target&&e.target.closest?e.target.closest('a[download]'):null;"
            + "if(!a)return;var h=a.getAttribute('href')||'';if(!/^(blob:|data:)/.test(h))return;"
            + "e.preventDefault();e.stopPropagation();var n=a.getAttribute('download')||'berkas';"
            + "fetch(h).then(function(r){return r.blob()}).then(function(bl){return b64(bl).then(function(s){"
            + "ChartFlowApp.simpan(s,bl.type||'application/octet-stream',n)})}).catch(function(){})},true);"
            // unduhan lewat a.click() buatan skrip (tanpa ditempel ke halaman) juga ditangkap
            + "var oc=HTMLAnchorElement.prototype.click;HTMLAnchorElement.prototype.click=function(){"
            + "var h=this.getAttribute('href')||'';if(this.hasAttribute('download')&&/^(blob:|data:)/.test(h)){"
            + "var n=this.getAttribute('download')||'berkas';fetch(h).then(function(r){return r.blob()}).then(function(bl){"
            + "return b64(bl).then(function(s){ChartFlowApp.simpan(s,bl.type||'application/octet-stream',n)})}).catch(function(){});return}"
            + "return oc.apply(this,arguments)};})();";

    @Override
    protected void onCreate(Bundle simpanan) {
        super.onCreate(simpanan);

        FrameLayout akar = new FrameLayout(this);
        web = new WebView(this);
        web.setOverScrollMode(View.OVER_SCROLL_NEVER);
        web.setBackgroundColor(0xFFF3F5FA);
        akar.addView(web, new FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT));

        bar = new ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal);
        bar.setMax(100);
        bar.setProgressTintList(ColorStateList.valueOf(0xFF2F5BEA));
        FrameLayout.LayoutParams lp = new FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, dp(3), Gravity.TOP);
        akar.addView(bar, lp);
        if (simpanan == null) {
            pembuka = buatPembuka();
            akar.addView(pembuka, new FrameLayout.LayoutParams(
                    ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT));
            pembukaMulai = SystemClock.uptimeMillis();
            akar.postDelayed(this::tutupPembuka, 12000); // pengaman bila halaman lambat sekali
        }
        setContentView(akar);

        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setDatabaseEnabled(true);
        s.setAllowFileAccess(false);
        s.setAllowContentAccess(true);
        s.setSupportMultipleWindows(false);
        s.setJavaScriptCanOpenWindowsAutomatically(true);
        s.setLoadWithOverviewMode(true);
        s.setUseWideViewPort(true);
        s.setTextZoom(100);
        s.setSupportZoom(false);
        s.setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);
        s.setUserAgentString(s.getUserAgentString() + " ChartFlowApp/" + VERSI);

        CookieManager cm = CookieManager.getInstance();
        cm.setAcceptCookie(true);
        cm.setAcceptThirdPartyCookies(web, true);

        web.addJavascriptInterface(new Jembatan(), "ChartFlowApp");
        web.setWebViewClient(new Klien());
        web.setWebChromeClient(new Krom());
        web.setDownloadListener((url, ua, cd, mime, panjang) -> unduh(url, ua, cd, mime));

        String bukaAwal = alamatDariNiat(getIntent());
        if (bukaAwal != null) {
            web.loadUrl(bukaAwal);
        } else if (simpanan == null || web.restoreState(simpanan) == null) {
            web.loadUrl(AWAL);
        }
        tampilkanGalatLama();
        pantauInternet();
    }

    /** Saat internet kembali dan layar "Sinyal terputus" tampil → buka lagi halaman yang gagal. */
    void pantauInternet() {
        try {
            ConnectivityManager cm = (ConnectivityManager) getSystemService(CONNECTIVITY_SERVICE);
            pantauJaringan = new ConnectivityManager.NetworkCallback() {
                @Override
                public void onAvailable(Network n) {
                    if (!layarGalat || web == null) return;
                    web.postDelayed(() -> { if (layarGalat && web != null) { layarGalat = false; web.loadUrl(urlGagal); } }, 1200);
                }
            };
            cm.registerDefaultNetworkCallback(pantauJaringan);
        } catch (Exception x) { pantauJaringan = null; }
    }

    // ---------- navigasi ----------

    static boolean milikChartFlow(Uri u) {
        if (u == null) return false;
        String skema = u.getScheme(), host = u.getHost();
        if (skema == null || host == null) return false;
        if (!skema.equals("https") && !skema.equals("http")) return false;
        host = host.toLowerCase();
        return host.equals(DOMAIN) || host.endsWith("." + DOMAIN);
    }

    void bukaLuar(Uri u) {
        try {
            Intent i;
            if ("intent".equals(u.getScheme())) {
                i = Intent.parseUri(u.toString(), Intent.URI_INTENT_SCHEME);
                i.addCategory(Intent.CATEGORY_BROWSABLE);
                i.setComponent(null);
                i.setSelector(null);
            } else {
                i = new Intent(Intent.ACTION_VIEW, u);
            }
            startActivity(i);
        } catch (Exception e) {
            Toast.makeText(this, "Tidak ada aplikasi untuk membuka tautan ini", Toast.LENGTH_SHORT).show();
        }
    }

    class Klien extends WebViewClient {
        @Override
        public boolean shouldOverrideUrlLoading(WebView v, WebResourceRequest r) {
            Uri u = r.getUrl();
            // berkas APK selalu lewat pengelola unduhan, bukan halaman
            if (milikChartFlow(u) && u.getPath() != null && u.getPath().endsWith(".apk")) { bukaLuar(u); return true; }
            if (milikChartFlow(u)) return false;
            if ("about".equals(u.getScheme()) || "data".equals(u.getScheme())
                    || "blob".equals(u.getScheme())) return false;
            bukaLuar(u);
            return true;
        }

        @Override
        public void onPageStarted(WebView v, String url, Bitmap ikon) {
            bar.setVisibility(View.VISIBLE);
        }

        @Override
        public void onPageCommitVisible(WebView v, String url) {
            v.evaluateJavascript(SISIP_CETAK + SISIP_BAGIKAN, null);
        }

        @Override
        public void onPageFinished(WebView v, String url) {
            if (url != null && url.startsWith("http")) tutupPembuka();
            v.evaluateJavascript(SISIP_CETAK + SISIP_BAGIKAN, null);
            bar.setVisibility(View.GONE);
            CookieManager.getInstance().flush();
        }

        @Override
        public void onReceivedError(WebView v, WebResourceRequest r, WebResourceError e) {
            if (!r.isForMainFrame()) return;
            urlGagal = r.getUrl().toString();
            layarGalat = true;
            String sebab = e.getDescription() == null ? "" : e.getDescription().toString().replace("<", "");
            // Flo beristirahat (gambar disimpan di dalam APK); buka ulang otomatis saat internet kembali
            String html = "<!doctype html><html lang='id'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
                    + "<style>body{font-family:sans-serif;margin:0;display:flex;align-items:center;justify-content:center;"
                    + "min-height:100vh;background:#F3F5FA;color:#0F172A;text-align:center;overscroll-behavior:none}"
                    + ".k{background:#fff;border-radius:20px;padding:18px 22px 24px;margin:20px;max-width:360px;"
                    + "box-shadow:0 2px 12px rgba(15,23,42,.08)}h2{color:#2F5BEA;margin:4px 0 8px}"
                    + ".t{position:relative;width:170px;margin:0 auto 6px;transform-origin:50% 95%;animation:n 4s ease-in-out infinite}"
                    + ".t img{display:block;width:100%;height:auto}"
                    + ".z{position:absolute;left:58%;top:12%;font-weight:800;color:#93A4C4;opacity:0;animation:z 3s ease-in infinite}"
                    + ".z:nth-child(3){animation-delay:1s;font-size:18px}.z:nth-child(4){animation-delay:2s;font-size:22px}"
                    + "@keyframes n{0%,100%{transform:scale(1,1)}50%{transform:scale(1.02,1.045)}}"
                    + "@keyframes z{0%{transform:translate(0,0) scale(.6);opacity:0}20%{opacity:1}100%{transform:translate(26px,-56px) scale(1.2);opacity:0}}"
                    + "p{color:#5B6382;line-height:1.5;margin:0 0 6px}small{display:block;color:#9AA3BA;font-size:11px;margin-top:14px}"
                    + "button{background:#2F5BEA;color:#fff;border:0;border-radius:12px;padding:12px 28px;font-size:16px;margin-top:10px}"
                    + "@media (prefers-reduced-motion:reduce){.t,.z{animation:none}}</style></head><body><div class='k'>"
                    + "<div class='t'><img src='flo-istirahat.webp' alt='Flo'><b class='z'>z</b><b class='z'>z</b><b class='z'>Z</b></div>"
                    + "<h2>Sinyal sedang terputus</h2><p>Internet HP belum tersambung ke ChartFlow.</p>"
                    + "<p>Flo akan membuka ChartFlow lagi begitu internet kembali.</p>"
                    + "<button onclick='ChartFlowApp.ulang()'>Coba lagi</button><small>" + sebab + "</small></div></body></html>";
            v.loadDataWithBaseURL("file:///android_asset/", html, "text/html", "utf-8", null);
            tutupPembuka();
        }
    }

    class Krom extends WebChromeClient {
        @Override
        public void onProgressChanged(WebView v, int p) {
            bar.setProgress(p);
            bar.setVisibility(p >= 100 ? View.GONE : View.VISIBLE);
        }

        @Override
        public void onPermissionRequest(PermissionRequest req) {
            runOnUiThread(req::deny); // ChartFlow tidak memakai kamera/mikrofon
        }

        @Override
        public boolean onShowFileChooser(WebView v, ValueCallback<Uri[]> cb, FileChooserParams p) {
            if (tungguBerkas != null) tungguBerkas.onReceiveValue(null);
            tungguBerkas = cb;
            paramBerkas = p;
            bukaPemilih();
            return true;
        }
    }

    // ---------- berkas (pulihkan cadangan portofolio) ----------

    void bukaPemilih() {
        Intent pilih = new Intent(Intent.ACTION_GET_CONTENT);
        pilih.addCategory(Intent.CATEGORY_OPENABLE);
        pilih.setType("*/*");
        if (paramBerkas != null && paramBerkas.getMode() == WebChromeClient.FileChooserParams.MODE_OPEN_MULTIPLE) {
            pilih.putExtra(Intent.EXTRA_ALLOW_MULTIPLE, true);
        }
        try {
            startActivityForResult(Intent.createChooser(pilih, "Pilih berkas"), MINTA_BERKAS);
        } catch (ActivityNotFoundException e) {
            selesaiBerkas(null);
        }
    }

    void selesaiBerkas(Uri[] hasil) {
        if (tungguBerkas != null) tungguBerkas.onReceiveValue(hasil);
        tungguBerkas = null;
        paramBerkas = null;
    }

    @Override
    protected void onActivityResult(int kode, int hasilKode, Intent data) {
        if (kode != MINTA_BERKAS) {
            super.onActivityResult(kode, hasilKode, data);
            return;
        }
        Uri[] hasil = null;
        if (hasilKode == RESULT_OK && data != null) {
            ArrayList<Uri> daftar = new ArrayList<>();
            if (data.getClipData() != null) {
                for (int i = 0; i < data.getClipData().getItemCount(); i++) {
                    Uri u = data.getClipData().getItemAt(i).getUri();
                    if (u != null) daftar.add(u);
                }
            } else if (data.getData() != null) {
                daftar.add(data.getData());
            }
            if (!daftar.isEmpty()) hasil = daftar.toArray(new Uri[0]);
        }
        selesaiBerkas(hasil);
    }

    // ---------- unduhan & cetak ----------

    void unduh(String url, String ua, String cd, String mime) {
        String nama = URLUtil.guessFileName(url, cd, mime);
        if (!(url.startsWith("https://") || url.startsWith("http://"))) {
            Toast.makeText(this, "Unduhan ini belum bisa dari aplikasi", Toast.LENGTH_LONG).show();
            return;
        }
        if (Build.VERSION.SDK_INT < 29) {
            bukaLuar(Uri.parse(url));
            return;
        }
        try {
            DownloadManager.Request r = new DownloadManager.Request(Uri.parse(url));
            String kue = CookieManager.getInstance().getCookie(url);
            if (kue != null) r.addRequestHeader("Cookie", kue);
            r.addRequestHeader("User-Agent", ua);
            if (mime != null) r.setMimeType(mime);
            r.setTitle(nama);
            r.setNotificationVisibility(DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED);
            r.setDestinationInExternalPublicDir(Environment.DIRECTORY_DOWNLOADS, nama);
            ((DownloadManager) getSystemService(DOWNLOAD_SERVICE)).enqueue(r);
            Toast.makeText(this, "Mengunduh " + nama + " (lihat folder Download)", Toast.LENGTH_LONG).show();
        } catch (Exception e) {
            bukaLuar(Uri.parse(url));
        }
    }

    class Jembatan {
        @JavascriptInterface
        public void cetak(String judul) {
            runOnUiThread(() -> {
                try {
                    String j = (judul == null || judul.trim().isEmpty()) ? "ChartFlow" : judul.trim();
                    PrintManager pm = (PrintManager) getSystemService(PRINT_SERVICE);
                    PrintDocumentAdapter a = web.createPrintDocumentAdapter(j);
                    pm.print(j, a, new PrintAttributes.Builder()
                            .setMediaSize(PrintAttributes.MediaSize.ISO_A4).build());
                } catch (Exception e) {
                    Toast.makeText(LauncherActivity.this, "Gagal membuka cetak", Toast.LENGTH_SHORT).show();
                }
            });
        }

        @JavascriptInterface
        public void bagikan(String b64, String mime, String nama, String teks, String judul) {
            runOnUiThread(() -> {
                try {
                    Intent i = new Intent(Intent.ACTION_SEND);
                    if (b64 != null && !b64.isEmpty()) {
                        File f = tulisCache(b64, nama);
                        Uri u = FileProvider.getUriForFile(LauncherActivity.this, getPackageName() + ".berkas", f);
                        i.setType(mime == null || mime.isEmpty() ? "application/octet-stream" : mime);
                        i.putExtra(Intent.EXTRA_STREAM, u);
                        i.setClipData(android.content.ClipData.newRawUri("", u));
                        i.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
                    } else {
                        i.setType("text/plain");
                    }
                    if (teks != null && !teks.isEmpty()) i.putExtra(Intent.EXTRA_TEXT, teks);
                    if (judul != null && !judul.isEmpty()) i.putExtra(Intent.EXTRA_SUBJECT, judul);
                    startActivity(Intent.createChooser(i, "Bagikan lewat"));
                } catch (Exception e) {
                    Toast.makeText(LauncherActivity.this, "Gagal membagikan", Toast.LENGTH_SHORT).show();
                }
            });
        }

        @JavascriptInterface
        public void simpan(String b64, String mime, String nama) {
            runOnUiThread(() -> simpanBerkas(b64, mime, nama));
        }

        @JavascriptInterface
        public void ulang() {
            runOnUiThread(() -> { layarGalat = false; web.loadUrl(urlGagal); });
        }

        @JavascriptInterface
        public String versi() {
            return VERSI;
        }
    }

    static String namaAman(String n) {
        String s = (n == null ? "" : n).replaceAll("[^A-Za-z0-9._ -]", "_").trim();
        return s.isEmpty() ? "berkas" : s;
    }

    File tulisCache(String b64, String nama) throws Exception {
        File dir = new File(getCacheDir(), "bagikan");
        if (!dir.exists()) dir.mkdirs();
        File[] lama = dir.listFiles();
        if (lama != null) for (File x : lama) x.delete();
        File f = new File(dir, namaAman(nama));
        try (java.io.FileOutputStream o = new java.io.FileOutputStream(f)) {
            o.write(android.util.Base64.decode(b64, android.util.Base64.DEFAULT));
        }
        return f;
    }

    void simpanBerkas(String b64, String mime, String nama) {
        String n = namaAman(nama);
        if (mime == null || mime.isEmpty()) mime = "application/octet-stream";
        try {
            if (Build.VERSION.SDK_INT >= 29) {
                boolean gambar = mime.startsWith("image/");
                android.content.ContentValues cv = new android.content.ContentValues();
                cv.put(MediaStore.MediaColumns.DISPLAY_NAME, n);
                cv.put(MediaStore.MediaColumns.MIME_TYPE, mime);
                cv.put(MediaStore.MediaColumns.RELATIVE_PATH,
                        (gambar ? Environment.DIRECTORY_PICTURES : Environment.DIRECTORY_DOWNLOADS) + "/ChartFlow");
                Uri koleksi = gambar ? MediaStore.Images.Media.EXTERNAL_CONTENT_URI
                        : MediaStore.Downloads.EXTERNAL_CONTENT_URI;
                Uri u = getContentResolver().insert(koleksi, cv);
                if (u == null) throw new Exception("insert");
                try (java.io.OutputStream o = getContentResolver().openOutputStream(u)) {
                    o.write(android.util.Base64.decode(b64, android.util.Base64.DEFAULT));
                }
                Toast.makeText(this, gambar ? "Gambar disimpan di Galeri (folder ChartFlow)"
                        : "Disimpan di folder Download/ChartFlow", Toast.LENGTH_LONG).show();
            } else {
                // HP lama: tawarkan lewat menu Bagikan (bisa dipilih "Simpan ke ...")
                new Jembatan().bagikan(b64, mime, n, "", n);
            }
        } catch (Exception e) {
            Toast.makeText(this, "Gagal menyimpan berkas", Toast.LENGTH_SHORT).show();
        }
    }

    /** Tautan chartflow.my.id/app/... yang dibuka dari aplikasi lain (mis. Telegram). */
    static String alamatDariNiat(Intent i) {
        if (i == null) return null;
        Uri d = i.getData();
        if (d != null && milikChartFlow(d)) return d.toString();
        return null;
    }

    @Override
    protected void onNewIntent(Intent i) {
        super.onNewIntent(i);
        String u = alamatDariNiat(i);
        if (u != null && web != null) web.loadUrl(u);
    }

    // ---------- siklus hidup ----------

    @Override
    public void onBackPressed() {
        if (web != null && web.canGoBack()) web.goBack();
        else super.onBackPressed();
    }

    @Override
    protected void onPause() {
        super.onPause();
        CookieManager.getInstance().flush();
        if (web != null) web.onPause();
    }

    @Override
    protected void onResume() {
        super.onResume();
        if (web != null) web.onResume();
    }

    @Override
    protected void onSaveInstanceState(Bundle keluar) {
        super.onSaveInstanceState(keluar);
        if (web != null) web.saveState(keluar);
    }

    @Override
    protected void onDestroy() {
        try { if (pantauJaringan != null) ((ConnectivityManager) getSystemService(CONNECTIVITY_SERVICE)).unregisterNetworkCallback(pantauJaringan); } catch (Exception x) { /* abaikan */ }
        if (web != null) {
            web.stopLoading();
            web.destroy();
            web = null;
        }
        super.onDestroy();
    }

    void tampilkanGalatLama() {
        try {
            File f = new File(getFilesDir(), "galat.txt");
            if (!f.exists()) return;
            ByteArrayOutputStream b = new ByteArrayOutputStream();
            try (FileInputStream in = new FileInputStream(f)) {
                byte[] buf = new byte[4096];
                int n;
                while ((n = in.read(buf)) > 0) b.write(buf, 0, n);
            }
            String isi = new String(b.toByteArray(), StandardCharsets.UTF_8);
            f.delete();
            if (isi.length() > 2500) isi = isi.substring(0, 2500);
            new AlertDialog.Builder(this)
                    .setTitle("Aplikasi sempat tertutup")
                    .setMessage("Tolong foto layar ini dan kirim ke Claude.\n\n" + isi)
                    .setPositiveButton("Tutup", null)
                    .show();
        } catch (Exception ignored) {
        }
    }

    /** Layar pembuka: Flo melambai + nama aplikasi + garis memuat. */
    View buatPembuka() {
        FrameLayout luar = new FrameLayout(this);
        luar.setBackgroundColor(0xFFF3F5FA);
        luar.setClickable(true);
        LinearLayout isi = new LinearLayout(this);
        isi.setOrientation(LinearLayout.VERTICAL);
        isi.setGravity(Gravity.CENTER_HORIZONTAL);

        ImageView flo = new ImageView(this);
        flo.setImageResource(R.drawable.flo_hai);
        flo.setAdjustViewBounds(true);
        isi.addView(flo, new LinearLayout.LayoutParams(dp(190), ViewGroup.LayoutParams.WRAP_CONTENT));

        TextView nama = new TextView(this);
        nama.setText("ChartFlow");
        nama.setTextColor(0xFF0F172A);
        nama.setTextSize(26);
        nama.setTypeface(Typeface.DEFAULT_BOLD);
        nama.setGravity(Gravity.CENTER);
        LinearLayout.LayoutParams lpn = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        lpn.topMargin = dp(10);
        isi.addView(nama, lpn);

        TextView kata = new TextView(this);
        kata.setText("Flo sedang menyiapkan data\u2026");
        kata.setTextColor(0xFF64748B);
        kata.setTextSize(14);
        kata.setGravity(Gravity.CENTER);
        LinearLayout.LayoutParams lpk = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        lpk.topMargin = dp(4);
        isi.addView(kata, lpk);

        ProgressBar garis = new ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal);
        garis.setIndeterminate(true);
        garis.setIndeterminateTintList(ColorStateList.valueOf(0xFF2F5BEA));
        LinearLayout.LayoutParams lpg = new LinearLayout.LayoutParams(dp(160), dp(4));
        lpg.topMargin = dp(18);
        isi.addView(garis, lpg);

        luar.addView(isi, new FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT, Gravity.CENTER));

        // Flo muncul pelan lalu melambai (bergoyang kiri-kanan)
        isi.setAlpha(0f);
        isi.setTranslationY(dp(18));
        isi.animate().alpha(1f).translationY(0).setDuration(450).start();
        flo.post(() -> {
            flo.setPivotX(flo.getWidth() / 2f);
            flo.setPivotY(flo.getHeight() * 0.92f);
            ObjectAnimator a = ObjectAnimator.ofFloat(flo, "rotation", -4f, 4f);
            a.setDuration(650);
            a.setRepeatCount(ValueAnimator.INFINITE);
            a.setRepeatMode(ValueAnimator.REVERSE);
            a.start();
        });
        return luar;
    }

    void tutupPembuka() {
        if (pembuka == null) return;
        long sisa = 1400 - (SystemClock.uptimeMillis() - pembukaMulai); // minimal 1,4 detik agar Flo sempat terlihat
        if (sisa > 0) { pembuka.postDelayed(this::tutupPembuka, sisa); return; }
        final View p = pembuka;
        pembuka = null;
        p.animate().alpha(0f).setDuration(350).withEndAction(() -> {
            ViewGroup induk = (ViewGroup) p.getParent();
            if (induk != null) induk.removeView(p);
        }).start();
    }

    int dp(int n) {
        return Math.round(n * getResources().getDisplayMetrics().density);
    }
}
