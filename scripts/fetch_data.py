"""
Pengambil data Screener Saham Indonesia (BEI).

Sumber (semua gratis):
  - Daftar saham, harga, volume, rasio, laporan keuangan, riwayat dividen: Yahoo Finance (yfinance)
  - Label syariah: Daftar Efek Syariah OJK (file Excel terbaru)
  - Deteksi IPO baru: e-IPO (best effort), plus data/tambahan.txt untuk kode yang ingin dipantau

Hasil: data/stocks.json, data/signals.json, data/fund_cache.json, data/syariah.json
"""
from __future__ import annotations

import io
import json
import math
import os
import re
import sys
import time
import traceback
from datetime import date, datetime, timezone
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ohlc
import strategies  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OUT_FILE = DATA / "stocks.json"
SIG_FILE = DATA / "signals.json"
CACHE_FILE = DATA / "fund_cache.json"
SYARIAH_FILE = DATA / "syariah.json"
EXTRA_FILE = DATA / "tambahan.txt"
INDEX = "^JKSE"
ETF_CANDIDATES = ["XIIT", "XPLQ", "XBLQ", "XISI", "XIJI", "XISC", "XIIC", "XIHD", "XKIV", "XISR", "XPES", "XSBC", "XMTS", "XPFT", "XIPI"]
LIQ_HI, LIQ_LO = 5.0, 1.0  # miliar rupiah per hari: likuid / kurang likuid
BROWSER = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"}
CODE = re.compile(r"^[A-Z]{4}$")
WARN: list[str] = []


def log(*a):
    print(*a, flush=True)


def summary(md: str):
    p = os.environ.get("GITHUB_STEP_SUMMARY")
    if p:
        with open(p, "a", encoding="utf-8") as f:
            f.write(md + "\n")


def fnum(v):
    try:
        v = float(v)
        return v if math.isfinite(v) else None
    except Exception:
        return None


def clean(d: dict) -> dict:
    out = {}
    for k, v in d.items():
        if isinstance(v, float):
            out[k] = round(v, 4) if math.isfinite(v) else None
        else:
            out[k] = v
    return out


# ---------------------------------------------------------------- daftar saham
def universe() -> dict[str, str]:
    import yfinance as yf
    from yfinance import EquityQuery

    q = EquityQuery("eq", ["exchange", "JKT"])
    names, off = {}, 0
    while off < 2000:
        r = yf.screen(q, offset=off, size=250, sortField="intradaymarketcap", sortAsc=False)
        quotes = (r or {}).get("quotes") or []
        for x in quotes:
            s = str(x.get("symbol", ""))
            if s.endswith(".JK") and CODE.match(s[:-3]):
                names[s[:-3]] = x.get("longName") or x.get("shortName") or s[:-3]
        if len(quotes) < 250:
            break
        off += 250
        time.sleep(1)
    log(f"Yahoo screener: {len(names)} saham")
    return names


def ipo_codes() -> set[str]:
    """Kode saham dari halaman e-IPO (best effort; hanya dipakai bila Yahoo punya harganya)."""
    out = set()
    for url in ("https://e-ipo.co.id/id/ipo/index", "https://e-ipo.co.id/en/ipo/index"):
        try:
            r = requests.get(url, headers=BROWSER, timeout=30)
            if r.status_code == 200:
                out |= set(re.findall(r"\(([A-Z]{4})\)", r.text)) | set(re.findall(r">\s*([A-Z]{4})\s*<", r.text))
        except Exception as e:
            log(f"  e-IPO: {e}")
    return out


def extra_codes() -> set[str]:
    if not EXTRA_FILE.exists():
        return set()
    return {x.strip().upper() for x in re.split(r"[\s,;]+", EXTRA_FILE.read_text()) if CODE.match(x.strip().upper())}


