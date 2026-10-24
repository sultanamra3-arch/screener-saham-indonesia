"""
Siklus & Fibonacci: analisis waktu dan harga dari teknik yang terbuka untuk umum, lengkap dengan
uji ketepatan terhadap tanggal acak supaya terlihat unsur mana yang benar-benar berguna.

Unsur:
  - Titik balik objektif (ZigZag berbasis volatilitas)
  - Zona konfluensi Fibonacci (retracement, extension, SMA50/200, angka bulat) dengan skor
  - Kalender: fase bulan, stasiun planet (Merkurius, Venus, Mars), Fibonacci time zone, musiman
  - Tanggal rawan pembalikan (beberapa siklus berdekatan)
  - Uji vs tanggal acak (permutasi) untuk setiap unsur, pada riwayat indeks sejak 2005
  - Papan skor ramalan yang dicatat sebelum terjadi
  - Rentang pergerakan mingguan berbasis probabilitas, dan kesehatan pasar (breadth)

Dipakai sama persis oleh screener Indonesia dan AS; perbedaannya lewat parameter `cfg`.
"""
from __future__ import annotations

import math
from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd

FIB_RET = [0.236, 0.382, 0.5, 0.618, 0.786]
FIB_EXT = [1.272, 1.618]
FIB_TIME = [13, 21, 34, 55, 89, 144]
NEAR = 2          # toleransi hari bursa untuk "tepat"
HORIZON = 92      # hari kalender ke depan untuk kalender
TEST_FROM = "2005-01-01"
RNG = np.random.default_rng(7)
PLANETS = [("Merkurius", "Mercury"), ("Venus", "Venus"), ("Mars", "Mars")]


def ok(v):
    return isinstance(v, (int, float)) and math.isfinite(v)


def r(v, d=2):
    return round(float(v), d) if ok(v) else None


# ---------------------------------------------------------------- ZigZag
def zz_threshold(s: pd.Series) -> float:
    ret = s.pct_change().abs().dropna().tail(252)
    if not len(ret):
        return 0.06
    return float(min(0.25, max(0.03, 8 * ret.mean())))


def zigzag(values: np.ndarray, thr: float):
    """Titik balik terkonfirmasi: [(indeks, harga, 'H'|'L')], plus ekstrem terakhir yang belum terkonfirmasi."""
    piv = []
    n = len(values)
    if n < 3:
        return piv, None
    i0 = 0
    while i0 < n and not math.isfinite(values[i0]):
        i0 += 1
    if i0 >= n:
        return piv, None
    trend, ext_i, ext_v = 0, i0, values[i0]
    lo_i, lo_v, hi_i, hi_v = i0, values[i0], i0, values[i0]
    for i in range(i0 + 1, n):
        v = values[i]
        if not math.isfinite(v):
            continue
        if trend == 0:
            if v > hi_v:
                hi_i, hi_v = i, v
            if v < lo_v:
                lo_i, lo_v = i, v
            if hi_v >= lo_v * (1 + thr) and hi_i > lo_i:
                piv.append((lo_i, lo_v, "L")); trend, ext_i, ext_v = 1, hi_i, hi_v
            elif lo_v <= hi_v * (1 - thr) and lo_i > hi_i:
                piv.append((hi_i, hi_v, "H")); trend, ext_i, ext_v = -1, lo_i, lo_v
        elif trend == 1:
            if v > ext_v:
                ext_i, ext_v = i, v
            elif v <= ext_v * (1 - thr):
                piv.append((ext_i, ext_v, "H")); trend, ext_i, ext_v = -1, i, v
        else:
            if v < ext_v:
                ext_i, ext_v = i, v
            elif v >= ext_v * (1 + thr):
                piv.append((ext_i, ext_v, "L")); trend, ext_i, ext_v = 1, i, v
    tent = (ext_i, ext_v, "H" if trend == 1 else "L") if trend else None
    return piv, tent


