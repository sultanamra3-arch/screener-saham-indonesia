"""
Tujuh metode versi asli untuk saham BEI: kriteria, aturan masuk, aturan keluar, dan alasannya.

Penyesuaian pasar Indonesia: arah pasar dari IHSG, biaya transaksi (beli 0,15%, jual 0,25%) masuk
uji mundur, harga patokan dibulatkan ke fraksi harga BEI, kriteria khusus bank, dan riwayat laba
Yahoo yang hanya ±4 tahun.

Metode investor (Value, Growth, Quality, Dividen) tidak memakai stop loss, sesuai aslinya;
posisinya dicatat maju sejak hari pertama (data/signals.json) karena butuh riwayat fundamental.
Metode trader (CAN SLIM, Momentum, Swing) diuji mundur hari demi hari dari harga harian.

Kode status: buy = Beli (sinyal baru), hold = Tahan, sell = Jual, wait = Tunggu, na = tidak dinilai.
Kode kriteria: 1 lolos, 0 gagal, None tanpa data, 2 tidak berlaku (tidak dihitung).
"""
from __future__ import annotations

import math
from datetime import date, timedelta

import numpy as np
import pandas as pd

INVESTOR = ["value", "growth", "quality", "dividend"]
TRADER = ["canslim", "momentum", "swing"]
METHODS = INVESTOR + TRADER
NAMES = {"value": "Value", "growth": "Growth", "quality": "Quality", "dividend": "Dividen",
         "canslim": "CAN SLIM", "momentum": "Momentum", "swing": "Swing"}
WINDOW = 252  # uji mundur 1 tahun bursa
MARKET = "^JKSE"
FEE_BUY, FEE_SELL = 0.0015, 0.0025  # perkiraan biaya broker + pajak jual 0,1%
DIV_MIN = 4.0  # yield minimal: di atas bunga deposito, dilengkapi Chowder rule (SBN 10 thn ±7,4% Juli 2026)
SIZE_MIN = 10_000  # market cap minimal (miliar Rp) = Rp10 triliun

# CAN SLIM (O'Neil / Minervini)
CS_STOP, CS_TARGET, CS_LOCK = 0.07, 0.20, 0.10
CS_BASE, CS_MIN_AGE, CS_VOL = 35, 15, 1.4
# Momentum (Jegadeesh & Titman)
MOM_BUY, MOM_KEEP = 90, 80

REASON = {
    "stop": "kena stop loss −7%",
    "be": "turun kembali ke harga beli (stop sudah dinaikkan ke harga beli)",
    "target": "target +20% tercapai",
    "8w": "aturan 8 minggu selesai",
    "sma5": "harga menutup di atas SMA5 (sudah memantul)",
    "rank": "keluar dari 20% teratas peringkat momentum",
    "target50": "target Graham +50% tercapai",
    "2y": "sudah 2 tahun tanpa mencapai target (aturan Graham)",
    "divstop": "dividen dihentikan",
    "peg2": "harga sudah mahal: PEG ≥ 2",
    "slow": "pertumbuhan laba melambat drastis (cerita berubah)",
    "quality": "kualitas bisnis memburuk",
    "expensive": "harga sudah sangat mahal (FCF yield < 1,5%, atau P/B > 4,5 untuk bank)",
    "cut": "dividen dipotong",
    "payout": "payout di atas 100%, dividen tidak berkelanjutan",
}


# ---------------------------------------------------------------- format
def usd(v) -> str:
    """Format rupiah (nama fungsi dipertahankan agar sama dengan versi AS)."""
    if v is None or not isinstance(v, (int, float)) or not math.isfinite(v):
        return "–"
    return "Rp" + f"{v:,.0f}".replace(",", ".")


def tick(p: float) -> float:
    """Fraksi harga BEI (Peraturan II-A 2016)."""
    return 1 if p < 200 else 2 if p < 500 else 5 if p < 2000 else 10 if p < 5000 else 25


def px(v, mode="near"):
    """Bulatkan harga ke fraksi BEI."""
    if not ok(v) or v <= 0:
        return None
    t = tick(v)
    if mode == "down":
        return float(math.floor(v / t) * t)
    if mode == "up":
        return float(math.ceil(v / t) * t)
    return float(round(v / t) * t)


def is_bank(o) -> bool:
    return "bank" in (o.get("industry") or "").lower()


def num(v, d=1) -> str:
    if v is None or not math.isfinite(v):
        return "–"
    return f"{v:,.{d}f}".replace(",", "_").replace(".", ",").replace("_", ".")


def pc(v, d=1, sign=False) -> str:
    if v is None or not math.isfinite(v):
        return "–"
    return ("+" if sign and v > 0 else "") + num(v, d) + "%"


def ok(v) -> bool:
    return isinstance(v, (int, float)) and math.isfinite(v)


def crit(label, text, state):
    return [label, text, state]


def cmp(v, op, t):
    if not ok(v):
        return None
    return 1 if {">": v > t, ">=": v >= t, "<=": v <= t, "<": v < t}[op] else 0


def r2(v):
    return round(float(v), 2) if ok(v) else None