# ---------------------------------------------------------------- syariah (OJK)
def syariah() -> dict:
    cur = json.loads(SYARIAH_FILE.read_text()) if SYARIAH_FILE.exists() else {}
    if cur.get("checked") and (date.today() - date.fromisoformat(cur["checked"])).days < 7:
        return cur
    base = "https://www.ojk.go.id"
    try:
        r = requests.get(f"{base}/id/kanal/syariah/data-dan-statistik/daftar-efek-syariah/Default.aspx", headers=BROWSER, timeout=60)
        pages = set(re.findall(r'href="([^"]*daftar-efek-syariah/Pages/Daftar-Efek-Syariah-KEP[^"]+\.aspx)"', r.text, re.I))

        def key(u):
            y = re.search(r"(\d{4})\.aspx$", u)
            n = re.search(r"KEP-?(\d+)", u, re.I)
            return (int(y.group(1)) if y else 0, int(n.group(1)) if n else 0)

        for page in sorted(pages, key=key, reverse=True)[:3]:
            url = page if page.startswith("http") else base + page
            pr = requests.get(url, headers=BROWSER, timeout=60)
            xl = re.findall(r'href="([^"]+\.xlsx?)"', pr.text, re.I)
            for f in xl:
                furl = f if f.startswith("http") else base + f
                fr = requests.get(furl, headers=BROWSER, timeout=120)
                if fr.status_code != 200:
                    continue
                import pandas as pd

                codes = set()
                for _, df in pd.read_excel(io.BytesIO(fr.content), sheet_name=None, header=None).items():
                    for col in df.columns:
                        vals = df[col].astype(str).str.strip().str.upper()
                        codes |= set(vals[vals.str.match(r"^[A-Z]{4}$")])
                if len(codes) > 300:
                    res = {"checked": date.today().isoformat(), "source": furl, "kep": url.split("/")[-1], "codes": sorted(codes)}
                    SYARIAH_FILE.write_text(json.dumps(res))
                    log(f"Daftar Efek Syariah: {len(codes)} saham ({res['kep']})")
                    return res
        WARN.append("File Daftar Efek Syariah OJK tidak ditemukan; memakai daftar sebelumnya.")
    except Exception as e:
        WARN.append(f"Daftar Efek Syariah OJK gagal diambil ({str(e)[:100]}); memakai daftar sebelumnya.")
    if cur:
        cur["checked"] = date.today().isoformat()
        SYARIAH_FILE.write_text(json.dumps(cur))
    return cur


# ---------------------------------------------------------------- harga
def fetch_prices(codes: list[str]):
    import pandas as pd
    import yfinance as yf

    syms = [c + ".JK" for c in codes] + [INDEX]
    fc, fv = [], []
    for i in range(0, len(syms), 100):
        chunk = syms[i:i + 100]
        for attempt in range(3):
            try:
                df = yf.download(chunk, period="3y", interval="1d", auto_adjust=True, progress=False, threads=True, group_by="column")
                if "Close" in df and not df["Close"].empty:
                    c, v = df["Close"], df["Volume"]
                    if isinstance(c, pd.Series):
                        c, v = c.to_frame(chunk[0]), v.to_frame(chunk[0])
                    fc.append(c); fv.append(v)
                    ohlc.keep(df)
                    break
            except Exception as e:
                log(f"  harga batch {i}: {e}")
            time.sleep(10 * (attempt + 1))
        time.sleep(2)
    if not fc:
        return None, None
    ren = lambda c: c[:-3] if str(c).endswith(".JK") else c
    close = pd.concat(fc, axis=1)
    close = close.loc[:, ~close.columns.duplicated()].rename(columns=ren).dropna(how="all")
    vol = pd.concat(fv, axis=1)
    vol = vol.loc[:, ~vol.columns.duplicated()].rename(columns=ren).reindex(close.index)
    # buang hari terakhir hanya bila hampir semua saham kosong (data hari itu belum masuk)
    filled = close.iloc[-1].notna().mean()
    log(f"  baris terakhir {close.index[-1].date()}: {filled:.0%} saham terisi")
    if filled < 0.2:
        WARN.append(f"Harga {close.index[-1].date()} baru {filled:.0%} terisi; memakai hari sebelumnya.")
        close, vol = close.iloc[:-1], vol.iloc[:-1]
    return close, vol


# ---------------------------------------------------------------- fundamental
def _row(df, *names):
    for n in names:
        if df is not None and n in df.index:
            return df.loc[n]
    return None


def _cagr(vals):
    v = [x for x in vals if x is not None]
    if len(v) < 2 or v[0] <= 0 or v[-1] <= 0:
        return None
    return ((v[-1] / v[0]) ** (1 / (len(v) - 1)) - 1) * 100


def ttm_from_hist(dvh: list) -> float:
    """Dividen 12 bulan terakhir dari [[tanggal, nilai], ...]: jendela 330 hari mundur dari dividen terakhir."""
    if not dvh:
        return 0.0
    last = date.fromisoformat(dvh[-1][0])
    if (date.today() - last).days >= 400:
        return 0.0
    return float(sum(v for d, v in dvh if (last - date.fromisoformat(d)).days < 330))