# ---------------------------------------------------------------- zona Fibonacci
def round_step(p: float) -> float:
    if p <= 0:
        return 1
    return 10 ** (math.floor(math.log10(p))) / 2


def zones(s: pd.Series, thr: float, piv, tent, tick=None):
    s = s.dropna()
    price = float(s.iloc[-1])
    pts = [(i, v, t) for i, v, t in piv] + ([tent] if tent else [])
    lv = []
    swings = list(zip(pts[:-1], pts[1:]))[-3:]
    for k, (a, b) in enumerate(swings):
        A, B = a[1], b[1]
        last = k == len(swings) - 1
        for f in FIB_RET:
            w = 1.5 if f in (0.382, 0.5, 0.618) else 1.0
            lv.append((B - f * (B - A), w, f"Fib {f * 100:.1f}%".replace(".0%", "%")))
        if last:
            for e in FIB_EXT:
                lv.append((A + e * (B - A), 1.0, f"Proyeksi {e * 100:.1f}%"))
    for i, v, t in pts[-6:-1] if tent else pts[-5:]:
        lv.append((v, 1.0, "Puncak sebelumnya" if t == "H" else "Lembah sebelumnya"))
    for n in (50, 200):
        if len(s) >= n:
            lv.append((float(s.iloc[-n:].mean()), 1.0, f"SMA{n}"))
    st = round_step(price)
    k0 = math.floor(price * 0.8 / st)
    while k0 * st <= price * 1.2:
        if k0 > 0:
            lv.append((k0 * st, 0.5, "Angka bulat"))
        k0 += 1
    lv = sorted((x for x in lv if x[0] > 0 and abs(x[0] / price - 1) <= 0.3), key=lambda x: x[0])
    band = price * max(0.006, thr / 10)
    groups, cur = [], []
    for x in lv:
        if cur and (x[0] - cur[-1][0] > band or x[0] - cur[0][0] > 2 * band):
            groups.append(cur); cur = []
        cur.append(x)
    if cur:
        groups.append(cur)
    out = []
    for g in groups:
        sc = sum(x[1] for x in g)
        fib = any(x[2].startswith(("Fib", "Proyeksi")) for x in g)
        if not fib or (sc < 2 and not any(x[2].startswith("Proyeksi") for x in g)):
            continue
        lo, hi = min(x[0] for x in g), max(x[0] for x in g)
        mid = sum(x[0] * x[1] for x in g) / sc
        out.append({"lo": rt(lo, tick), "hi": rt(hi, tick), "mid": rt(mid, tick), "score": round(sc, 1),
                    "kind": "support" if mid < price else "resistance",
                    "why": sorted({x[2] for x in g}), "dist": round((mid / price - 1) * 100, 2)})
    sup = sorted([z for z in out if z["kind"] == "support"], key=lambda z: -z["mid"])[:3]
    res = sorted([z for z in out if z["kind"] == "resistance"], key=lambda z: z["mid"])[:3]
    for z in sup + res:
        z["strength"] = "kuat" if z["score"] >= 4 else "sedang" if z["score"] >= 2.5 else "lemah"
    return sup, res


def rt(v, tick):
    if tick is None:
        return r(v, 2)
    t = tick(v)
    return float(round(v / t) * t)


# ---------------------------------------------------------------- kalender astronomi dan musiman
def moon_phases(start: date, end: date):
    import ephem

    out, d = [], ephem.Date(start)
    while True:
        nm, fm = ephem.next_new_moon(d), ephem.next_full_moon(d)
        nxt = min(nm, fm)
        dd = ephem.Date(nxt).datetime().date()
        if dd > end:
            break
        out.append((dd, "Bulan baru" if nxt == nm else "Bulan purnama"))
        d = ephem.Date(nxt + 1)
    return out