# ---------------------------------------------------------------- indikator harga
def indicators(close: pd.DataFrame, volume: pd.DataFrame | None, stocks: list[str], eligible: list[str] | None = None) -> dict:
    c = close
    ind = {
        "sma5": c.rolling(5).mean(), "sma50": c.rolling(50).mean(),
        "sma150": c.rolling(150).mean(), "sma200": c.rolling(200).mean(),
        "hi252": c.rolling(252, min_periods=200).max(), "lo252": c.rolling(252, min_periods=200).min(),
    }
    d = c.diff()
    au = d.clip(lower=0).ewm(alpha=0.5, adjust=False).mean()
    ad = (-d.clip(upper=0)).ewm(alpha=0.5, adjust=False).mean()
    ind["rsi2"] = (100 - 100 / (1 + au / ad.replace(0, np.nan))).fillna(100.0).where(c.notna())

    # peringkat RS dan momentum hanya di antara saham yang cukup likuid, supaya saham gorengan tidak mendominasi
    cs = c[[t for t in (eligible or stocks) if t in c.columns]]
    score = 0.4 * (cs / cs.shift(63) - 1) + 0.2 * (cs / cs.shift(126) - 1) + 0.2 * (cs / cs.shift(189) - 1) + 0.2 * (cs / cs.shift(252) - 1)
    ind["rs"] = (score.rank(axis=1, pct=True) * 98 + 1).round()
    mom = cs.shift(21) / cs.shift(252) - 1
    ind["mom"] = mom
    ind["momRank"] = (mom.rank(axis=1, pct=True) * 100).round(1)

    if volume is not None:
        v = volume.reindex_like(c)
        ind["avgv50"] = v.rolling(50).mean()
        up = (d > 0)
        upv = v.where(up, 0).rolling(50).sum()
        dnv = v.where(d < 0, 0).rolling(50).sum()
        ind["udv"] = upv / dnv.replace(0, np.nan)
        ind["vol"] = v
    return ind


def market(close: pd.DataFrame, volume: pd.DataFrame | None) -> dict:
    """Arah pasar (huruf M) dari IHSG: di atas SMA50, SMA50 di atas SMA200, distribution days ≤ 5."""
    if MARKET not in close:
        return {"ok": None, "series": None, "text": "Data IHSG tidak tersedia"}
    s = close[MARKET]
    s50, s200 = s.rolling(50).mean(), s.rolling(200).mean()
    dist = pd.Series(0, index=s.index)
    if volume is not None and MARKET in volume:
        v = volume[MARKET].reindex(s.index)
        dd = ((s.pct_change() <= -0.002) & (v > v.shift(1))).astype(int)
        dist = dd.rolling(25).sum().fillna(0)
    okser = (s > s50) & (s50 > s200) & (dist <= 5)
    last = s.index[-1]
    text = (f"IHSG {num(s[last], 0)}, {'di atas' if s[last] > s50[last] else 'di bawah'} SMA50 {num(s50[last], 0)}, "
            f"SMA50 {'di atas' if s50[last] > s200[last] else 'di bawah'} SMA200, {int(dist[last])} distribution days (25 hari)")
    return {"ok": bool(okser[last]), "series": okser, "text": text, "dist": int(dist[last])}


def tt_series(close, ind, t):
    c = close[t]
    s50, s150, s200 = ind["sma50"][t], ind["sma150"][t], ind["sma200"][t]
    rs = ind["rs"][t] if t in ind["rs"] else pd.Series(np.nan, index=c.index)
    conds = [
        ("Harga di atas SMA150 dan SMA200", (c > s150) & (c > s200)),
        ("SMA150 di atas SMA200", s150 > s200),
        ("SMA200 naik minimal 1 bulan", s200 > s200.shift(21)),
        ("SMA50 di atas SMA150 dan SMA200", (s50 > s150) & (s50 > s200)),
        ("Harga di atas SMA50", c > s50),
        ("Minimal 30% di atas 52W low", c >= ind["lo252"][t] * 1.3),
        ("Maksimal 25% di bawah 52W high", c >= ind["hi252"][t] * 0.75),
        ("RS rating minimal 70", rs >= 70),
    ]
    allok = conds[0][1]
    for _, s in conds[1:]:
        allok = allok & s
    return conds, allok


# ---------------------------------------------------------------- fundamental bantu
def eps_hist(o):
    return [v for _, v in (o.get("epsA") or []) if ok(v)]


def eps3avg(o):
    h = eps_hist(o)
    if len(h) >= 3:
        return sum(h[-3:]) / 3, True
    return (o.get("eps"), False) if ok(o.get("eps")) else (None, False)


def dps_now(o):
    """Dividen per saham tahun penuh terakhir (perusahaan Indonesia membagi interim + final)."""
    return o.get("dpsY") if ok(o.get("dpsY")) else None


def growth_rate(o):
    if ok(o.get("epsG")):
        return o["epsG"], f"data {o.get('epsGy', 3)} tahun"
    return None, ""


# ---------------------------------------------------------------- kriteria per metode
def crit_value(o):
    sector = (o.get("sector") or "").lower()
    e3, avg = eps3avg(o)
    h = eps_hist(o)
    dy = o.get("divYears")
    price, pb = o.get("price"), o.get("pb")
    pe3 = price / e3 if ok(price) and ok(e3) and e3 > 0 else None
    out = [crit("Ukuran: market cap ≥ Rp10 triliun", "Rp" + num(o["mcap"] / 1000, 1) + " triliun" if ok(o.get("mcap")) else "–",
                cmp(o.get("mcap"), ">=", SIZE_MIN))]
    if "financ" in sector or is_bank(o):
        out.append(crit("Neraca: current ratio ≥ 2", "tidak berlaku untuk bank/keuangan", 2))
    elif "utilit" in sector:
        out.append(crit("Neraca utilitas: utang ≤ 2× ekuitas", num(o.get("de"), 2), cmp(o.get("de"), "<=", 2)))
    else:
        out.append(crit("Neraca: current ratio ≥ 2", num(o.get("cr"), 2), cmp(o.get("cr"), ">=", 2)))
    if len(h) >= 3:
        out.append(crit(f"Laba positif tiap tahun ({len(h)} tahun data; Graham: 10 tahun)", "semua positif" if min(h) > 0 else "ada tahun rugi", 1 if min(h) > 0 else 0))
    else:
        out.append(crit("Laba positif tiap tahun (≥3 tahun data)", "riwayat tidak tersedia", None))
    if ok(dy):
        out.append(crit("Dividen tanpa putus 20 tahun", f"{int(dy)} tahun berturut-turut", 1 if dy >= 20 else 0))
    else:
        out.append(crit("Dividen tanpa putus 20 tahun", "tidak membagi dividen" if o.get("divYears") == 0 else "riwayat tidak tersedia", 0 if o.get("divYears") == 0 else None))
    if len(h) >= 4 and (h[0] + h[1]) > 0:
        g = ((h[-1] + h[-2]) / (h[0] + h[1]) - 1) * 100
        out.append(crit(f"Laba naik ({len(h)} tahun data; 2 tahun terakhir vs 2 tahun pertama)", pc(g, 0, True), 1 if g > 0 else 0))
    else:
        out.append(crit("Laba naik dalam data yang tersedia", "riwayat tidak tersedia", None))
    lbl = "P/E (laba rata-rata 3 tahun) ≤ 15" if avg else "P/E (laba 12 bulan) ≤ 15"
    out.append(crit(lbl, num(pe3), cmp(pe3, "<=", 15) if pe3 is not None else (0 if ok(e3) and e3 <= 0 else None)))
    prod = pe3 * pb if pe3 is not None and ok(pb) and pb > 0 else None
    out.append(crit("P/E × P/B ≤ 22,5", num(prod), cmp(prod, "<=", 22.5)))
    graham = math.sqrt(22.5 * e3 * o["bvps"]) if ok(e3) and e3 > 0 and ok(o.get("bvps")) and o["bvps"] > 0 else None
    return out, {"graham": graham, "pe3": pe3}


