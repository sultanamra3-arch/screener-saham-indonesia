"""Siapkan salinan screener untuk chartflow.my.id/app/<pasar>/ (dipakai langkah kirim FTP).

Pemakaian: python scripts/build_chartflow_app.py <id|us> <folder keluaran>
"""
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
market, out = sys.argv[1], Path(sys.argv[2])
GH = "https://sultanamra3-arch.github.io"
if out.exists():
    shutil.rmtree(out)
if Path(str(out) + "_pub").exists():
    shutil.rmtree(Path(str(out) + "_pub"))
(out / "data").mkdir(parents=True)

s = (ROOT / "index.html").read_text(encoding="utf-8")
rep = [
    ('<link rel="manifest" href="/screener-saham/manifest.webmanifest">', '<link rel="manifest" href="/app.webmanifest">'),
    (f"{GH}/screener-saham-indonesia/", "/app/id/"),
    (f"{GH}/screener-saham/", "/app/us/"),
    ('location.replace("/screener-saham-indonesia/"+location.hash)', 'location.replace("/app/id/"+location.hash)'),
    ('<b>Screener Saham</b>', '<b>ChartFlow</b>'),
    ('<button type="button" class="iconbtn" id="theme"',
     '<button type="button" class="cfuser" id="cfUser" title="Akun">👤</button>\n      <button type="button" class="iconbtn" id="theme"'),
    ("Portofolio tersimpan di browser ini saja. Unduh cadangan secara berkala, lalu pulihkan di HP atau laptop lain bila perlu.",
     "Portofolio tersimpan di akun ChartFlow Anda dan ikut muncul di perangkat lain. Cadangan file tetap bisa diunduh untuk arsip pribadi."),
    ('  set(k,v){try{localStorage.setItem(k,v)}catch(e){}}',
     '  set(k,v){try{localStorage.setItem(k,v)}catch(e){} if(window.CF_SYNC) window.CF_SYNC(k,v);}'),
]
for a, b in rep:
    if a not in s:
        sys.exit(f"Pola tidak ditemukan di index.html: {a[:60]}")
    s = s.replace(a, b)