def planet_stations(start: date, end: date):
    import ephem

    out = []
    for name, cls in PLANETS:
        body = getattr(ephem, cls)()
        prev, pdir = None, None
        d = start - timedelta(days=2)
        while d <= end:
            body.compute(ephem.Date(d))
            lon = float(ephem.Ecliptic(body).lon)
            if prev is not None:
                diff = (lon - prev + math.pi) % (2 * math.pi) - math.pi
                retro = diff < 0
                if pdir is not None and retro != pdir and d >= start:
                    out.append((d, f"{name} {'mulai retrograde' if retro else 'kembali direct'}"))
                pdir = retro
            prev = lon
            d += timedelta(days=1)
    return out


def ramadan_dates(year_from: int, year_to: int):
    """Perkiraan 1 Ramadan dan Idul Fitri (±1 hari) dari panjang tahun Hijriah rata-rata."""
    anchor, H = date(2026, 2, 18), 1447  # 1 Ramadan 1447
    out = []
    for h in range(H - 40, H + 5):
        start = anchor + timedelta(days=round((h - H) * 354.36707))
        if year_from <= start.year <= year_to:
            out.append((start, start + timedelta(days=30)))
    return out


# ---------------------------------------------------------------- uji ketepatan
def near_pivot_mask(n: int, piv_idx: list[int]) -> np.ndarray:
    m = np.zeros(n, bool)
    for i in piv_idx:
        m[max(0, i - NEAR):min(n, i + NEAR + 1)] = True
    return m


def perm_test(mask: np.ndarray, ev_idx: list[int], lo: int, hi: int, n_iter=3000):
    ev = [i for i in ev_idx if lo <= i < hi]
    if len(ev) < 8:
        return None
    obs = float(mask[ev].mean())
    base = float(mask[lo:hi].mean())
    sims = mask[RNG.integers(lo, hi, size=(n_iter, len(ev)))].mean(axis=1)
    p = float((sims >= obs).mean())
    return {"n": len(ev), "hit": round(obs * 100, 1), "base": round(base * 100, 1),
            "lift": round(obs / base, 2) if base else None, "p": round(p, 3), "verdict": verdict(p, obs / base if base else 1)}


def verdict(p, lift):
    if p < 0.05 and lift >= 1.15:
        return "berguna"
    if p < 0.2 and lift > 1:
        return "lemah"
    return "acak"


def ret_test(rets: pd.Series, flag: pd.Series, n_iter=3000):
    flag = flag.reindex(rets.index).fillna(False).astype(bool)
    a, b = rets[flag], rets[~flag]
    if len(a) < 20 or len(b) < 20:
        return None
    diff = a.mean() - b.mean()
    vals, k = rets.to_numpy(), int(flag.sum())
    sims = np.array([vals[RNG.permutation(len(vals))[:k]].mean() for _ in range(n_iter)]) - (vals.sum() - 0) / len(vals)
    obs = a.mean() - vals.mean()
    p = float((np.abs(sims) >= abs(obs)).mean())
    v = "berguna" if p < 0.05 else "lemah" if p < 0.2 else "acak"
    return {"n": int(len(a)), "in": round(a.mean() * 100, 3), "out": round(b.mean() * 100, 3), "diff": round(diff * 100, 3),
            "p": round(p, 3), "verdict": v, "dir": "naik" if diff > 0 else "turun"}


def to_idx(index: pd.DatetimeIndex, d: date) -> int | None:
    i = index.searchsorted(pd.Timestamp(d))
    return int(i) if i < len(index) else None


