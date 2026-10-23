"""
Uji coba kedua: daftar semua saham BEI, cakupan Yahoo untuk semuanya, sebaran likuiditas,
dan apakah Yahoo membatasi permintaan fundamental dalam jumlah besar. Hanya membaca.
"""
import io
import json
import os
import re
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

OUT = Path(__file__).resolve().parent
UA = {"User-Agent": "ScreenerSahamBot/0.2 (https://github.com/sultanamra3-arch/screener-saham-indonesia)"}
BROWSER = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"}
res = {"waktu": datetime.now(timezone.utc).isoformat(timespec="seconds")}
md = [f"# Uji coba kedua ({res['waktu']})", ""]
CODE = re.compile(r"^[A-Z]{4}$")

# ---------------------------------------------------------------- 1. daftar induk
md += ["## 1. Daftar semua saham BEI", ""]
lists = {}

# a) Yahoo screener
try:
    import yfinance as yf
    from yfinance import EquityQuery

    q = EquityQuery("eq", ["exchange", "JKT"])
    codes, off = set(), 0
    while off < 1500:
        r = yf.screen(q, offset=off, size=250, sortField="intradaymarketcap", sortAsc=False)
        quotes = (r or {}).get("quotes") or []
        for x in quotes:
            s = str(x.get("symbol", ""))
            if s.endswith(".JK"):
                codes.add(s[:-3])
        if len(quotes) < 250:
            break
        off += 250
        time.sleep(1)
    lists["yahoo_screener"] = sorted(codes)
    md.append(f"- **Yahoo screener (bursa JKT)**: {len(codes)} kode")
except Exception as e:
    md.append(f"- **Yahoo screener**: GAGAL ({str(e)[:200]})")

# b) Wikipedia
def wiki_tables(lang, title):
    r = requests.get(f"https://{lang}.wikipedia.org/w/api.php", params={"action": "parse", "page": title, "prop": "text",
                     "format": "json", "formatversion": "2", "redirects": "1"}, headers=UA, timeout=60)
    j = r.json()
    if "parse" not in j:
        return None, j.get("error", {}).get("info", "tidak ada")
    return pd.read_html(io.StringIO(j["parse"]["text"])), j["parse"].get("title")

for lang, title in (("id", "Daftar perusahaan yang tercatat di Bursa Efek Indonesia"),
                    ("id", "Daftar emiten di Bursa Efek Indonesia"),
                    ("en", "List of companies listed on the Indonesia Stock Exchange")):
    try:
        tabs, t2 = wiki_tables(lang, title)
        if tabs is None:
            md.append(f"- Wikipedia {lang} '{title}': tidak ada ({t2})")
            continue
        codes = set()
        for t in tabs:
            for col in t.columns:
                vals = t[col].astype(str).str.strip().str.replace(".JK", "", regex=False)
                hit = vals[vals.str.match(CODE)]
                if len(hit) > 0.5 * len(t) and len(t) > 5:
                    codes |= set(hit)
        lists[f"wiki_{lang}"] = sorted(codes)
        md.append(f"- **Wikipedia {lang} '{t2}'**: {len(tabs)} tabel, {len(codes)} kode")
    except Exception as e:
        md.append(f"- Wikipedia {lang} '{title}': GAGAL ({str(e)[:150]})")

allc = set()
for v in lists.values():
    allc |= set(v)
md.append(f"- **Gabungan semua sumber**: {len(allc)} kode")
if "yahoo_screener" in lists and any(k.startswith("wiki") for k in lists):
    w = set().union(*[set(v) for k, v in lists.items() if k.startswith("wiki")])
    y = set(lists["yahoo_screener"])
    md.append(f"  - hanya di Yahoo: {len(y - w)} · hanya di Wikipedia: {len(w - y)} · di keduanya: {len(y & w)}")
    md.append(f"  - contoh hanya di Yahoo: {sorted(y - w)[:15]}")
    md.append(f"  - contoh hanya di Wikipedia: {sorted(w - y)[:15]}")
res["lists"] = {k: len(v) for k, v in lists.items()}

