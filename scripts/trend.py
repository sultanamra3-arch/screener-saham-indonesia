"""Garis tren otomatis (dari titik balik ZigZag) untuk grafik: statistik historis dan rekam jejak sinyal.

Aturan (sama dengan yang digambar di grafik):
  - Garis naik  = garis lurus (skala log) melalui 2 lembah terakhir, bila lembah kedua lebih tinggi.
  - Garis turun = garis lurus melalui 2 puncak terakhir, bila puncak kedua lebih rendah.
  - Titik balik hanya dipakai setelah terkonfirmasi (harga sudah berbalik sejauh ambang ZigZag), jadi tanpa melihat masa depan.
Sinyal yang dinilai (H hari bursa ke depan, setelah biaya):
  brk_up   = harga ditutup menembus garis turun ke atas
  brk_dn   = harga ditutup menembus garis naik ke bawah
  touch_up = harga menyentuh garis naik lalu ditutup di atasnya (pantulan)
  touch_dn = harga menyentuh garis turun lalu ditutup di bawahnya (tertolak)
Hasil: <data>/trend_stats.json (statistik) dan <data>/trend_track.json (rekam jejak sinyal sejak dipasang).
"""
from __future__ import annotations

import json
import math
from datetime import date
from pathlib import Path

import numpy as np

H = 10           # hari bursa ke depan yang dinilai
WARM = 120       # bar awal yang dilewati (butuh titik balik)
KINDS = ("brk_up", "brk_dn", "touch_up", "touch_dn")


def zz_threshold(c: np.ndarray) -> float:
    r = np.abs(np.diff(c[-253:]) / c[-253:-1])
    r = r[np.isfinite(r)]
    return float(min(0.25, max(0.03, 8 * r.mean()))) if len(r) else 0.06


def zigzag(v: np.ndarray, thr: float):
    """[(indeks, harga, 'H'|'L', indeks konfirmasi)]"""
    piv, n = [], len(v)
    if n < 3:
        return piv
    trend, lo_i, hi_i, lo_v, hi_v, ext_i, ext_v = 0, 0, 0, v[0], v[0], 0, v[0]
    for i in range(1, n):
        x = v[i]
        if trend == 0:
            if x > hi_v:
                hi_i, hi_v = i, x
            if x < lo_v:
                lo_i, lo_v = i, x
            if hi_v >= lo_v * (1 + thr) and hi_i > lo_i:
                piv.append((lo_i, lo_v, "L", i)); trend, ext_i, ext_v = 1, hi_i, hi_v
            elif lo_v <= hi_v * (1 - thr) and lo_i > hi_i:
                piv.append((hi_i, hi_v, "H", i)); trend, ext_i, ext_v = -1, lo_i, lo_v
        elif trend == 1:
            if x > ext_v:
                ext_i, ext_v = i, x
            elif x <= ext_v * (1 - thr):
                piv.append((ext_i, ext_v, "H", i)); trend, ext_i, ext_v = -1, i, x
        else:
            if x < ext_v:
                ext_i, ext_v = i, x
            elif x >= ext_v * (1 + thr):
                piv.append((ext_i, ext_v, "L", i)); trend, ext_i, ext_v = 1, i, x
    return piv


def lines_at(piv, t):
    P = [p for p in piv if p[3] <= t]
    lo = [p for p in P if p[2] == "L"][-2:]
    hi = [p for p in P if p[2] == "H"][-2:]
    up = (lo[0][0], math.log(lo[0][1]), lo[1][0], math.log(lo[1][1])) if len(lo) == 2 and lo[1][1] > lo[0][1] else None
    dn = (hi[0][0], math.log(hi[0][1]), hi[1][0], math.log(hi[1][1])) if len(hi) == 2 and hi[1][1] < hi[0][1] else None
    return up, dn


def val(ln, t):
    return math.exp(ln[1] + (ln[3] - ln[1]) * (t - ln[0]) / (ln[2] - ln[0]))


def events_at(piv, h, l, c, t):
    """Sinyal yang terjadi pada bar t."""
    up, dn = lines_at(piv, t)
    out = []
    if dn:
        v1, v0 = val(dn, t), val(dn, t - 1)
        if c[t - 1] <= v0 and c[t] > v1:
            out.append("brk_up")
        elif h[t] >= v1 * 0.99 and c[t] < v1 and c[t - 1] < v0 * 0.99:
            out.append("touch_dn")
    if up:
        s1, s0 = val(up, t), val(up, t - 1)
        if c[t - 1] >= s0 and c[t] < s1:
            out.append("brk_dn")
        elif l[t] <= s1 * 1.01 and c[t] > s1 and c[t - 1] > s0 * 1.01:
            out.append("touch_up")
    return out, up, dn


def load_ohlc(d: Path, skip_last: bool = False) -> dict:
    out = {}
    for f in sorted(d.glob("*.json")):
        try:
            b = json.loads(f.read_text())["b"]
        except Exception:
            continue
        if skip_last:
            b = b[:-1]
        if len(b) < WARM + H + 20:
            continue
        a = np.array([[x[2], x[3], x[4]] for x in b], float)
        if not np.all(np.isfinite(a)) or (a <= 0).any():
            continue
        out[f.stem] = ([x[0] for x in b], a)
    return out