def run_tests(long: pd.Series, cfg: dict) -> dict:
    s = long.dropna()
    s = s[s.index >= TEST_FROM]
    if len(s) < 1000:
        return {}
    v = s.to_numpy()
    thr = zz_threshold(s)
    piv, _ = zigzag(v, thr)
    pidx = [i for i, _, _ in piv]
    n = len(v)
    mask = near_pivot_mask(n, pidx)
    hi = pidx[-1] if pidx else n  # setelah pivot terakhir belum bisa dinilai
    start, end = s.index[0].date(), s.index[-1].date()
    out = {"from": str(start), "to": str(end), "pivots": len(pidx), "thr": round(thr * 100, 1),
           "base": round(float(mask[:hi].mean()) * 100, 1), "time": {}, "price": {}, "season": {}}

    moons = moon_phases(start, end)
    for kind in ("Bulan baru", "Bulan purnama"):
        out["time"][kind] = perm_test(mask, [to_idx(s.index, d) for d, k in moons if k == kind and to_idx(s.index, d) is not None], 0, hi)
    st = planet_stations(start, end)
    for name, _ in PLANETS:
        out["time"][f"Stasiun {name}"] = perm_test(mask, [to_idx(s.index, d) for d, k in st if k.startswith(name) and to_idx(s.index, d) is not None], 0, hi)
    # Pembanding yang adil: jarak acak 13–144 hari dari titik balik yang SAMA (bukan tanggal acak),
    # karena jarak antar titik balik memang punya pola sendiri.
    ev = [p + f for p in pidx for f in FIB_TIME if p + f < hi]
    if len(ev) >= 8:
        obs = float(mask[ev].mean())
        sims = []
        for _ in range(2000):
            offs = RNG.integers(13, 145, size=(len(pidx), len(FIB_TIME)))
            e2 = [p + o for p, row in zip(pidx, offs) for o in row if p + o < hi]
            sims.append(mask[e2].mean() if e2 else 0)
        sims = np.array(sims)
        p = float((sims >= obs).mean())
        out["time"]["Fibonacci time zone"] = {"n": len(ev), "hit": round(obs * 100, 1), "base": round(float(sims.mean()) * 100, 1),
                                               "lift": round(obs / sims.mean(), 2) if sims.mean() else None, "p": round(p, 3),
                                               "verdict": verdict(p, obs / sims.mean() if sims.mean() else 1), "vs": "jarak acak 13–144 hari"}

    # Fibonacci harga: apakah retracement berhenti di dekat 38,2/50/61,8% lebih sering dari acak?
    rets_ratio = []
    for a, b, c in zip(piv, piv[1:], piv[2:]):
        move = b[1] - a[1]
        if move:
            rets_ratio.append((b[1] - c[1]) / move)
    rr = np.array([x for x in rets_ratio if 0.1 <= x <= 0.95])
    if len(rr) >= 15:
        tol = 0.03
        hit = lambda arr: np.mean([min(abs(x - f) for f in (0.382, 0.5, 0.618)) <= tol for x in arr])
        obs = float(hit(rr))
        # Pembanding yang adil: tiga rasio acak di antara 25–75% diuji pada retracement yang SAMA,
        # karena retracement memang cenderung mengumpul di tengah.
        def hit_r(arr, ratios):
            return np.mean([min(abs(x - f) for f in ratios) <= tol for x in arr])
        sims = np.array([hit_r(rr, RNG.uniform(0.25, 0.75, 3)) for _ in range(2000)])
        p = float((sims >= obs).mean())
        out["price"]["Retracement berhenti di 38,2/50/61,8% (±3 poin)"] = {
            "n": int(len(rr)), "hit": round(obs * 100, 1), "base": round(float(sims.mean()) * 100, 1),
            "lift": round(obs / sims.mean(), 2), "p": round(p, 3), "verdict": verdict(p, obs / sims.mean()), "vs": "3 rasio acak 25–75%"}

    lr = np.log(s).diff().dropna()
    idx = lr.index
    ym = pd.Series(list(zip(idx.year, idx.month)), index=idx)
    first = ~ym.duplicated(keep="first")
    last = ~ym.duplicated(keep="last")
    pos_in_month = ym.groupby(ym).cumcount()
    tom = last | (pos_in_month < 3)
    out["season"]["Pergantian bulan (hari terakhir + 3 hari pertama)"] = ret_test(lr, pd.Series(tom.values, index=idx))
    out["season"]["Januari"] = ret_test(lr, pd.Series(idx.month == 1, index=idx))
    out["season"]["Mei–Oktober (\"sell in May\")"] = ret_test(lr, pd.Series((idx.month >= 5) & (idx.month <= 10), index=idx))
    dec = pd.Series(False, index=idx)
    for y in sorted(set(idx.year)):
        d = idx[(idx.year == y) & (idx.month == 12)]
        dec.loc[d[-10:]] = True
    out["season"]["10 hari bursa terakhir Desember"] = ret_test(lr, dec)
    if cfg.get("ramadan"):
        ram, pre = pd.Series(False, index=idx), pd.Series(False, index=idx)
        for a, b in ramadan_dates(idx[0].year, idx[-1].year):
            ram.loc[(idx >= pd.Timestamp(a)) & (idx < pd.Timestamp(b))] = True
            before = idx[idx < pd.Timestamp(b)][-10:]
            pre.loc[before] = True
        out["season"]["Bulan Ramadan"] = ret_test(lr, ram)
        out["season"]["10 hari bursa sebelum Lebaran"] = ret_test(lr, pre)
    return out