HEAD_JS = r'''<script>
/* ChartFlow: muat data akun dari server sebelum aplikasi berjalan */
(function(){
  var KEYS=["si.porto","ss.porto","si.star","ss.star","si.calc","ss.calc"];
  window.CF_KEYS=KEYS;
  try{
    var x=new XMLHttpRequest(); x.open("GET","/api/store.php",false); x.send();
    if(x.status===401){ location.replace("/?masuk=1&next="+encodeURIComponent(location.pathname)); return; }
    if(x.status===200){
      var j=JSON.parse(x.responseText);
      if(j.ok){
        window.CF_USER=j.user;
        var d=j.data||{}, pend={};
        try{ pend=JSON.parse(localStorage.getItem("cf.pending")||"{}"); if(localStorage.getItem("cf.owner")!==j.user.code) pend={}; }catch(e){}
        KEYS.forEach(function(k){ try{
          if(k in pend) return; /* perubahan offline yang belum terkirim menang */
          if(d[k]==null) localStorage.removeItem(k); else localStorage.setItem(k,d[k]);
        }catch(e){} });
        try{ localStorage.setItem("cf.owner",j.user.code); }catch(e){}
      }
    }
  }catch(e){ window.CF_OFFLINE=true; }
})();
</script>
'''
CSS = '''
.cfuser{display:inline-flex;align-items:center;gap:6px;max-width:170px;border-radius:999px;padding:6px 12px;font-weight:700;font-size:13px;background:var(--surface);border:1px solid var(--line);color:var(--fg);cursor:pointer;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.cfwarn{background:var(--warn-soft);color:var(--warn);border-radius:12px;padding:10px 14px;font-size:13.5px;font-weight:600}
#cfDlg,#cfApk{border:none;border-radius:20px;padding:0;width:min(380px,calc(100% - 32px));background:var(--surface);color:var(--fg);box-shadow:0 30px 80px rgba(0,0,0,.3)}
#cfDlg::backdrop,#cfApk::backdrop{background:rgba(10,15,30,.45)}
#cfDlg .b,#cfApk .b{padding:22px;display:flex;flex-direction:column;gap:10px}
#cfDlg .r{display:flex;justify-content:space-between;gap:10px;font-size:14px}#cfDlg .r span:first-child{color:var(--muted)}
#cfSync{font-size:12px;color:var(--muted)}
@media (max-width:760px){.cfuser{max-width:92px;padding:6px 9px;font-size:12px}}
'''
BODY_JS = r'''<dialog id="cfDlg"><div class="b"><b style="font-size:18px" id="cfName"></b>
  <div class="r"><span>Kode akses</span><b class="num" id="cfCode"></b></div>
  <div class="r"><span>Berlaku sampai</span><b id="cfExp"></b></div>
  <div class="r"><span>Perangkat</span><b id="cfDev"></b></div>
  <div class="r"><span>Portofolio &amp; ★</span><span id="cfSync">tersimpan di akun</span></div>
  <p class="note" style="margin:0">Portofolio, saham yang ditandai, dan pengaturan Kalkulator tersimpan di akun Anda dan ikut muncul di perangkat lain.</p>
  <div style="display:flex;gap:8px;margin-top:6px"><button type="button" onclick="this.closest('dialog').close()" style="flex:1">Tutup</button><a id="cfOut" href="/api/logout.php" style="flex:1;text-align:center;text-decoration:none;border-radius:10px;padding:8px 12px;background:var(--bad-soft);color:var(--bad);font-weight:700">Keluar</a></div>
</div></dialog>
<script>
/* ChartFlow: nama akun, pengingat masa berlaku, dan sinkron data ke server */
(function(){
  var U=window.CF_USER, $=function(i){return document.getElementById(i)};
  var btn=$("cfUser");
  if(U&&btn){
    var first=(U.name||"Akun").split(" ")[0];
    btn.textContent="👤 "+first; btn.title=U.name;
    $("cfName").textContent="👤 "+(U.name||"Akun"); $("cfCode").textContent=U.code; $("cfExp").textContent=U.expText+(U.days>=0?" ("+U.days+" hari lagi)":"");
    $("cfDev").textContent=U.devices+" dari "+U.maxDevices;
    btn.addEventListener("click",function(){ $("cfDlg").showModal(); });
    if(U.days<=7){ var w=document.createElement("div"); w.className="cfwarn"; w.textContent=U.days<0?"Kode akses Anda sudah berakhir. Hubungi pengelola untuk perpanjang.":"⏳ Kode akses Anda berakhir "+(U.days===0?"hari ini":U.days+" hari lagi")+" ("+U.expText+"). Hubungi pengelola untuk perpanjang.";
      var st=$("status"); if(st) st.parentNode.insertBefore(w,st); }
  }
  $("cfOut").addEventListener("click",function(){ try{ (window.CF_KEYS||[]).forEach(function(k){ localStorage.removeItem(k); }); localStorage.removeItem("cf.pending"); localStorage.removeItem("cf.owner"); }catch(e){} });
  var timer=null, busy=false;
  function pending(){ try{ return JSON.parse(localStorage.getItem("cf.pending")||"{}"); }catch(e){ return {}; } }
  function flush(){
    if(busy) return; var p=pending(); if(!Object.keys(p).length) return; busy=true;
    var s=$("cfSync"); if(s) s.textContent="menyimpan…";
    fetch("/api/store.php",{method:"POST",credentials:"same-origin",headers:{"Content-Type":"application/json"},body:JSON.stringify({set:p})})
      .then(function(r){ return r.json().then(function(j){ return [r.status,j]; }); })
      .then(function(a){ busy=false;
        if(a[1].ok){ var now=pending(); Object.keys(p).forEach(function(k){ if(now[k]===p[k]) delete now[k]; }); try{ localStorage.setItem("cf.pending",JSON.stringify(now)); }catch(e){} if(s) s.textContent="tersimpan di akun ✓"; if(Object.keys(now).length) flush(); }
        else { if(s) s.textContent=a[1].msg||"gagal menyimpan"; if(a[0]===401) location.replace("/?masuk=1"); } })
      .catch(function(){ busy=false; if(s) s.textContent="offline: akan dikirim saat online"; });
  }
  window.CF_SYNC=function(k,v){
    if((window.CF_KEYS||[]).indexOf(k)<0||!U) return;
    var p=pending(); p[k]=v==null?null:String(v); try{ localStorage.setItem("cf.pending",JSON.stringify(p)); }catch(e){}
    clearTimeout(timer); timer=setTimeout(flush,1200);
  };
  window.addEventListener("online",flush); setTimeout(flush,2000);
})();
</script>
'''
s = s.replace("<style>", HEAD_JS + "<style>", 1).replace("</style>", CSS + "</style>", 1)
# ---- tombol "Pasang aplikasi": di Android langsung unduh APK
APK_JS = r"""<dialog id="cfApk"><div class="b"><b style="font-size:17px">📲 Mengunduh ChartFlow.apk…</b>
<ol style="margin:10px 0 0;padding-left:20px;line-height:1.6;font-size:14px"><li>Tunggu unduhan selesai, lalu ketuk <b>ChartFlow.apk</b> di notifikasi atau folder <b>Download</b>.</li>
<li>Bila diminta, izinkan <b>“Instal dari sumber tidak dikenal”</b> untuk browser ini.</li><li>Ketuk <b>Instal</b>, lalu buka ChartFlow dan masuk dengan kode Anda.</li></ol>
<p style="font-size:13px;opacity:.75;margin:10px 0 0">Unduhan tidak mulai? <a href="/download/ChartFlow.apk" download>Ketuk di sini</a>.</p>
<div style="text-align:right;margin-top:12px"><button type="button" class="btn" onclick="this.closest('dialog').close()">Tutup</button></div></div></dialog>
<script>(function(){
  var btn=document.getElementById("install"); if(!btn) return;
  var inApp=matchMedia("(display-mode: standalone)").matches||(document.referrer||"").indexOf("android-app://")===0;
  try{ if(inApp) sessionStorage.setItem("cf.inapp","1"); if(sessionStorage.getItem("cf.inapp")) inApp=true; }catch(e){}
  if(inApp){ btn.hidden=true; new MutationObserver(function(){ if(!btn.hidden) btn.hidden=true; }).observe(btn,{attributes:true}); return; }
  if(!/android/i.test(navigator.userAgent)) return;
  btn.hidden=false;
  btn.addEventListener("click",function(e){ e.stopImmediatePropagation(); e.preventDefault();
    var a=document.createElement("a"); a.href="/download/ChartFlow.apk"; a.download="ChartFlow.apk"; document.body.appendChild(a); a.click(); a.remove();
    var d=document.getElementById("cfApk"); if(d&&d.showModal) d.showModal(); },true);
})();</script>
"""
i = s.rindex("</body>")
s = s[:i] + BODY_JS + APK_JS + s[i:]
(out / "index.html").write_text(s, encoding="utf-8")
shutil.copy(ROOT / "sw.js", out / "sw.js")
shutil.copytree(ROOT / "icons", out / "icons")
for f in ("stocks.json", "detail.json", "cycles.json", "series.json"):
    if (ROOT / "data" / f).exists():
        shutil.copy(ROOT / "data" / f, out / "data" / f)