def crit_growth(o):
    g, per = growth_rate(o)
    y = o.get("div") if ok(o.get("div")) else 0.0
    pe = o.get("pe")
    peg = pe / (g + y) if ok(pe) and pe > 0 and ok(g) and (g + y) > 0 else None
    out = [
        crit(f"Laba tumbuh 20–50% per tahun ({per or 'data'})", pc(g, 1, True), (1 if 20 <= g <= 50 else 0) if ok(g) else None),
        crit("Pendapatan tumbuh ≥ 10% per tahun", pc(o.get("salesG"), 1, True), cmp(o.get("salesG"), ">=", 10)),
        crit("P/E positif", num(pe), cmp(pe, ">", 0)),
        crit("PEG plus dividen ≤ 1: P/E ÷ (pertumbuhan + yield)", num(peg, 2), cmp(peg, "<=", 1)),
        crit("Neraca kuat: utang ≤ 0,5× ekuitas", "tidak berlaku untuk bank" if is_bank(o) else num(o.get("de"), 2),
             2 if is_bank(o) else cmp(o.get("de"), "<=", 0.5)),
        crit("Laba tahun terakhir masih tumbuh (≥ 10% atau ≥ separuh laju rata-rata)", pc(o.get("epsTTM"), 1, True),
             (1 if o["epsTTM"] >= 0 and (o["epsTTM"] >= 10 or (ok(g) and o["epsTTM"] >= g / 2)) else 0) if ok(o.get("epsTTM")) else None),
    ]
    eps = o.get("eps")
    fair = eps * (g + y) if ok(eps) and eps > 0 and ok(g) and (g + y) > 0 else None
    return out, {"fair": fair, "peg": peg, "g": g}


def quality_vals(o):
    pe, pfcf = o.get("pe"), o.get("pfcf")
    conv = pe / pfcf * 100 if ok(pe) and pe > 0 and ok(pfcf) and pfcf > 0 else None
    fy = 100 / pfcf if ok(pfcf) and pfcf > 0 else None
    fcfps = o["price"] / pfcf if ok(o.get("price")) and ok(pfcf) and pfcf > 0 else None
    return conv, fy, fcfps


def crit_quality(o):
    conv, fy, fcfps = quality_vals(o)
    if is_bank(o):
        out = [
            crit("ROE ≥ 15% (bank memakai ROE, bukan ROIC)", pc(o.get("roe")), cmp(o.get("roe"), ">=", 15)),
            crit("Margin kotor ≥ 40%", "tidak berlaku untuk bank", 2),
            crit("Konversi kas ≥ 80%", "tidak berlaku untuk bank", 2),
            crit("Utang ≤ 1× ekuitas", "tidak berlaku untuk bank", 2),
            crit("Pendapatan tumbuh ≥ 5% per tahun", pc(o.get("salesG"), 1, True), cmp(o.get("salesG"), ">=", 5)),
            crit("Tidak kemahalan: P/B ≤ 3", num(o.get("pb"), 2), cmp(o.get("pb"), "<=", 3)),
        ]
        return out, {"conv": None, "fy": None, "fcfps": None, "bank": True}
    out = [
        crit("ROIC ≥ 15%", pc(o.get("roic")), cmp(o.get("roic"), ">=", 15)),
        crit("Margin kotor ≥ 40%", pc(o.get("gm")), cmp(o.get("gm"), ">=", 40)),
        crit("Konversi kas ≥ 80% (arus kas bebas ÷ laba)", pc(conv, 0), cmp(conv, ">=", 80)),
        crit("Utang ≤ 1× ekuitas", num(o.get("de"), 2), cmp(o.get("de"), "<=", 1)),
        crit("Pendapatan tumbuh ≥ 5% per tahun", pc(o.get("salesG"), 1, True), cmp(o.get("salesG"), ">=", 5)),
        crit("Tidak kemahalan: FCF yield ≥ 2,5%", pc(fy, 2), cmp(fy, ">=", 2.5)),
    ]
    return out, {"conv": conv, "fy": fy, "fcfps": fcfps}


def crit_dividend(o):
    y, g = o.get("div"), o.get("divGrowth5y")
    chow = y + g if ok(y) and ok(g) else None
    need = 12 if ok(y) and y >= 3 else 15
    p = o.get("payout")
    out = [
        crit("Dividend yield ≥ 4% (di atas bunga deposito)", pc(y, 2), cmp(y, ">=", DIV_MIN)),
        crit("Dividen naik dalam 5 tahun", pc(g, 1, True) + " per tahun" if ok(g) else "–", cmp(g, ">", 0)),
        crit(f"Chowder: yield + pertumbuhan dividen ≥ {need}", num(chow), cmp(chow, ">=", need)),
        crit("Payout ratio 0–70%", pc(p, 0), (1 if 0 < p <= 70 else 0) if ok(p) else None),
        crit("Laba tidak menyusut (data ±4 tahun)", pc(o.get("epsG"), 1, True), cmp(o.get("epsG"), ">=", 0)),
    ]
    dps = dps_now(o)
    return out, {"dps": dps, "buy": dps / (DIV_MIN / 100) if ok(dps) and dps > 0 else None}