# ---------------------------------------------------------------- 2. harga semua saham + likuiditas
md += ["", "## 2. Harga semua saham dari Yahoo dan sebaran likuiditas", ""]
try:
    syms = sorted(allc)
    t0 = time.time()
    frames_c, frames_v = [], []
    for i in range(0, len(syms), 100):
        chunk = [s + ".JK" for s in syms[i:i + 100]]
        df = yf.download(chunk, period="1y", interval="1d", auto_adjust=False, progress=False, threads=True, group_by="column")
        frames_c.append(df["Close"]); frames_v.append(df["Volume"])
        time.sleep(2)
    close = pd.concat(frames_c, axis=1); vol = pd.concat(frames_v, axis=1)
    md.append(f"- Waktu unduh harga {len(syms)} saham: {time.time() - t0:.0f} detik")
    have = [c for c in close.columns if close[c].notna().sum() > 0]
    fresh = [c for c in have if close[c].last_valid_index() >= close.index[-1] - pd.Timedelta(days=7)]
    md.append(f"- Ada data harga: {len(have)} · masih aktif diperdagangkan seminggu terakhir: {len(fresh)}")
    days = {c: int(close[c].notna().sum()) for c in have}
    md.append(f"- Riwayat < 200 hari (baru/IPO atau bolong): {sum(1 for v in days.values() if v < 200)}")
    val = (close * vol).tail(63)
    adv = val.mean().dropna() / 1e9  # miliar rupiah per hari
    zero = (vol.tail(63) == 0).sum()
    bins = [(">= Rp50 M", adv >= 50), ("Rp10–50 M", (adv >= 10) & (adv < 50)), ("Rp5–10 M", (adv >= 5) & (adv < 10)),
            ("Rp1–5 M", (adv >= 1) & (adv < 5)), ("Rp0,1–1 M", (adv >= .1) & (adv < 1)), ("< Rp0,1 M", adv < .1)]
    md.append("- Sebaran rata-rata nilai transaksi harian (3 bulan):")
    for name, m in bins:
        md.append(f"  - {name}: {int(m.sum())} saham")
    md.append(f"- Saham dengan > 20 hari tanpa transaksi dalam 3 bulan: {int((zero > 20).sum())}")
    top = adv.sort_values(ascending=False)
    md.append(f"- Nilai transaksi saham ke-150: Rp{top.iloc[149]:.1f} M/hari · ke-250: Rp{top.iloc[249]:.1f} M/hari" if len(top) > 250 else "")
    res["likuiditas"] = {k.replace(".JK", ""): round(float(v), 3) for k, v in top.items()}
except Exception:
    md.append("GAGAL: " + traceback.format_exc()[-600:])

# ---------------------------------------------------------------- 3. uji beban fundamental Yahoo
md += ["", "## 3. Uji beban fundamental Yahoo (info + laporan laba + dividen)", ""]
try:
    sample = list(top.index[:60]) + list(top.index[150:210]) + list(top.index[-60:])
    ok = {"info": 0, "laba": 0, "dividen": 0}
    err, t0 = [], time.time()
    for s in sample:
        tk = yf.Ticker(s)
        try:
            if (tk.info or {}).get("marketCap"):
                ok["info"] += 1
        except Exception as e:
            err.append(f"info {s}: {str(e)[:80]}")
        try:
            if len(tk.income_stmt.columns) >= 1:
                ok["laba"] += 1
        except Exception as e:
            err.append(f"laba {s}: {str(e)[:80]}")
        try:
            tk.dividends
            ok["dividen"] += 1
        except Exception as e:
            err.append(f"dividen {s}: {str(e)[:80]}")
        time.sleep(0.7)
    el = time.time() - t0
    md.append(f"- {len(sample)} saham (60 paling likuid, 60 menengah, 60 paling sepi) dalam {el:.0f} detik "
              f"(±{el / len(sample):.1f} detik per saham → semua saham ±{el / len(sample) * len(allc) / 60:.0f} menit)")
    md.append(f"- Berhasil: info {ok['info']}, laporan laba {ok['laba']}, dividen {ok['dividen']} dari {len(sample)}")
    md.append(f"- Error: {len(err)}" + (f" · contoh: {err[:5]}" if err else ""))
    md.append(f"- Tanda dibatasi (429/Too Many Requests): {sum('429' in e or 'Too Many' in e for e in err)}")
except Exception:
    md.append("GAGAL: " + traceback.format_exc()[-600:])

# ---------------------------------------------------------------- 4. e-IPO dan file DES OJK
md += ["", "## 4. e-IPO dan file Daftar Efek Syariah", ""]
for name, url in (("e-ipo", "https://e-ipo.co.id/en/ipo/index"), ("e-ipo_id", "https://e-ipo.co.id/id/ipo/index")):
    try:
        r = requests.get(url, headers=BROWSER, timeout=30)
        md.append(f"- {name}: HTTP {r.status_code}, {len(r.text):,} karakter, judul: "
                  f"`{(re.search(r'<title>(.*?)</title>', r.text, re.S) or [None, ''])[1].strip()[:80]}`")
    except Exception as e:
        md.append(f"- {name}: GAGAL {str(e)[:120]}")
try:
    r = requests.get("https://www.ojk.go.id/id/kanal/syariah/data-dan-statistik/daftar-efek-syariah/Default.aspx", headers=BROWSER, timeout=60)
    links = sorted(set(re.findall(r'href="([^"]+\.(?:xlsx?|pdf|zip))"', r.text, re.I)))
    md.append(f"- OJK halaman DES: {len(links)} tautan file. Contoh: {links[:6]}")
    pages = sorted(set(re.findall(r'href="([^"]*daftar-efek-syariah[^"]*)"', r.text, re.I)))[:8]
    md.append(f"- Tautan halaman DES lain: {pages}")
except Exception as e:
    md.append(f"- OJK: GAGAL {str(e)[:120]}")

(OUT / "hasil2.md").write_text("\n".join(md))
(OUT / "hasil2.json").write_text(json.dumps(res, indent=1, default=str))
if os.environ.get("GITHUB_STEP_SUMMARY"):
    open(os.environ["GITHUB_STEP_SUMMARY"], "a").write("\n".join(md))
print("\n".join(md))