# ---------------------------------------------------------------- kalender ke depan
def trading_days(start: date, n: int, holidays: set[str]) -> list[date]:
    out, d = [], start
    while len(out) < n:
        d += timedelta(days=1)
        if d.weekday() < 5 and d.isoformat() not in holidays:
            out.append(d)
    return out


def calendar(s: pd.Series, piv, cfg: dict, today: date):
    end = today + timedelta(days=HORIZON)
    fut = trading_days(today, 70, cfg.get("holidays", set()))
    ev = []
    for d, k in moon_phases(today + timedelta(days=1), end):
        ev.append({"d": d.isoformat(), "type": "bulan", "what": k})
    for d, k in planet_stations(today + timedelta(days=1), end):
        ev.append({"d": d.isoformat(), "type": "planet", "what": k})
    idx = s.dropna().index
    n = len(idx)
    for i, v, t in piv[-3:]:
        for f in FIB_TIME:
            k = i + f - (n - 1)  # hari bursa ke depan dari hari terakhir
            if 1 <= k <= len(fut):
                ev.append({"d": fut[k - 1].isoformat(), "type": "fibtime",
                           "what": f"{f} hari bursa dari {'puncak' if t == 'H' else 'lembah'} {idx[i].date().strftime('%d/%m/%Y')}"})
    for d in fut:
        nxt = d + timedelta(days=1)
        while nxt.weekday() >= 5 or nxt.isoformat() in cfg.get("holidays", set()):
            nxt += timedelta(days=1)
        if nxt.month != d.month:
            ev.append({"d": d.isoformat(), "type": "musiman", "what": "Hari terakhir bulan (awal efek pergantian bulan)"})
    if cfg.get("ramadan"):
        for a, b in ramadan_dates(today.year, end.year + 1):
            if today < a <= end:
                ev.append({"d": a.isoformat(), "type": "musiman", "what": "Perkiraan awal Ramadan"})
            if today < b <= end:
                ev.append({"d": b.isoformat(), "type": "musiman", "what": "Perkiraan Idul Fitri"})
    ev.sort(key=lambda e: e["d"])
    # tanggal rawan: beberapa siklus waktu dalam ±1 hari bursa
    pos = {d.isoformat(): i for i, d in enumerate(fut)}

    def fpos(ds):
        d = date.fromisoformat(ds)
        while d.isoformat() not in pos and d <= fut[-1]:
            d += timedelta(days=1)
        return pos.get(d.isoformat())

    timing = [(fpos(e["d"]), e) for e in ev if e["type"] in ("bulan", "planet", "fibtime")]
    rawan = []
    for i, d in enumerate(fut):
        hits = [e for p, e in timing if p is not None and abs(p - i) <= 1]
        kinds = {e["type"] for e in hits}
        score = len(hits)
        if score >= 2 and len(kinds) >= 2 or score >= 3:
            rawan.append({"d": d.isoformat(), "score": score, "why": [e["what"] for e in hits]})
    # gabungkan hari berurutan, ambil skor tertinggi
    merged = []
    for x in rawan:
        if merged and (date.fromisoformat(x["d"]) - date.fromisoformat(merged[-1]["d"])).days <= 5:
            if x["score"] > merged[-1]["score"]:
                merged[-1] = x
        else:
            merged.append(x)
    return ev, merged, [d.isoformat() for d in fut]