def fundamentals(code: str) -> dict | None:
    import pandas as pd
    import yfinance as yf

    tk = yf.Ticker(code + ".JK")
    info = tk.info or {}
    if not info or not (info.get("marketCap") or info.get("regularMarketPrice") or info.get("currentPrice")):
        return None
    f = {"sector": info.get("sector") or "", "industry": info.get("industry") or "", "company": info.get("longName") or info.get("shortName")}
    mc = fnum(info.get("marketCap"))
    f["mcap"] = mc / 1e9 if mc else None  # miliar rupiah
    f["pe"] = fnum(info.get("trailingPE"))
    f["pb"] = fnum(info.get("priceToBook"))
    pct = lambda k: (fnum(info.get(k)) * 100) if fnum(info.get(k)) is not None else None
    f["payout"] = pct("payoutRatio")
    f["roe"] = pct("returnOnEquity")
    f["gm"] = pct("grossMargins")
    f["om"] = pct("operatingMargins")
    f["epsQ"] = pct("earningsQuarterlyGrowth")
    f["salesQ"] = pct("revenueGrowth")
    de = fnum(info.get("debtToEquity"))
    f["de"] = de / 100 if de is not None else None
    f["cr"] = fnum(info.get("currentRatio"))
    f["eps"] = fnum(info.get("trailingEps"))
    f["bvps"] = fnum(info.get("bookValue"))
    f["beta"] = fnum(info.get("beta"))
    exd = info.get("exDividendDate")
    try:
        f["exInfo"] = datetime.fromtimestamp(int(exd), timezone.utc).strftime("%Y-%m-%d") if exd else None
    except Exception:
        f["exInfo"] = None
    fcf = fnum(info.get("freeCashflow"))
    f["pfcf"] = mc / fcf if mc and fcf and fcf > 0 else None

    # laporan laba tahunan (±4 tahun)
    try:
        inc = tk.income_stmt
        cols = sorted(inc.columns)
        eps = _row(inc, "Diluted EPS", "Basic EPS")
        f["epsA"] = [[c.year, round(float(eps[c]), 4)] for c in cols if eps is not None and pd.notna(eps[c])]
        rev = _row(inc, "Total Revenue", "Operating Revenue")
        revs = [float(rev[c]) if rev is not None and pd.notna(rev[c]) else None for c in cols]
        f["salesG"] = _cagr(revs)
        e = [v for _, v in f["epsA"]]
        f["epsG"] = _cagr(e)
        f["epsGy"] = len(e)
        f["epsTTM"] = ((e[-1] / e[-2] - 1) * 100) if len(e) >= 2 and e[-2] > 0 else None
        ebit = _row(inc, "EBIT", "Operating Income")
        bs = tk.balance_sheet
        debt, eq = _row(bs, "Total Debt"), _row(bs, "Stockholders Equity", "Common Stock Equity")
        if ebit is not None and eq is not None:
            c = max(set(ebit.index) & set(eq.index))
            cap = float(eq[c]) + (float(debt[c]) if debt is not None and pd.notna(debt.get(c)) else 0)
            if cap > 0 and pd.notna(ebit[c]):
                f["roic"] = float(ebit[c]) * (1 - 0.22) / cap * 100
    except Exception as e:
        log(f"  laporan {code}: {str(e)[:80]}")

    # riwayat dividen (Yahoo: sampai ±20 tahun)
    try:
        dv = tk.dividends
        if len(dv):
            by = dv.groupby(dv.index.year).sum()
            last_full = date.today().year - 1
            by = by[by.index <= last_full]
            f["dpsY"] = float(by.get(last_full, 0.0))
            yrs = 0
            for y in range(last_full, last_full - 30, -1):
                if by.get(y, 0) > 0:
                    yrs += 1
                else:
                    break
            f["divYears"] = yrs
            if by.get(last_full - 5, 0) > 0 and by.get(last_full, 0) > 0:
                f["divGrowth5y"] = ((by[last_full] / by[last_full - 5]) ** (1 / 5) - 1) * 100
            # 12 bulan terakhir dihitung mundur 330 hari dari dividen terakhir: dividen tahunan yang
            # jadwalnya bergeser beberapa minggu tidak terhitung dua kali (dulu 365 hari -> yield BBNI 2x lipat)
            ttm = dv[dv.index > dv.index[-1] - pd.Timedelta(days=330)].sum() if (pd.Timestamp.now(tz=dv.index.tz) - dv.index[-1]).days < 400 else 0.0
            f["dpsTTM"] = float(ttm)
            f["dvh"] = [[str(i.date()), round(float(v), 4)] for i, v in dv[dv.index >= dv.index[-1] - pd.Timedelta(days=800)].items()]
        else:
            f["divYears"], f["dpsY"], f["dpsTTM"] = 0, 0.0, 0.0
    except Exception as e:
        log(f"  dividen {code}: {str(e)[:80]}")
    return clean(f)