if (ROOT / "data" / "ohlc").is_dir():
    shutil.copytree(ROOT / "data" / "ohlc", out / "data" / "ohlc")
# ---- ringkasan publik untuk pita berjalan di beranda (tanpa sinyal per saham)
import json as _json
_d = _json.loads((ROOT / "data" / "stocks.json").read_text())
_rows = [o for o in _d.get("stocks", []) if o.get("liq", "L") == "L"]
_ORDER = ["canslim", "value", "growth", "quality", "dividend", "momentum", "swing"]


def _layak(o, mid):
    st = (o.get("m") or {}).get(mid) or {}
    s, lv, p = st.get("s"), st.get("lv") or {}, o.get("price")
    if s == "buy":
        return True
    if s != "hold" or not p:
        return False
    if mid == "canslim":
        piv = st.get("bp") or lv.get("buy")
        return bool(piv) and p <= piv * 1.05
    if mid == "momentum":
        return (o.get("momRank") or 0) >= 90
    if mid == "swing":
        return bool(st.get("p"))
    return bool(st.get("p")) and (lv.get("buy") is None or p <= lv["buy"])


_sma = [o for o in _rows if isinstance(o.get("sma200"), (int, float))]
_above = round(sum(1 for o in _sma if o["sma200"] > 0) / len(_sma) * 100) if _sma else 0
_ok = (_d.get("market") or {}).get("ok")
_reg = "naik" if _above >= 60 and _ok is not False else "tertekan" if _above < 40 or (_ok is False and _above < 50) else "campuran"
_b = ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des"]
_pd = _d.get("priceDate", "")
pub = Path(str(out) + "_pub")
pub.mkdir(parents=True, exist_ok=True)
(pub / f"{market}.json").write_text(_json.dumps({
    "m": market, "regime": _reg, "above200": _above,
    "layak": sum(1 for o in _rows if any(_layak(o, m) for m in _ORDER)),
    "date": f"{int(_pd[8:10])} {_b[int(_pd[5:7]) - 1]}" if len(_pd) >= 10 else "",
}))

print(f"Salinan {market} siap di {out}: {sum(1 for _ in out.rglob('*') if _.is_file())} file")