def a_criteria(o):
    h = eps_hist(o)
    if len(h) >= 4 and all(x > 0 for x in h[-4:-1]):
        gs = [(h[i] / h[i - 1] - 1) * 100 for i in range(len(h) - 3, len(h))]
        return crit("A: laba tahunan naik ≥ 25% tiap tahun (3 tahun)", " · ".join(pc(x, 0, True) for x in gs), 1 if min(gs) >= 25 else 0)
    return crit("A: laba tahunan naik ≥ 25% tiap tahun (3 tahun)", "riwayat tidak cukup", None)


def crit_canslim(o, now, mkt):
    out = [
        crit("C: laba kuartal naik ≥ 25% (vs tahun lalu)", pc(o.get("epsQ"), 1, True), cmp(o.get("epsQ"), ">=", 25)),
        a_criteria(o),
        crit("A: ROE ≥ 17%", pc(o.get("roe")), cmp(o.get("roe"), ">=", 17)),
        crit("N: dekat titik tertinggi (≤ 15% di bawah 52W high)", pc(o.get("hi52"), 1), cmp(o.get("hi52"), ">=", -15)),
        crit("S: volume akumulasi (rasio volume naik/turun 50 hari ≥ 1)", num(now.get("udv"), 2), cmp(now.get("udv"), ">=", 1)),
        crit("L: pemimpin pasar (RS rating ≥ 80)", num(now.get("rs"), 0), cmp(now.get("rs"), ">=", 80)),
        crit("I: dukungan institusi", "data tidak tersedia di paket gratis", 2),
        crit("M: arah pasar naik", mkt.get("text", "–"), None if mkt.get("ok") is None else int(bool(mkt["ok"]))),
    ]
    return out


def crit_momentum(o, now):
    return [
        crit("Peringkat momentum 12-1 bulan di 10% teratas (≥ 90)", num(now.get("momRank"), 0), cmp(now.get("momRank"), ">=", MOM_BUY)),
        crit("Kinerja 12 bulan tanpa bulan terakhir", pc(now["mom"] * 100 if ok(now.get("mom")) else None, 1, True), 2),
    ]


def crit_swing(o, now):
    return [
        crit("Tren besar naik: harga di atas SMA200", pc(o.get("sma200"), 1, True) + " dari SMA200" if ok(o.get("sma200")) else "–", cmp(o.get("sma200"), ">", 0)),
        crit("RSI(2) di bawah 10 (koreksi tajam jangka pendek)", num(now.get("rsi2"), 1), cmp(now.get("rsi2"), "<", 10)),
    ]


def count(cs):
    use = [c for c in cs if c[2] != 2]
    return sum(1 for c in use if c[2] == 1), len(use)


def failed(cs, k=2):
    bad = [c[0] for c in cs if c[2] in (0, None)]
    return bad[:k]


# ---------------------------------------------------------------- uji mundur trader
def net_ret(bp, sp):
    """Hasil bersih setelah biaya beli dan jual."""
    return round((sp * (1 - FEE_SELL) / (bp * (1 + FEE_BUY)) - 1) * 100, 2)


def _trade(b, bp, s, sp, r, dates_b, dates_s):
    return {"b": b, "bp": r2(bp), "s": s, "sp": r2(sp), "r": r, "ret": net_ret(bp, sp),
            "d": (date.fromisoformat(s) - date.fromisoformat(b)).days}


def bt_canslim(close, ind, mkt_series, t, fund_ok):
    """Breakout dari base ≥ 3 minggu (koreksi 5–33%) dengan volume ≥ 1,4× rata-rata, trend template
    Minervini terpenuhi, dan pasar naik. Keluar: stop −7% (naik ke harga beli setelah +10%), target +20%,
    kecuali naik +20% dalam 3 minggu → tahan sampai 8 minggu (aturan O'Neil)."""
    c = close[t].to_numpy(dtype=float)
    idx = close.index
    n = len(c)
    _, tt = tt_series(close, ind, t)
    tt = tt.to_numpy()
    mk = mkt_series.reindex(idx).fillna(False).to_numpy() if mkt_series is not None else np.ones(n, bool)
    vol = ind["vol"][t].to_numpy(dtype=float) if "vol" in ind and t in ind["vol"] else None
    av = ind["avgv50"][t].to_numpy(dtype=float) if vol is not None else None
    trades, pos = [], None
    pivot_now = None
    start = max(CS_BASE + 1, n - WINDOW)
    for i in range(start, n):
        p = c[i]
        if not math.isfinite(p):
            continue
        day = idx[i].strftime("%Y-%m-%d")
        if pos is None:
            if not fund_ok:
                continue
            w = c[i - CS_BASE:i]
            if np.isnan(w).any():
                continue
            j = int(np.argmax(w))
            H = w[j]
            age = CS_BASE - j
            low = w[j:].min()
            depth = (H - low) / H
            if i == n - 1:
                pivot_now = {"H": H, "age": age, "depth": depth}
            volok = vol is not None and math.isfinite(vol[i]) and math.isfinite(av[i - 1]) and vol[i] >= CS_VOL * av[i - 1]
            if (tt[i] and mk[i] and age >= CS_MIN_AGE and 0.05 <= depth <= 0.33
                    and H < p <= H * 1.05 and volok):
                pos = {"b": day, "bp": p, "i": i, "lock": False, "hold8": None, "pivot": H,
                       "vr": vol[i] / av[i - 1]}
        else:
            bp = pos["bp"]
            if p >= bp * (1 + CS_LOCK):
                pos["lock"] = True
            stop = bp if pos["lock"] else bp * (1 - CS_STOP)
            r = None
            if pos["hold8"] is not None:
                if i >= pos["hold8"]:
                    r = "8w"
                elif p <= stop:
                    r = "be" if pos["lock"] else "stop"
            elif p <= stop:
                r = "be" if pos["lock"] else "stop"
            elif p >= bp * (1 + CS_TARGET):
                if i - pos["i"] <= 15:
                    pos["hold8"] = pos["i"] + 40
                else:
                    r = "target"
            if r:
                trades.append(_trade(pos["b"], bp, day, p, r, None, None))
                pos = None
    return trades, pos, pivot_now