# ---------------------------------------------------------------- teknikal ringkas
def flow(c, v, last) -> dict:
    """Untuk tab 'Ramai hari ini': perubahan dari penutupan kemarin, volume hari ini dibanding
    rata-rata 20 hari bursa sebelumnya, dan nilai transaksi hari ini. Kosong bila tidak ditransaksikan hari itu."""
    out = {"chg1d": None, "volR": None, "val1d": None}
    try:
        c = c.dropna()
        if len(c) < 2 or c.index[-1] != last:
            return out
        p = float(c.iloc[-1])
        out["chg1d"] = round((p / float(c.iloc[-2]) - 1) * 100, 2)
        if v is not None:
            v = v.reindex(c.index).fillna(0)
            if len(v) >= 21:
                avg, today = float(v.iloc[-21:-1].mean()), float(v.iloc[-1])
                if avg > 0:
                    out["volR"] = round(today / avg, 2)
                out["val1d"] = round(today * p)
    except Exception:
        pass
    return out


def technicals(s) -> dict:
    import pandas as pd

    s = s.dropna()
    out = {k: None for k in ("price", "sma20", "sma50", "sma200", "perf1m", "perf6m", "perf1y", "perfYtd", "hi52", "perf1w", "perf3m", "perf1mP", "perf3mP")}
    if len(s) < 25:
        return out
    p = float(s.iloc[-1])
    out["price"] = p
    for n in (20, 50, 200):
        if len(s) >= n:
            out[f"sma{n}"] = (p / float(s.iloc[-n:].mean()) - 1) * 100
    last = s.index[-1]

    def back(days):
        prev = s[s.index <= last - pd.Timedelta(days=days)]
        return float(prev.iloc[-1]) if len(prev) else None

    for k, d in (("perf1m", 30), ("perf6m", 182), ("perf1y", 365)):
        b = back(d)
        out[k] = (p / b - 1) * 100 if b else None
    # untuk Peta sektor: 1 minggu, 3 bulan, dan nilai yang sama 5 hari bursa lalu (arah peringkat)
    ago = lambda k: float(s.iloc[-1 - k]) if len(s) > k else None
    chg = lambda x, y: (x / y - 1) * 100 if x and y else None
    out["perf1w"] = chg(p, ago(5))
    out["perf3m"] = chg(p, ago(63))
    out["perf1mP"] = chg(ago(5), ago(26))
    out["perf3mP"] = chg(ago(5), ago(68))
    py = s[s.index.year < last.year]
    out["perfYtd"] = (p / float(py.iloc[-1]) - 1) * 100 if len(py) else None
    yr = s[s.index > last - pd.Timedelta(days=365)]
    out["hi52"] = (p / float(yr.max()) - 1) * 100
    return out


def etf_info(close) -> dict:
    import yfinance as yf

    res = {}
    for t in ETF_CANDIDATES:
        try:
            df = yf.download(t + ".JK", period="2y", interval="1d", auto_adjust=True, progress=False)
            if df is None or df.empty:
                continue
            c = df["Close"].squeeze().dropna()
            if len(c) < 60 or (c.index[-1] - c.index[-2]).days > 10:
                continue
            info = {}
            try:
                info = yf.Ticker(t + ".JK").info or {}
            except Exception:
                pass
            d = {"name": info.get("longName") or info.get("shortName") or t, "aum": fnum(info.get("totalAssets")),
                 "expense": fnum(info.get("netExpenseRatio") or info.get("annualReportExpenseRatio"))}
            d.update(technicals(c))
            vol = df["Volume"].squeeze().tail(63)
            d["adv"] = float((c.tail(63) * vol).mean() / 1e9) if len(vol) else None
            res[t] = clean(d)
            time.sleep(1)
        except Exception as e:
            log(f"  ETF {t}: {str(e)[:80]}")
    if close is not None and INDEX in close:
        res["IHSG"] = clean({"name": "Indeks Harga Saham Gabungan", **technicals(close[INDEX])})
    return res


# ---------------------------------------------------------------- siklus & Fibonacci
CYC_FILE = DATA / "cycles.json"
SERIES_FILE = DATA / "series.json"
CYC_STATE = DATA / "cycles_state.json"