def stats(data: dict, cost: float, skip=()) -> dict:
    base, ev = [], {k: [] for k in KINDS}
    scen = [0, 0, 0]
    for k, (dates, a) in data.items():
        if k in skip:
            continue
        h, l, c = a.T
        n = len(c)
        piv = zigzag(c, zz_threshold(c))
        thr = zz_threshold(c)
        for t in range(WARM, n - H - 1):
            r = c[t + H] / c[t] - 1 - cost
            base.append(r)
            es, up, dn = events_at(piv, h, l, c, t)
            for e in es:
                ev[e].append(r)
            if "touch_up" in es:
                tgt = val(dn, t) if dn and val(dn, t) > c[t] * 1.02 else c[t] * (1 + 2 * thr)
                res = 2
                for j in range(t + 1, min(n, t + 31)):
                    if h[j] >= tgt:
                        res = 0; break
                    if c[j] < val(up, j) * 0.98:
                        res = 1; break
                scen[res] += 1
    B = np.array(base)
    rng = np.random.default_rng(7)
    out = {"h": H, "cost": round(cost * 100, 2), "n_sym": len(data) - len(skip), "n_base": len(B),
           "base": {"avg": round(float(B.mean()) * 100, 2), "med": round(float(np.median(B)) * 100, 2), "win": round(float((B > 0).mean()) * 100, 1)}, "ev": {}}
    for k, v in ev.items():
        v = np.array(v)
        if len(v) < 20:
            out["ev"][k] = {"n": int(len(v))}
            continue
        sims = np.array([rng.choice(B, len(v)).mean() for _ in range(400)])
        p = float((sims >= v.mean()).mean() if v.mean() >= B.mean() else (sims <= v.mean()).mean())
        out["ev"][k] = {"n": int(len(v)), "avg": round(float(v.mean()) * 100, 2), "med": round(float(np.median(v)) * 100, 2),
                        "win": round(float((v > 0).mean()) * 100, 1), "diff": round(float(v.mean() - B.mean()) * 100, 2), "p": round(p * 100, 1)}
    tot = sum(scen)
    if tot:
        out["scen"] = {"n": tot, "up": round(scen[0] / tot * 100), "dn": round(scen[1] / tot * 100), "none": round(scen[2] / tot * 100)}
    return out


def track(data: dict, file: Path, today: str, cost: float, skip=()):
    """Catat sinyal hari ini, nilai sinyal yang sudah H hari bursa."""
    T = json.loads(file.read_text()) if file.exists() else {}
    T.setdefault("start", today)
    opn, done = T.get("open", []), T.get("done", [])
    # rata-rata semua saham per tanggal untuk pembanding (kenaikan H hari)
    idx = {k: {d: i for i, d in enumerate(v[0])} for k, v in data.items()}
    still = []
    for r in opn:
        k = r["t"]
        if k not in data or r["d"] not in idx[k]:
            continue
        dates, a = data[k]
        i = idx[k][r["d"]]
        if i + H >= len(dates):
            still.append(r); continue
        c = a[:, 2]
        ret = (c[i + H] / c[i] - 1 - cost) * 100
        mk = [v[1][idx[kk][r["d"]] + H, 2] / v[1][idx[kk][r["d"]], 2] - 1 for kk, v in data.items()
              if r["d"] in idx[kk] and idx[kk][r["d"]] + H < len(v[0])]
        ex = ret - (float(np.mean(mk)) * 100 if mk else 0)
        done.append({**r, "xd": dates[i + H], "xp": round(float(c[i + H]), 6), "ret": round(ret, 2), "ex": round(ex, 2)})
    seen = {(r["t"], r["d"], r["k"]) for r in still + done}
    for k, (dates, a) in data.items():
        if k in skip or dates[-1] != today:
            continue
        h, l, c = a.T
        piv = zigzag(c, zz_threshold(c))
        es, _, _ = events_at(piv, h, l, c, len(c) - 1)
        for e in es:
            if (k, today, e) not in seen:
                still.append({"t": k, "k": e, "d": today, "p": round(float(c[-1]), 6)})
    T["open"], T["done"] = still, done[-500:]
    T["today"] = today
    file.write_text(json.dumps(T, separators=(",", ":")))
    return len(still), len(done)


def run(data_dir: Path, cost: float, skip=(), skip_last: bool = False, log=print):
    """Dipanggil dari fetch_data.py / fetch_kripto.py setelah data candlestick ditulis."""
    try:
        data = load_ohlc(data_dir / "ohlc", skip_last)
        if not data:
            return
        st = stats(data, cost, skip)
        st["date"] = max(v[0][-1] for v in data.values())
        (data_dir / "trend_stats.json").write_text(json.dumps(st, separators=(",", ":")))
        o, dn = track(data, data_dir / "trend_track.json", st["date"], cost, skip)
        log(f"Garis tren: {st['n_sym']} grafik, sinyal berjalan {o}, selesai {dn}")
    except Exception as e:  # tidak boleh menggagalkan pembaruan utama
        log(f"Garis tren gagal: {e}")


if __name__ == "__main__":
    import sys
    run(Path(sys.argv[1]), float(sys.argv[2]) if len(sys.argv) > 2 else 0.0)