# ---------------------------------------------------------------- rentang mingguan dan breadth
def weekly_range(s: pd.Series, vix: float | None = None):
    s = s.dropna()
    p = float(s.iloc[-1])
    sig = float(np.log(s).diff().dropna().tail(60).std() * math.sqrt(5))
    out = {"price": r(p), "sigma": round(sig * 100, 2), "r68": [r(p * math.exp(-sig)), r(p * math.exp(sig))],
           "r95": [r(p * math.exp(-2 * sig)), r(p * math.exp(2 * sig))]}
    if ok(vix):
        sv = vix / 100 * math.sqrt(5 / 252)
        out["vix"] = r(vix)
        out["r68vix"] = [r(p * math.exp(-sv)), r(p * math.exp(sv))]
    return out


def breadth(close: pd.DataFrame, cols: list[str]):
    c = close[[x for x in cols if x in close]].tail(520)
    c = c.loc[c.notna().mean(axis=1) > 0.5]  # buang hari yang hanya berisi data indeks
    s200, s50 = c.rolling(200, min_periods=150).mean(), c.rolling(50, min_periods=40).mean()
    a200 = (c > s200).where(s200.notna()).mean(axis=1) * 100
    a50 = (c > s50).where(s50.notna()).mean(axis=1) * 100
    hi = c >= c.rolling(252, min_periods=200).max()
    lo = c <= c.rolling(252, min_periods=200).min()
    ch = c.pct_change()
    last = c.index[-1]
    ser = a200.dropna().tail(252)
    return {"n": int(c.iloc[-1].notna().sum()), "above200": r(a200.iloc[-1], 1), "above50": r(a50.iloc[-1], 1),
            "adv": int((ch.iloc[-1] > 0).sum()), "dec": int((ch.iloc[-1] < 0).sum()),
            "newHi": int(hi.iloc[-1].sum()), "newLo": int(lo.iloc[-1].sum()),
            "series": [[d.strftime("%Y-%m-%d"), r(v, 1)] for d, v in ser.items()],
            "date": last.strftime("%Y-%m-%d")}


# ---------------------------------------------------------------- papan skor
def scoreboard(state: dict, s: pd.Series, rawan: list, sup, res, today: date, name: str):
    sb = state.setdefault(name, {"dates": {}, "zones": []})
    s = s.dropna()
    idx = s.index
    for x in rawan:
        rec = sb["dates"].setdefault(x["d"], {"created": today.isoformat(), "score": x["score"], "why": x["why"]})
        rec.setdefault("created", today.isoformat())
    # catat zona terdekat sekali per minggu
    wk = today.isocalendar()[:2]
    if not sb["zones"] or tuple(sb["zones"][-1]["wk"]) != tuple(wk):
        for z in (sup[:1] + res[:1]):
            sb["zones"].append({"wk": list(wk), "created": today.isoformat(), "kind": z["kind"], "lo": z["lo"], "hi": z["hi"],
                                "price": r(float(s.iloc[-1]))})
    # nilai yang sudah lewat
    thr = zz_threshold(s)
    piv, _ = zigzag(s.to_numpy(), thr)
    pdates = [idx[i] for i, _, _ in piv]
    for d, rec in sb["dates"].items():
        if "hit" in rec:
            continue
        dd = pd.Timestamp(d)
        if dd > idx[-1] or (date.fromisoformat(d) - date.fromisoformat(rec["created"])).days < 3:
            continue
        pos = idx.searchsorted(dd)
        if len(idx) - 1 - pos < 15:
            continue  # tunggu titik balik terkonfirmasi
        rec["hit"] = any(abs(idx.get_loc(p) - pos) <= NEAR for p in pdates)
    for z in sb["zones"]:
        if "hit" in z:
            continue
        cd = pd.Timestamp(z["created"])
        after = s[s.index > cd].head(20)
        if len(after) < 20:
            continue
        touched = after[(after >= z["lo"] * 0.995) & (after <= z["hi"] * 1.005)]
        if z["kind"] == "support":
            broke = (after < z["lo"] * 0.98).any()
            z["hit"] = bool(len(touched) and not broke and after.iloc[-1] > z["hi"])
        else:
            broke = (after > z["hi"] * 1.02).any()
            z["hit"] = bool(len(touched) and not broke and after.iloc[-1] < z["lo"])
        z["touched"] = bool(len(touched))
    sb["zones"] = sb["zones"][-120:]
    done_d = [x for x in sb["dates"].values() if "hit" in x]
    done_z = [x for x in sb["zones"] if "hit" in x and x.get("touched")]
    mask_base = None
    if len(s) > 300:
        m = near_pivot_mask(len(s), [i for i, _, _ in piv])
        mask_base = round(float(m[-260:-15].mean()) * 100, 1)
    return {"dates": {"n": len(done_d), "hit": sum(1 for x in done_d if x["hit"]), "base": mask_base,
                      "pending": sum(1 for x in sb["dates"].values() if "hit" not in x)},
            "zones": {"n": len(done_z), "hit": sum(1 for x in done_z if x["hit"]),
                      "pending": sum(1 for x in sb["zones"] if "hit" not in x)},
            "recent": sorted(([d, x] for d, x in sb["dates"].items() if "hit" in x), key=lambda t: t[0])[-8:]}