def _track(idr: bool, fees):
    """Rekam jejak Rencana beli (hanya update sore/penuh)."""
    try:
        import notify_telegram as nt
        import plan_track

        d = json.loads(OUT_FILE.read_text())
        c = json.loads(CYC_FILE.read_text())
        st = d.get("stats") or {}
        bad = {m for m in ("canslim", "momentum", "swing") if (st.get(m) or {}).get("n", 0) >= 10 and (st.get(m) or {}).get("avg", 0) < 0}
        allow = nt.INV if nt.market_regime(d, c) == "tertekan" else [m for m in nt.ORDER if m not in bad]
        pl = plan_track.plans(d, c, allow, nt.layak, idr=idr, liquid_only=idr)
        s = plan_track.update(DATA / "plan_track.json", DATA / "ohlc", d["priceDate"], pl, fees)
        sc = plan_track.score(s)
        log(f"Rekam jejak: {len(pl)} rencana hari ini, {len(s['open'])} berjalan, {sc.get('n', 0)} selesai")
    except Exception as e:
        log(f"  rekam jejak gagal: {e}")


def _ohlc(close, volume, cols):
    try:
        n = ohlc.write(DATA / "ohlc", close, volume, cols, {"IHSG": INDEX}, rename=lambda c: c[:-3] if str(c).endswith(".JK") else c, decimals=0)
        log(f"Data candlestick: {n} file")
    except Exception as e:
        log(f"  data candlestick gagal: {e}")


def run_cycles(close, indices: dict, cfg: dict, stock_cols: list, breadth_cols: list, tick=None, vix=None, persist=True):
    """Tidak boleh menggagalkan pembaruan utama: kesalahan hanya dicatat."""
    try:
        import cycles
        import yfinance as yf

        long = {}
        for name, sym in indices.items():
            try:
                df = yf.download(sym, period="max", interval="1d", auto_adjust=True, progress=False)
                c = df["Close"].squeeze().dropna()
                if len(c) > 1000:
                    long[name] = c
            except Exception as e:
                log(f"  riwayat panjang {sym}: {e}")
        state = json.loads(CYC_STATE.read_text()) if CYC_STATE.exists() else {}
        out, series = cycles.run(close, indices, long, stock_cols, breadth_cols, cfg, state, tick=tick, vix=vix)
        CYC_FILE.write_text(json.dumps(out, separators=(",", ":")))
        SERIES_FILE.write_text(cycles.dump_series(series))
        if persist:  # update siang tidak menyimpan status area support (dasar perbandingan tetap penutupan kemarin)
            CYC_STATE.write_text(json.dumps(state, separators=(",", ":")))
        lines = ["### Siklus & Fibonacci"]
        for name, t in out.get("tests", {}).items():
            if not t or "time" not in t:
                lines.append(f"- {name}: uji tidak tersedia ({(t or {}).get('error', 'riwayat kurang')})")
                continue
            useful = [k for sec in ("time", "price", "season") for k, v in t[sec].items() if v and v["verdict"] == "berguna"]
            lines.append(f"- {name}: data {t['from']}–{t['to']}, {t['pivots']} titik balik; unsur yang terbukti berguna: {', '.join(useful) or 'tidak ada'}")
        summary("\n".join(lines))
        log("Siklus & Fibonacci selesai")
    except Exception as e:
        import traceback

        traceback.print_exc()
        summary(f"- Peringatan: Siklus & Fibonacci gagal dihitung ({type(e).__name__}: {str(e)[:150]})")


# ---------------------------------------------------------------- utama
def load_state() -> dict:
    if SIG_FILE.exists():
        try:
            st = json.loads(SIG_FILE.read_text())
            if isinstance(st, dict) and st.get("v") == 2:
                return st
        except Exception:
            pass
    return {"v": 2}



def slim_rows(rows):
    """Pisahkan rincian syarat (c), riwayat sinyal (h), dan trend template (tt) ke data/detail.json
    supaya stocks.json yang diunduh saat halaman dibuka jauh lebih kecil."""
    import copy
    slim, det, labels = copy.deepcopy(rows), {}, {}
    code = lambda v: "1" if v == 1 else "0" if v == 0 else "2" if v == 2 else "n"
    for o in slim:
        d = {}
        for mid, st in (o.get("m") or {}).items():
            c, h = st.pop("c", None), st.pop("h", None)
            if c:
                st["cs"] = "".join(code(x[2]) for x in c)
                labels.setdefault(mid, [x[0] for x in c])
            dd = {k: v for k, v in (("c", c), ("h", h)) if v}
            if dd:
                d[mid] = dd
        for k in ("tt", "insL", "ksL"):
            v = o.pop(k, None)
            if v:
                d["_" + k] = v
        if d:
            d_key = o["ticker"]
            det[d_key] = d
    return slim, det, labels