def bt_swing(close, ind, t):
    """Connors RSI(2): beli saat harga di atas SMA200 dan RSI(2) < 10; jual saat menutup di atas SMA5."""
    c = close[t].to_numpy(dtype=float)
    s200 = ind["sma200"][t].to_numpy(dtype=float)
    s5 = ind["sma5"][t].to_numpy(dtype=float)
    r2_ = ind["rsi2"][t].to_numpy(dtype=float)
    idx = close.index
    n = len(c)
    trades, pos = [], None
    for i in range(max(1, n - WINDOW), n):
        p = c[i]
        if not math.isfinite(p) or not math.isfinite(s200[i]):
            continue
        day = idx[i].strftime("%Y-%m-%d")
        if pos is None:
            if p > s200[i] and r2_[i] < 10:
                pos = {"b": day, "bp": p, "i": i}
        elif p > s5[i]:
            trades.append(_trade(pos["b"], pos["bp"], day, p, "sma5", None, None))
            pos = None
    return trades, pos


def rebalance_days(idx):
    win = idx[-WINDOW:]
    out, seen = [], set()
    for i, d in enumerate(win):
        k = (d.year, d.month)
        if k not in seen:
            seen.add(k)
            out.append(len(idx) - WINDOW + i)
    return out


def bt_momentum(close, ind, t, rb):
    """Jegadeesh & Titman: tiap awal bulan, beli bila peringkat 12-1 ≥ 90; jual bila turun di bawah 80."""
    c = close[t].to_numpy(dtype=float)
    rk = ind["momRank"][t].to_numpy(dtype=float) if t in ind["momRank"] else np.full(len(c), np.nan)
    idx = close.index
    trades, pos = [], None
    for i in rb:
        p = c[i]
        if not math.isfinite(p) or not math.isfinite(rk[i]):
            continue
        day = idx[i].strftime("%Y-%m-%d")
        if pos is None and rk[i] >= MOM_BUY:
            pos = {"b": day, "bp": p, "i": i, "rank": rk[i]}
        elif pos is not None and rk[i] < MOM_KEEP:
            trades.append(_trade(pos["b"], pos["bp"], day, p, "rank", None, None))
            pos = None
    return trades, pos


def legacy_bt(close, ind, t):
    """Aturan lama (sebelum diganti) untuk perbandingan: SMA20/52W high, stop −8%, target +25%, tren patah SMA50."""
    c = close[t]
    s20, s50, s200 = c.rolling(20).mean(), ind["sma50"][t], ind["sma200"][t]
    hi = c.rolling(252, min_periods=120).max()
    cv, a20, a50, a200, h = (x.to_numpy(dtype=float) for x in (c, s20, s50, s200, hi))
    idx = close.index
    trades, pos = [], None
    for i in range(len(cv) - WINDOW, len(cv)):
        p = cv[i]
        if any(not math.isfinite(x) for x in (p, a20[i], a50[i], a200[i])):
            continue
        day = idx[i].strftime("%Y-%m-%d")
        if pos is None:
            up = p > a200[i] and a50[i] > a200[i] and p >= a50[i]
            brk = math.isfinite(h[i]) and p >= h[i] * 0.98
            e = h[i] if brk else a20[i]
            if up and e * 0.92 <= p <= e * 1.03:
                pos = {"b": day, "bp": p}
        else:
            r = "stop" if p <= pos["bp"] * 0.92 else "target" if p >= pos["bp"] * 1.25 else "trend" if p < a50[i] else None
            if r:
                trades.append(_trade(pos["b"], pos["bp"], day, p, r, None, None))
                pos = None
    return trades