# ---------------------------------------------------------------- area support per saham
IN_ABOVE, NEAR_ABOVE, BREAK_BELOW = 0.02, 0.05, 0.01


def support_status(a: dict):
    """('in', zona) bila harga di dalam atau ≤2% di atas zona support (belum jebol),
    ('near', zona) bila 2–5% di atas zona kuat/sedang, selain itu (None, None)."""
    p = a.get("price")
    if not ok(p):
        return None, None
    for z in a.get("sup") or []:
        if z["lo"] * (1 - BREAK_BELOW) <= p <= z["hi"] * (1 + IN_ABOVE):
            return "in", z
    z = (a.get("sup") or [None])[0]
    if z and z["strength"] in ("kuat", "sedang") and z["hi"] * (1 + IN_ABOVE) < p <= z["hi"] * (1 + NEAR_ABOVE):
        return "near", z
    return None, None


def watch(stocks: dict, state: dict, today: date, tick=None) -> dict:
    ws = state.setdefault("_watch", {})
    if ws.get("day") != today.isoformat():
        ws["base"] = ws.get("cur", {})
        ws["day"] = today.isoformat()
    base = ws.get("base", {})
    cur, near = {}, {}
    for t, a in stocks.items():
        k, z = support_status(a)
        if not z:
            continue
        rec = {"lo": z["lo"], "hi": z["hi"], "strength": z["strength"], "score": z["score"], "why": z["why"],
               "dist": round((a["price"] / z["hi"] - 1) * 100, 2), "brk": rt(z["lo"] * (1 - BREAK_BELOW), tick), "price": a["price"]}
        if k == "in":
            rec["since"] = (base.get(t) or {}).get("since") or today.isoformat()
            cur[t] = rec
        else:
            near[t] = rec
    first = not base and not ws.get("init")  # hari pertama: semua saham "baru", jangan dikabarkan
    new = [] if first else sorted(t for t in cur if t not in base)
    if base:
        ws["init"] = True
    broken = []
    for t, b in base.items():
        if t in cur or t not in stocks:
            continue
        p = stocks[t].get("price")
        if ok(p) and p < b["lo"] * (1 - BREAK_BELOW):
            broken.append({"t": t, "lo": b["lo"], "hi": b["hi"], "strength": b["strength"], "price": p,
                           "drop": round((p / b["lo"] - 1) * 100, 2)})
    ws["cur"] = {t: {"lo": v["lo"], "hi": v["hi"], "strength": v["strength"], "since": v["since"]} for t, v in cur.items()}
    return {"in": cur, "near": near, "new": new, "broken": broken, "rules": {"in": IN_ABOVE * 100, "near": NEAR_ABOVE * 100, "brk": BREAK_BELOW * 100}}