def main():
    DATA.mkdir(exist_ok=True)
    t0 = time.time()
    names = universe()
    if len(names) < 400:
        raise RuntimeError(f"Daftar saham dari Yahoo terlalu sedikit ({len(names)}); dibatalkan agar data lama tidak tertimpa")
    extra = extra_codes() | {c for c in ipo_codes() if c not in names}
    codes = sorted(set(names) | extra)
    limit = int(os.environ.get("LIMIT", "0") or 0)
    if limit:
        codes = codes[:limit]

    log(f"Mengambil harga {len(codes)} saham ...")
    close, volume = fetch_prices(codes)
    if close is None:
        raise RuntimeError("Harga dari Yahoo gagal diambil")
    have = [c for c in codes if c in close and close[c].notna().sum() > 0]
    dropped = sorted(set(extra) - set(have))
    codes = have
    day = close.index[-1].strftime("%Y-%m-%d")
    log(f"  {len(codes)} saham dengan harga, harga penutupan {day}")

    # likuiditas: rata-rata nilai transaksi 3 bulan (miliar rupiah)
    val = (close[codes] * volume[codes]).tail(63)
    adv = (val.mean() / 1e9).to_dict()
    eligible = [c for c in codes if (adv.get(c) or 0) >= LIQ_LO]

    syr = syariah()
    syr_codes = set(syr.get("codes") or [])

    cache = json.loads(CACHE_FILE.read_text()) if CACHE_FILE.exists() else {}
    log(f"Mengambil fundamental {len(codes)} saham ...")
    fresh, stale, missing = 0, 0, []
    for i, c in enumerate(codes, 1):
        f = None
        for attempt in range(2):
            try:
                f = fundamentals(c)
                break
            except Exception as e:
                msg = str(e)
                if "429" in msg or "Too Many" in msg:
                    time.sleep(30 * (attempt + 1))
                else:
                    break
        if f:
            f["asOf"] = day
            cache[c] = f
            fresh += 1
        elif c in cache:
            stale += 1
        else:
            missing.append(c)
        if i % 100 == 0:
            log(f"  {i}/{len(codes)}")
        time.sleep(0.4)
    CACHE_FILE.write_text(json.dumps(cache, separators=(",", ":")))

    rows = []
    for c in codes:
        f = dict(cache.get(c) or {})
        f.pop("asOf", None)
        o = {"ticker": c, "company": f.pop("company", None) or names.get(c, c), **f}
        o.update(technicals(close[c]))
        o.update(flow(close[c], volume[c] if volume is not None and c in volume else None, close.index[-1]))
        a = adv.get(c)
        o["adv"] = round(a, 3) if a is not None and math.isfinite(a) else None
        o["liq"] = "L" if (a or 0) >= LIQ_HI else "K" if (a or 0) >= LIQ_LO else "T"
        o["syariah"] = (c in syr_codes) if syr_codes else None
        o["days"] = int(close[c].notna().sum())
        if c in extra and c not in names:
            o["ipo"] = True
        if o.get("dvh"):  # hitung ulang dari riwayat (juga memperbaiki data lama di cache)
            o["dpsTTM"] = ttm_from_hist(o["dvh"])
        if o.get("price") and o.get("dpsTTM") is not None:
            o["div"] = o["dpsTTM"] / o["price"] * 100
        rows.append(clean(o))

    prev_day = None
    if OUT_FILE.exists():
        try:
            prev_day = json.loads(OUT_FILE.read_text()).get("priceDate")
        except Exception:
            pass
    state = load_state()
    log("Menghitung 7 metode ...")
    res = strategies.run(rows, close, volume, day, state, eligible)
    import dataguard
    dq = dataguard.apply(rows, close)
    log(f"  penjaga data: {len(dq)} saham ditandai janggal")
    import divcal
    import ksei
    today = date.fromisoformat(day)
    for r in rows:
        nd = divcal.next_div(r.pop("dvh", None), r.pop("exInfo", None), today)
        if nd and r.get("price"):
            nd["y"] = round(nd["amt"] / r["price"] * 100, 2)
        if nd:
            r["dv"] = nd
    log(f"  kalender dividen: {sum(1 for r in rows if r.get('dv'))} saham dengan ex-date ≤ {divcal.HORIZON} hari")
    log("Kepemilikan efek bulanan (KSEI) ...")
    ks_new = False
    try:
        kc, _ = ksei.update(DATA / "ksei.json", log)
        ks_new = bool(kc.get("months")) and kc["months"][-1] != kc.get("announced")
        if ks_new and prev_day != day:  # pesan pagi akan terkirim: tandai bulan ini sudah dikabarkan
            kc["announced"] = kc["months"][-1]
            (DATA / "ksei.json").write_text(json.dumps(kc, separators=(",", ":")))
        ksei.apply(rows, kc)
    except Exception as e:
        log(f"  KSEI gagal: {str(e)[:120]}")
    SIG_FILE.write_text(json.dumps(state, separators=(",", ":")))
    out = {
        "updatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "priceDate": day, "prevPriceDate": prev_day, "newSession": prev_day != day,
        "ksNew": ks_new,
        "count": len(rows), "liqCount": {k: sum(1 for r in rows if r["liq"] == k) for k in "LKT"},
        "syariahSource": syr.get("kep"), "missingFundamentals": missing,
        "thresholds": {"liqHi": LIQ_HI, "liqLo": LIQ_LO, "divMin": strategies.DIV_MIN, "fees": [strategies.FEE_BUY, strategies.FEE_SELL]},
        **res,
        "dq": dq,
        "stocks": rows,
        "etf": etf_info(close),
    }
    slim, det, labels = slim_rows(out["stocks"])
    (DATA / "detail.json").write_text(json.dumps(det, separators=(",", ":")))
    OUT_FILE.write_text(json.dumps({**out, "stocks": slim, "clabels": labels, "hasDetail": True}, separators=(",", ":")))
    import notify_telegram

    liquid = [r["ticker"] for r in rows if r["liq"] == "L"]
    run_cycles(close, {"IHSG": INDEX}, {"ramadan": True, "holidays": set(notify_telegram.HOLIDAYS)},
               liquid, eligible, tick=strategies.tick)
    _ohlc(close, volume, liquid)
    _track(True, (0.0015, 0.0025))
    log(f"Selesai dalam {(time.time() - t0) / 60:.1f} menit -> {OUT_FILE.relative_to(ROOT)}")

    lc = out["liqCount"]
    summary(f"### Berhasil\n- {len(rows)} saham (likuid {lc['L']}, kurang likuid {lc['K']}, tidak likuid {lc['T']}), harga penutupan {day}\n"
            f"- Fundamental baru {fresh}, memakai data sebelumnya {stale}, tanpa fundamental {len(missing)}\n"
            f"- Syariah: {len(syr_codes)} kode dari {syr.get('kep') or '–'}\n"
            f"- Tambahan/IPO: {len(extra)} kode dicek, {len(dropped)} belum ada harganya di Yahoo\n"
            f"- Lama proses: {(time.time() - t0) / 60:.1f} menit")
    cnt = lambda f: sum(1 for r in rows if f(r))
    summary("### Kelengkapan data\n"
            f"- Laba tahunan ≥ 3 tahun: {cnt(lambda r: len(r.get('epsA') or []) >= 3)} · ROIC: {cnt(lambda r: r.get('roic') is not None)} · "
            f"P/FCF: {cnt(lambda r: r.get('pfcf') is not None)} · riwayat dividen: {cnt(lambda r: (r.get('divYears') or 0) > 0)} · "
            f"pertumbuhan dividen 5 thn: {cnt(lambda r: r.get('divGrowth5y') is not None)}")
    st = res.get("stats") or {}
    summary("### Uji mundur 1 tahun (setelah biaya)\n" + "\n".join(
        f"- {strategies.NAMES[m]}: {s.get('n', 0)} transaksi" + (f", {s['win']}% untung, rata-rata {s['avg']:+.2f}%, median {s['med']} hari" if s.get("n") else "")
        for m, s in st.items()))
    sig = {m: {k: sum(1 for r in rows if (r.get('m') or {}).get(m, {}).get('s') == k and r['liq'] == 'L') for k in ('buy', 'hold', 'sell')} for m in strategies.METHODS}
    summary("### Sinyal hari ini (saham likuid)\n" + "\n".join(f"- {strategies.NAMES[m]}: {v['buy']} beli, {v['hold']} tahan, {v['sell']} jual" for m, v in sig.items()))
    for w in WARN:
        summary(f"- Peringatan: {w}")



