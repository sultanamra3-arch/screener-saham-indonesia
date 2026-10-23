"""
Uji coba akses data saham Indonesia dari server GitHub Actions.
Hanya membaca; hasilnya ditulis ke probe/hasil.md dan probe/hasil.json.
"""
import json
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

import requests

OUT = Path(__file__).resolve().parent
TICKERS = ["BBCA", "BBRI", "BMRI", "TLKM", "ASII", "UNVR", "ICBP", "ADRO", "ANTM", "GOTO",
           "MDKA", "AMRT", "KLBF", "PGAS", "SIDO", "ITMG", "BRIS", "CPIN", "INCO", "MAPI"]
BROWSER = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36",
           "Accept": "application/json, text/plain, */*", "Accept-Language": "id-ID,id;q=0.9,en;q=0.8",
           "Referer": "https://www.idx.co.id/"}
res = {"waktu": datetime.now(timezone.utc).isoformat(timespec="seconds")}
md = [f"# Hasil uji coba akses data ({res['waktu']})", ""]


def http(name, url, headers=None, n=300):
    try:
        r = requests.get(url, headers=headers or BROWSER, timeout=30)
        body = r.text[:n].replace("\n", " ")
        ok = r.status_code == 200
        res.setdefault("http", {})[name] = {"status": r.status_code, "len": len(r.text), "ctype": r.headers.get("content-type", ""), "awal": body}
        md.append(f"- **{name}**: HTTP {r.status_code}, {len(r.text):,} karakter, `{r.headers.get('content-type', '')[:40]}`")
        md.append(f"  - awal isi: `{body[:160]}`")
        return r if ok else None
    except Exception as e:
        res.setdefault("http", {})[name] = {"error": str(e)[:300]}
        md.append(f"- **{name}**: GAGAL ({str(e)[:150]})")
        return None


# ---------------------------------------------------------------- Yahoo
md += ["## 1. Yahoo Finance (yfinance)", ""]
try:
    import yfinance as yf
    import pandas as pd

    syms = [t + ".JK" for t in TICKERS] + ["^JKSE"]
    df = yf.download(syms, period="3y", interval="1d", auto_adjust=True, progress=False, threads=True, group_by="column")
    close, vol = df["Close"], df["Volume"]
    harga = {}
    for s in syms:
        c = close[s].dropna() if s in close else pd.Series(dtype=float)
        v = vol[s].dropna() if s in vol else pd.Series(dtype=float)
        harga[s] = {"hari": len(c), "awal": str(c.index[0].date()) if len(c) else None,
                    "akhir": str(c.index[-1].date()) if len(c) else None, "volume_hari": int((v > 0).sum())}
    res["yahoo_harga"] = harga
    md.append("| Kode | Hari data | Dari | Sampai | Hari dengan volume |")
    md.append("|---|---|---|---|---|")
    for s, h in harga.items():
        md.append(f"| {s} | {h['hari']} | {h['awal']} | {h['akhir']} | {h['volume_hari']} |")

    keys = ["marketCap", "trailingPE", "priceToBook", "returnOnEquity", "returnOnAssets", "dividendYield", "payoutRatio",
            "grossMargins", "operatingMargins", "debtToEquity", "currentRatio", "freeCashflow", "trailingEps", "bookValue",
            "earningsGrowth", "earningsQuarterlyGrowth", "revenueGrowth", "sector", "industry", "longName", "sharesOutstanding",
            "fiveYearAvgDividendYield", "dividendRate"]
    info_all, fin_all = {}, {}
    for t in TICKERS:
        tk = yf.Ticker(t + ".JK")
        try:
            info = tk.info or {}
        except Exception as e:
            info = {"_err": str(e)[:100]}
        info_all[t] = {k: info.get(k) for k in keys}
        f = {}
        for name, getter in (("laba_tahunan", lambda: tk.income_stmt), ("laba_kuartal", lambda: tk.quarterly_income_stmt),
                             ("neraca_tahunan", lambda: tk.balance_sheet), ("arus_kas_tahunan", lambda: tk.cashflow)):
            try:
                x = getter()
                f[name] = {"periode": [str(c.date()) for c in x.columns], "baris": len(x.index),
                           "contoh_baris": [str(i) for i in list(x.index)[:6]]}
                if name == "laba_tahunan":
                    for row in ("Diluted EPS", "Basic EPS", "Net Income"):
                        if row in x.index:
                            f[name][row] = [None if pd.isna(v) else float(v) for v in x.loc[row].tolist()]
            except Exception as e:
                f[name] = {"error": str(e)[:150]}
        try:
            dv = tk.dividends
            f["dividen"] = {"jumlah": len(dv), "pertama": str(dv.index[0].date()) if len(dv) else None,
                            "terakhir": str(dv.index[-1].date()) if len(dv) else None,
                            "per_tahun": {str(k): round(float(v), 2) for k, v in dv.groupby(dv.index.year).sum().tail(12).items()}}
        except Exception as e:
            f["dividen"] = {"error": str(e)[:150]}
        fin_all[t] = f
        time.sleep(1.5)
    res["yahoo_info"] = info_all
    res["yahoo_laporan"] = fin_all
    md += ["", "### Rasio dari Yahoo (`info`): jumlah saham yang punya nilainya, dari 20", ""]
    for k in keys:
        n = sum(1 for t in TICKERS if info_all[t].get(k) not in (None, "", 0))
        md.append(f"- {k}: {n}/20")
    md += ["", "### Laporan keuangan dan dividen per saham", "",
           "| Kode | Tahun laba | Kuartal laba | Tahun neraca | Tahun arus kas | Dividen (pertama–terakhir, jumlah) |", "|---|---|---|---|---|---|"]
    for t, f in fin_all.items():
        g = lambda n: len(f.get(n, {}).get("periode", [])) if "periode" in f.get(n, {}) else "gagal"
        d = f.get("dividen", {})
        md.append(f"| {t} | {g('laba_tahunan')} | {g('laba_kuartal')} | {g('neraca_tahunan')} | {g('arus_kas_tahunan')} | "
                  f"{d.get('pertama')}–{d.get('terakhir')}, {d.get('jumlah')} |")