def stats(trades):
    closed = [t for t in trades if t.get("s")]
    if not closed:
        return {"n": 0, "win": None, "avg": None, "med": None}
    ds = sorted(t["d"] for t in closed)
    return {"n": len(closed), "win": round(sum(1 for t in closed if t["ret"] > 0) / len(closed) * 100, 1),
            "avg": round(sum(t["ret"] for t in closed) / len(closed), 2), "med": ds[len(ds) // 2]}


# ---------------------------------------------------------------- status trader
def trader_state(mid, trades, pos, day, last_px, extra):
    """Ubah hasil uji mundur menjadi status hari ini beserta alasan dan harga patokan."""
    res = {"s": "wait", "lv": {}}
    recent_days = 5
    if pos is not None:
        bp = pos["bp"]
        res.update({"b": pos["b"], "bp": r2(bp), "ret": net_ret(bp, last_px)})
        res["s"] = "buy" if pos["b"] == day else "hold"
        if mid == "canslim":
            lock = last_px >= bp * (1 + CS_LOCK) or pos.get("lock")
            res["lv"] = {"buy": px(bp), "stop": px(bp if lock else bp * (1 - CS_STOP), "down"), "target": px(bp * (1 + CS_TARGET), "down")}
            res["lock"] = bool(lock)
            res["hold8"] = pos.get("hold8") is not None
        elif mid == "swing":
            res["lv"] = {"buy": px(bp), "exit": px(extra.get("sma5px"), "up")}
        elif mid == "momentum":
            res["lv"] = {"buy": px(bp)}
        return res
    if trades:
        lt = trades[-1]
        if lt["s"] and (date.fromisoformat(day) - date.fromisoformat(lt["s"])).days <= recent_days:
            res.update({"s": "sell", "sd": lt["s"], "sp": lt["sp"], "b": lt["b"], "bp": lt["bp"], "ret": lt["ret"], "why": lt["r"]})
    return res


def reason_trader(mid, st, o, now, cs, extra, mkt):
    s = st["s"]
    if mid == "canslim":
        if s in ("buy", "hold"):
            lv = st["lv"]
            base = (f"Breakout di atas pivot {usd(extra.get('pivot'))} dengan volume {num(extra.get('vr'), 1)}× rata-rata, "
                    f"laba kuartal {pc(o.get('epsQ'), 0, True)}, RS rating {num(now.get('rs'), 0)}, pasar naik.") if s == "buy" else \
                   (f"Dibeli {tgl(st['b'])} di {usd(st['bp'])}, sekarang {pc(st['ret'], 1, True)}. ")
            if s == "hold":
                if st.get("hold8"):
                    base += "Naik +20% dalam 3 minggu: tahan sampai 8 minggu (aturan O'Neil)."
                elif st.get("lock"):
                    base += f"Sudah pernah +10%: stop dinaikkan ke harga beli {usd(lv['stop'])}."
                else:
                    base += f"Belum kena stop {usd(lv['stop'])} atau target {usd(lv['target'])}."
            short = f"breakout volume {num(extra.get('vr'), 1)}×, laba kuartal {pc(o.get('epsQ'), 0, True)}" if s == "buy" else "posisi berjalan"
            return base, short
    if mid == "swing":
        if s == "buy":
            return (f"Harga di atas SMA200 (tren naik) dan RSI(2) {num(now.get('rsi2'), 1)} di bawah 10: koreksi tajam yang biasanya memantul. "
                    f"Jual saat harga menutup di atas SMA5 (sekarang {usd(extra.get('sma5px'))})."), f"RSI(2) {num(now.get('rsi2'), 1)}, tren naik"
        if s == "hold":
            return (f"Dibeli {tgl(st['b'])} di {usd(st['bp'])}, sekarang {pc(st['ret'], 1, True)}. "
                    f"Jual saat harga menutup di atas SMA5 ({usd(extra.get('sma5px'))})."), "menunggu pantulan"
    if mid == "momentum":
        if s == "buy":
            return (f"Peringkat momentum 12-1 bulan {num(now.get('momRank'), 0)} (10% teratas), naik {pc(now['mom'] * 100 if ok(now.get('mom')) else None, 0, True)} "
                    f"dalam 12 bulan tanpa bulan terakhir. Dicek lagi awal bulan depan."), f"peringkat {num(now.get('momRank'), 0)}, 10% teratas"
        if s == "hold":
            return (f"Dibeli {tgl(st['b'])} di {usd(st['bp'])}, sekarang {pc(st['ret'], 1, True)}. Peringkat saat ini {num(now.get('momRank'), 0)}; "
                    f"tahan selama masih ≥ {MOM_KEEP} di pengecekan awal bulan."), "masih di peringkat atas"
    if s == "sell":
        r = REASON.get(st["why"], st["why"])
        return (f"Jual {tgl(st['sd'])} di {usd(st['sp'])}: {r}. Dibeli {tgl(st['b'])} di {usd(st['bp'])}, hasil {pc(st['ret'], 1, True)}.",
                f"{r} ({pc(st['ret'], 1, True)})")
    # tunggu
    if mid == "canslim":
        bad = failed(cs, 2)
        pv = extra.get("pivotNow")
        if not extra.get("fund"):
            return "Syarat fundamental belum terpenuhi: " + "; ".join(failed(cs[:3], 3) or ["–"]) + ".", "fundamental belum memenuhi"
        if pv and 0.05 <= pv["depth"] <= 0.33 and pv["age"] >= CS_MIN_AGE:
            return (f"Fundamental memenuhi. Tunggu breakout di atas pivot {usd(pv['H'])} (maks. {usd(pv['H'] * 1.05)}) "
                    f"dengan volume ≥ 1,4× rata-rata" + ("" if mkt.get("ok") else ", dan pasar kembali naik") + "."), "tunggu breakout"
        return "Belum membentuk base yang sah atau trend template belum terpenuhi" + (": " + "; ".join(bad) if bad else "") + ".", "belum ada base"
    if mid == "swing":
        if not ok(o.get("sma200")) or o["sma200"] <= 0:
            return "Harga di bawah SMA200: Connors hanya membeli saat tren besar naik.", "di bawah SMA200"
        return f"Tren naik, tapi RSI(2) {num(now.get('rsi2'), 1)} belum di bawah 10. Tunggu koreksi tajam.", "tunggu koreksi"
    if mid == "momentum":
        return (f"Peringkat momentum {num(now.get('momRank'), 0)}; perlu ≥ {MOM_BUY} pada pengecekan awal bulan."), "peringkat belum masuk 10% teratas"
    return "", ""


def tgl(d):
    if not d:
        return "–"
    bl = ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des"]
    y, m, dd = d.split("-")
    return f"{int(dd)} {bl[int(m) - 1]} {y}"


# ---------------------------------------------------------------- posisi investor (dicatat maju)
def investor_exit(mid, o, p, extra, day):
    price = o.get("price")
    if not ok(price):
        return None
    if mid == "value":
        if price >= p["bp"] * 1.5:
            return "target50"
        if (date.fromisoformat(day) - date.fromisoformat(p["b"])).days >= 730:
            return "2y"
        d = dps_now(o)
        if (p.get("dps") or 0) > 0 and ok(d) and d == 0:
            return "divstop"
    elif mid == "growth":
        fair = extra.get("fair")
        if ok(fair) and fair > 0 and price >= 2 * fair:
            return "peg2"
        g, et = extra.get("g"), o.get("epsTTM")
        if ok(et) and (et < 0 or (ok(g) and et < g / 2 and et < 10)):
            return "slow"
    elif mid == "quality" and is_bank(o):
        if ok(o.get("roe")) and o["roe"] < 12:
            return "quality"
        if ok(o.get("pb")) and o["pb"] > 4.5:
            return "expensive"
    elif mid == "quality":
        conv, fy, _ = quality_vals(o)
        if (ok(o.get("roic")) and o["roic"] < 12) or (ok(o.get("gm")) and o["gm"] < 35) or (ok(conv) and conv < 60):
            return "quality"
        if ok(fy) and fy < 1.5:
            return "expensive"
    elif mid == "dividend":
        d = dps_now(o)
        ref = p.get("dps") or 0
        if ref > 0 and ok(d) and d < ref * 0.9:
            return "cut"
        if ok(o.get("payout")) and o["payout"] > 100:
            return "payout"
    return None


def investor_levels(mid, o, extra, p=None):
    if mid == "value":
        lv = {"buy": px(extra.get("graham"), "down")}
        if p:
            lv["target"] = px(p["bp"] * 1.5, "down")
            lv["until"] = (date.fromisoformat(p["b"]) + timedelta(days=730)).isoformat()
        return lv
    if mid == "growth":
        f = extra.get("fair")
        return {"buy": px(f, "down"), "target": px(2 * f, "down") if ok(f) else None}
    if mid == "quality" and is_bank(o):
        bv = o.get("bvps")
        return {"buy": px(bv * 3, "down") if ok(bv) and bv > 0 else None, "sell": px(bv * 4.5, "up") if ok(bv) and bv > 0 else None}
    if mid == "quality":
        fc = extra.get("fcfps")
        return {"buy": px(fc / 0.025, "down") if ok(fc) else None, "sell": px(fc / 0.015, "up") if ok(fc) else None}
    if mid == "dividend":
        return {"buy": px(extra.get("buy"), "down")}
    return {}


def reason_investor(mid, st, o, cs, extra):
    s = st["s"]
    price = o.get("price")
    if s == "sell":
        r = REASON.get(st["why"], st["why"])
        return (f"Jual {tgl(st['sd'])} di {usd(st['sp'])}: {r}. Dibeli {tgl(st['b'])} di {usd(st['bp'])}, hasil {pc(st['ret'], 1, True)}.",
                f"{r} ({pc(st['ret'], 1, True)})")
    if s in ("buy", "hold"):
        head = "Semua kriteria terpenuhi. " if s == "buy" else f"Dibeli {tgl(st['b'])} di {usd(st['bp'])}, sekarang {pc(st['ret'], 1, True)}. "
        if mid == "value":
            txt = (f"P/E rata-rata 3 tahun {num(extra.get('pe3'))}, harga di bawah angka Graham {usd(extra.get('graham'))}, laba dan dividen konsisten. "
                   if s == "buy" else "") + f"Jual di +50% ({usd(st['lv'].get('target'))}) atau paling lambat {tgl(st['lv'].get('until'))}."
            short = f"P/E 3 thn {num(extra.get('pe3'))}, di bawah angka Graham"
        elif mid == "growth":
            txt = (f"Laba tumbuh {pc(extra.get('g'), 0)} per tahun dengan PEG {num(extra.get('peg'), 2)}, neraca kuat. " if s == "buy" else "") + \
                  f"Jual bila PEG mencapai 2 (sekitar {usd(st['lv'].get('target'))}) atau pertumbuhan melambat drastis."
            short = f"laba +{num(extra.get('g'), 0)}%/thn, PEG {num(extra.get('peg'), 2)}"
        elif mid == "quality" and is_bank(o):
            txt = (f"Bank dengan ROE {pc(o.get('roe'), 0)}, pendapatan tumbuh {pc(o.get('salesG'), 0)} per tahun, P/B {num(o.get('pb'), 2)}. "
                   "Terry Smith: tahan bisnis bagus selama kualitasnya terjaga; jual bila ROE < 12% atau P/B > 4,5.")
            short = f"bank, ROE {pc(o.get('roe'), 0)}, P/B {num(o.get('pb'), 1)}"
        elif mid == "quality":
            conv, fy, _ = quality_vals(o)
            txt = (f"ROIC {pc(o.get('roic'), 0)}, margin kotor {pc(o.get('gm'), 0)}, konversi kas {pc(conv, 0)}, FCF yield {pc(fy, 1)}. "
                   "Terry Smith: tahan bisnis bagus selama kualitasnya terjaga; tidak ada stop loss atau target.")
            short = f"ROIC {pc(o.get('roic'), 0)}, margin {pc(o.get('gm'), 0)}"
        else:
            txt = (f"Yield {pc(o.get('div'), 2)}, dividen tumbuh {pc(o.get('divGrowth5y'), 1)} per tahun, payout {pc(o.get('payout'), 0)}. "
                   "Tahan selama dividen tidak dipotong; tidak ada stop loss atau target harga.")
            short = f"yield {pc(o.get('div'), 1)}, dividen naik {pc(o.get('divGrowth5y'), 0)}/thn"
        return head + txt, short
    bad = failed(cs, 2)
    if not bad:
        return "Semua kriteria terpenuhi, menunggu pencatatan berikutnya.", "–"
    return "Belum memenuhi: " + "; ".join(bad) + ".", "belum memenuhi kriteria"


# ---------------------------------------------------------------- jalankan semua
def run(rows: list[dict], close: pd.DataFrame | None, volume: pd.DataFrame | None, day: str, state: dict,
        eligible: list[str] | None = None) -> dict:
    stocks = [o["ticker"] for o in rows]
    ind = indicators(close, volume, stocks, eligible) if close is not None else None
    mkt = market(close, volume) if close is not None else {"ok": None, "series": None, "text": "Data harga tidak tersedia"}
    rb = rebalance_days(close.index) if close is not None else []
    st_pos = state.setdefault("pos", {m: {} for m in INVESTOR})
    for m in INVESTOR:
        st_pos.setdefault(m, {})
    closed_log = state.setdefault("closed", [])
    first_day = not state.get("started")
    if first_day:
        state["started"] = day
    allt = {m: [] for m in TRADER}

    for o in rows:
        t = o["ticker"]
        now, extra_t = {}, {}
        has_px = close is not None and t in close and close[t].notna().sum() > 260
        if has_px:
            last = close.index[-1]
            for k in ("rs", "momRank", "mom", "rsi2", "udv"):
                if k in ind and t in ind[k]:
                    v = ind[k][t].iloc[-1]
                    now[k] = float(v) if pd.notna(v) else None
            extra_t["sma5px"] = float(ind["sma5"][t].iloc[-1]) if pd.notna(ind["sma5"][t].iloc[-1]) else None
            conds, _ = tt_series(close, ind, t)
            o["tt"] = [[lbl, bool(s.iloc[-1]) if pd.notna(s.iloc[-1]) else None] for lbl, s in conds]
        o["rs"] = r2(now.get("rs"))
        o["momRank"] = r2(now.get("momRank"))
        o["rsi2"] = r2(now.get("rsi2"))
        o["m"] = {}

        # ---- investor
        for mid, fn in (("value", crit_value), ("growth", crit_growth), ("quality", crit_quality), ("dividend", crit_dividend)):
            cs, extra = fn(o)
            k, n = count(cs)
            passed = k == n and n > 0
            pos = st_pos[mid].get(t)
            st = {"s": "wait", "lv": investor_levels(mid, o, extra)}
            price = o.get("price")
            if pos and ok(price):
                why = investor_exit(mid, o, pos, extra, day)
                if why and pos["b"] != day:
                    ret = net_ret(pos["bp"], price)
                    rec = {"m": mid, "t": t, "b": pos["b"], "bp": pos["bp"], "s": day, "sp": r2(price), "r": why, "ret": ret}
                    closed_log.append(rec)
                    del st_pos[mid][t]
                    st.update({"s": "sell", "sd": day, "sp": r2(price), "b": pos["b"], "bp": pos["bp"], "ret": ret, "why": why})
                else:
                    if mid == "dividend":
                        d = dps_now(o)
                        if ok(d) and d > (pos.get("dps") or 0):
                            pos["dps"] = d
                    st.update({"s": "buy" if pos["b"] == day else "hold", "b": pos["b"], "bp": pos["bp"],
                               "ret": net_ret(pos["bp"], price), "lv": investor_levels(mid, o, extra, pos)})
                    if pos.get("first"):
                        st["first"] = True
            elif passed and ok(price) and not any(c["m"] == mid and c["t"] == t and c["s"] == day for c in closed_log[-400:]):
                pos = {"b": day, "bp": r2(price), "dps": r2(dps_now(o))}
                if first_day:
                    pos["first"] = True
                st_pos[mid][t] = pos
                st.update({"s": "buy", "b": day, "bp": pos["bp"], "ret": 0.0, "lv": investor_levels(mid, o, extra, pos)})
                if first_day:
                    st["first"] = True
            else:
                recent = [c for c in closed_log if c["m"] == mid and c["t"] == t]
                if recent and (date.fromisoformat(day) - date.fromisoformat(recent[-1]["s"])).days <= 5:
                    lc = recent[-1]
                    st.update({"s": "sell", "sd": lc["s"], "sp": lc["sp"], "b": lc["b"], "bp": lc["bp"], "ret": lc["ret"], "why": lc["r"]})
            if not ok(price):
                st["s"] = "na"
            st["r"], st["rs"] = reason_investor(mid, st, o, cs, extra) if st["s"] != "na" else ("Harga tidak tersedia.", "–")
            st.update({"c": cs, "k": k, "n": n, "p": passed})
            o["m"][mid] = st

        # ---- trader
        fund_ok = False
        cs_cs = crit_canslim(o, now, mkt)
        fund_ok = all(c[2] == 1 for c in cs_cs[:3])
        for mid in TRADER:
            if mid == "canslim":
                cs = cs_cs
            elif mid == "momentum":
                cs = crit_momentum(o, now)
            else:
                cs = crit_swing(o, now)
            k, n = count(cs)
            if not has_px:
                o["m"][mid] = {"s": "na", "r": "Data harga harian tidak tersedia.", "rs": "–", "c": cs, "k": k, "n": n, "p": False, "lv": {}}
                continue
            lastpx = float(close[t].dropna().iloc[-1])
            extra = dict(extra_t)
            if mid == "canslim":
                trades, pos, pv = bt_canslim(close, ind, mkt.get("series"), t, fund_ok)
                extra.update({"fund": fund_ok, "pivotNow": pv})
                if pos:
                    extra.update({"pivot": pos["pivot"], "vr": pos["vr"]})
                    pos = dict(pos, hold8=pos.get("hold8"))
            elif mid == "swing":
                trades, pos = bt_swing(close, ind, t)
            else:
                trades, pos = bt_momentum(close, ind, t, rb)
            st = trader_state(mid, trades, pos, day, lastpx, extra)
            st["r"], st["rs"] = reason_trader(mid, st, o, now, cs, extra, mkt)
            st.update({"c": cs, "k": k, "n": n, "p": k == n and n > 0})
            hist = [dict(x) for x in trades[-6:]]
            if pos:
                hist.append({"b": pos["b"], "bp": r2(pos["bp"]), "s": None, "ret": net_ret(pos["bp"], lastpx)})
            st["h"] = hist
            o["m"][mid] = st
            allt[mid].extend(trades)

    # posisi investor yang sahamnya sudah keluar dari indeks
    alive = set(stocks)
    for m in INVESTOR:
        for t in [t for t in st_pos[m] if t not in alive]:
            del st_pos[m][t]
    state["closed"] = closed_log[-800:]
    state["lastPriceDate"] = day

    next_rb = None
    if close is not None:
        last = close.index[-1]
        ny, nm = (last.year + 1, 1) if last.month == 12 else (last.year, last.month + 1)
        next_rb = f"{ny}-{nm:02d}-01"
    return {
        "market": {k: v for k, v in mkt.items() if k != "series"},
        "stats": {m: stats(allt[m]) for m in TRADER},
        "nextRebalance": next_rb,
        "started": state["started"],
        "firstDay": first_day,
    }