def intraday():
    """Update siang (istirahat sesi 1): harga sementara saja. Sinyal metode, posisi simulasi,
    dan status area support tidak disimpan; semuanya final pada pembaruan setelah bursa tutup."""
    from zoneinfo import ZoneInfo
    t0 = time.time()
    if not OUT_FILE.exists():
        log("Belum ada data penutupan; update siang dilewati")
        return
    prev = json.loads(OUT_FILE.read_text())
    rows = prev["stocks"]
    codes = [r["ticker"] for r in rows]
    log(f"Update siang: harga {len(codes)} saham ...")
    close, volume = fetch_prices(codes)
    if close is None:
        raise RuntimeError("Harga dari Yahoo gagal diambil")
    last = close.index[-1].strftime("%Y-%m-%d")
    now = datetime.now(ZoneInfo("Asia/Jakarta"))
    if last != now.date().isoformat():
        log(f"Belum ada harga hari ini (data terakhir {last}); kemungkinan bursa libur")
        summary(f"### Update siang dilewati\nHarga terakhir {last}, belum ada perdagangan hari ini.")
        return
    n = 0
    for r in rows:
        c = r["ticker"]
        if c not in close or not close[c].notna().any():
            continue
        t = technicals(close[c])
        r.update({k: v for k, v in t.items() if v is not None})
        r.update(flow(close[c], volume[c] if volume is not None and c in volume else None, close.index[-1]))
        if r.get("price") and r.get("dpsTTM") is not None:
            r["div"] = r["dpsTTM"] / r["price"] * 100
        if r.get("dv") and r.get("price"):
            r["dv"]["y"] = round(r["dv"]["amt"] / r["price"] * 100, 2)
        n += 1
    prev["stocks"] = [clean(r) for r in rows]
    prev["intraday"] = {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "date": last, "wib": now.strftime("%H.%M")}
    OUT_FILE.write_text(json.dumps(prev, separators=(",", ":")))
    import notify_telegram

    liquid = [r["ticker"] for r in rows if r.get("liq") == "L"]
    eligible = [r["ticker"] for r in rows if r.get("liq") in ("L", "K")]
    run_cycles(close, {"IHSG": INDEX}, {"ramadan": True, "holidays": set(notify_telegram.HOLIDAYS)},
               liquid, eligible, tick=strategies.tick, persist=False)
    _ohlc(close, volume, liquid)
    # pesan Telegram: ringkasan siang (sekali, setelah sesi 1) + saham yang baru masuk / hampir sampai area beli
    try:
        nf_ = DATA / "intraday_note.json"
        note = json.loads(nf_.read_text()) if nf_.exists() else {}
        if note.get("date") != last:
            note = {"date": last, "sent": [], "midday": None}
        d = json.loads(OUT_FILE.read_text())
        wd, hm = now.weekday(), now.hour * 60 + now.minute
        parts = []
        if hm >= (11 * 60 + 30 if wd == 4 else 12 * 60) and note.get("midday") != last:
            note["midday"] = last
            m = notify_telegram.midday(d)
            if m:
                parts.append(m)
        L, keys = notify_telegram.near_lines(d, set(note.get("sent") or []))
        if L:
            note["sent"] = (note.get("sent") or []) + keys
            parts.append("\n".join([f"⏱️ <b>Harga sementara {now.strftime('%H.%M')} WIB</b> · area beli", *L,
                                     "<i>Pertimbangkan memasang order limit di harga area beli. Harga tertunda beberapa menit.</i>"]))
        note["msg"] = "\n\n".join(parts) or None
        note["at"] = prev["intraday"]["at"]
        nf_.write_text(json.dumps(note, ensure_ascii=False))
        log(f"Catatan siang: {len(L)} saham area beli baru/hampir sampai, ringkasan siang {'ya' if note['midday'] == last and parts and parts[0].startswith('⏱️ <b>Update') else 'tidak'}")
    except Exception as e:
        log(f"  catatan siang gagal: {e}")
    summary(f"### Update siang berhasil\n- {n} saham, harga sementara {last} pukul {prev['intraday']['wib']} WIB\n- Lama proses: {(time.time() - t0) / 60:.1f} menit")

if __name__ == "__main__":
    try:
        intraday() if os.environ.get("INTRADAY") == "1" else main()
    except Exception as e:
        traceback.print_exc()
        summary(f"### Gagal\n**{type(e).__name__}**: {e}")
        sys.exit(1)