except Exception:
    md.append("GAGAL: " + traceback.format_exc()[-800:])

# ---------------------------------------------------------------- IDX, OJK, Stooq, Wikipedia
md += ["", "## 2. Situs resmi BEI (idx.co.id)", ""]
http("idx_beranda", "https://www.idx.co.id/id")
http("idx_profil_emiten", "https://www.idx.co.id/primary/ListedCompany/GetCompanyProfiles?emitenType=s&start=0&length=10")
http("idx_laporan_keuangan", "https://www.idx.co.id/primary/ListedCompany/GetFinancialReport?indexFrom=1&pageSize=12&year=2025&reportType=rdf&EmitenType=s&periode=audit&kodeEmiten=BBCA&SortColumn=KodeEmiten&SortOrder=asc")
http("idx_ringkasan_saham", "https://www.idx.co.id/primary/TradingSummary/GetStockSummary?length=10&start=0&date=20261022")
http("idx_daftar_indeks", "https://www.idx.co.id/primary/StockData/GetIndexList")
http("idx_konstituen_IDX80", "https://www.idx.co.id/primary/StockData/GetConstituent?indexCode=IDX80&start=0&length=100")
http("idx_dividen", "https://www.idx.co.id/primary/ListedCompany/GetCalendar?range=m&date=20261001")

md += ["", "## 3. OJK (Daftar Efek Syariah)", ""]
http("ojk_beranda", "https://www.ojk.go.id/id/Default.aspx")
http("ojk_des", "https://www.ojk.go.id/id/kanal/syariah/data-dan-statistik/daftar-efek-syariah/Default.aspx")

md += ["", "## 4. Stooq (cadangan harga)", ""]
http("stooq_bbca", "https://stooq.com/q/d/l/?s=bbca.jk&i=d", headers={"User-Agent": BROWSER["User-Agent"]})

md += ["", "## 5. Wikipedia (daftar indeks)", ""]
for name, url in (("wiki_idx80", "https://id.wikipedia.org/wiki/IDX80"), ("wiki_kompas100", "https://id.wikipedia.org/wiki/Kompas100"),
                  ("wiki_lq45", "https://id.wikipedia.org/wiki/LQ45"), ("wiki_lq45_en", "https://en.wikipedia.org/wiki/LQ45")):
    http(name, url, headers={"User-Agent": "ScreenerSahamBot/0.1 (https://github.com/sultanamra3-arch/screener-saham-indonesia)"}, n=120)

(OUT / "hasil.json").write_text(json.dumps(res, indent=1, default=str))
(OUT / "hasil.md").write_text("\n".join(md))
import os
if os.environ.get("GITHUB_STEP_SUMMARY"):
    with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as f:
        f.write("\n".join(md))
print("\n".join(md))