# ---------------------------------------------------------------- jalankan
def analyse(s: pd.Series, cfg: dict, today: date, tick=None):
    s = s.dropna()
    thr = zz_threshold(s)
    v = s.to_numpy()
    piv, tent = zigzag(v, thr)
    sup, res = zones(s, thr, piv, tent, tick)
    idx = s.index
    return {"thr": round(thr * 100, 1), "price": rt(float(v[-1]), tick),
            "piv": [[idx[i].strftime("%Y-%m-%d"), rt(p, tick), t] for i, p, t in piv[-12:]],
            "tent": [idx[tent[0]].strftime("%Y-%m-%d"), rt(tent[1], tick), tent[2]] if tent else None,
            "sup": sup, "res": res}, piv


def run(close: pd.DataFrame, indices: dict[str, str], long: dict[str, pd.Series], stock_cols: list[str],
        breadth_cols: list[str], cfg: dict, state: dict, tick=None, vix: float | None = None) -> tuple[dict, dict]:
    """indices: {nama tampilan: kolom di close}. long: {nama: riwayat panjang untuk uji}.
    Mengembalikan (cycles.json, series.json)."""
    today = close.index[-1].date()
    out = {"date": today.isoformat(), "indices": {}, "stocks": {}, "tests": {}, "score": {}}
    series = {"dates": [d.strftime("%Y-%m-%d") for d in close.index[-260:]], "idx": {}, "stocks": {}}
    for name, col in indices.items():
        if col not in close:
            continue
        s = close[col].dropna()
        a, piv = analyse(s, cfg, today)
        ev, rawan, fut = calendar(s, piv, cfg, today)
        a.update({"events": ev, "rawan": rawan, "range": weekly_range(s, vix if name == cfg.get("vix_for") else None)})
        out["indices"][name] = a
        out["future"] = fut
        out["score"][name] = scoreboard(state, s, rawan, a["sup"], a["res"], today, name)
        series["idx"][name] = [r(x) for x in close[col].iloc[-260:].tolist()]
        if name in long:
            try:
                out["tests"][name] = run_tests(long[name], cfg)
            except Exception as e:  # uji tidak boleh menggagalkan seluruh pembaruan
                out["tests"][name] = {"error": str(e)[:200]}
    for t in stock_cols:
        if t not in close or close[t].dropna().shape[0] < 120:
            continue
        s = close[t].dropna()
        a, piv = analyse(s, cfg, today, tick)
        fut = out.get("future") or []
        n = len(s)
        tz = []
        for i, v, ty in piv[-3:]:
            for f in FIB_TIME:
                k = i + f - (n - 1)
                if 1 <= k <= len(fut):
                    tz.append([fut[k - 1], f])
        a["tz"] = sorted(tz)[:8]
        out["stocks"][t] = a
        vals = close[t].iloc[-260:]
        series["stocks"][t] = [None if not ok(x) else (int(round(x)) if tick else round(float(x), 2)) for x in vals.tolist()]
    out["breadth"] = breadth(close, breadth_cols)
    out["watch"] = watch(out["stocks"], state, today, tick)
    return out, series


def dump_series(series: dict) -> str:
    """Satu baris per saham supaya riwayat git tetap kecil."""
    import json

    lines = ['{"dates":' + json.dumps(series["dates"], separators=(",", ":")) + ',',
             '"idx":' + json.dumps(series["idx"], separators=(",", ":")) + ',', '"stocks":{']
    items = list(series["stocks"].items())
    for k, (t, v) in enumerate(items):
        lines.append(json.dumps(t) + ":" + json.dumps(v, separators=(",", ":")) + ("," if k < len(items) - 1 else ""))
    lines.append("}}")
    return "\n".join(lines)
