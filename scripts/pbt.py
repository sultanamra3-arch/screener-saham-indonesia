"""Pullback Tren v3 (tab Watchlist dan grafik).

Aturan (diuji 216 saham likuid BEI, harian, Nov 2020–Nov 2026, biaya beli 0,15% & jual 0,25%):
- Beli  : harga penutupan di atas EMA50 dan EMA200, RSI 3 hari < 15, dan IHSG di atas rata-rata 50 harinya.
          Dibeli di harga pembukaan hari bursa berikutnya.
- Jual  : penutupan di atas SMA5, atau sudah 15 hari bursa (dijual di pembukaan berikutnya),
          atau harga menyentuh stop darurat 20% di bawah harga beli.
Data dari data/ohlc (saham likuid + IHSG). Hasil: data/pbt.json.
Pemakaian: python scripts/pbt.py
"""
from __future__ import annotations

import json
import math
from pathlib import Path

EMA_LEN, RSI_LEN, RSI_BUY, EXIT_LEN, MAX_BARS, STOP, IDX_LEN = 50, 3, 15.0, 5, 15, 0.20, 50
BUY_FEE, SELL_FEE = 0.0015, 0.0025
WARMUP = 200
# hasil uji panjang (lihat docstring); angka tetap, diperbarui bila aturan diubah
TEST = {"from": "2020", "to": "2026", "stocks": 216, "n": 755, "win": 65.2, "avg": 1.16, "days": 4,
        "test_win": 65.2, "test_avg": 1.58, "y2026": -2.68}


def ema(x: list[float], n: int) -> list[float]:
    a, out = 2 / (n + 1), [x[0]]
    for v in x[1:]:
        out.append(out[-1] + a * (v - out[-1]))
    return out


def sma(x: list[float], n: int) -> list[float | None]:
    out, s = [], 0.0
    for i, v in enumerate(x):
        s += v
        if i >= n:
            s -= x[i - n]
        out.append(s / n if i >= n - 1 else None)
    return out


def rsi(c: list[float], n: int) -> list[float | None]:
    out: list[float | None] = [None] * len(c)
    ag = al = 0.0
    for i in range(1, len(c)):
        d = c[i] - c[i - 1]
        g, l = max(d, 0.0), max(-d, 0.0)
        if i <= n:
            ag += g / n
            al += l / n
            if i < n:
                continue
        else:
            ag += (g - ag) / n
            al += (l - al) / n
        out[i] = 100.0 if al == 0 else 100 - 100 / (1 + ag / al)
    return out


def trades_of(bars: list, idx_ok: dict) -> tuple[list, dict | None, bool]:
    """Simulasi satu saham. Mengembalikan transaksi selesai, posisi berjalan, dan sinyal beli di bar terakhir."""
    d = [b[0] for b in bars]
    o = [float(b[1]) for b in bars]
    lo = [float(b[3]) for b in bars]
    c = [float(b[4]) for b in bars]
    e50, e200, r, s5 = ema(c, EMA_LEN), ema(c, 200), rsi(c, RSI_LEN), sma(c, EXIT_LEN)
    done, pos, pend_in, pend_out = [], None, False, False
    n = len(c)

    def close_pos(i, px, why):
        done.append([pos["d"], pos["p"], d[i], px, round((px * (1 - SELL_FEE) / (pos["p"] * (1 + BUY_FEE)) - 1) * 100, 2), why, i - pos["i"]])

    def sig(i):
        return (i >= WARMUP and r[i] is not None and c[i] > e50[i] and c[i] > e200[i] and r[i] < RSI_BUY and idx_ok.get(d[i], False))

    for i in range(n):
        if pend_in:
            pos = {"d": d[i], "p": o[i], "i": i, "bars": 0, "stop": o[i] * (1 - STOP), "exit": False}
            pend_in = False
        if pend_out and pos:
            close_pos(i, o[i], pos["why"])
            pos, pend_out = None, False
        if pos:
            if lo[i] <= pos["stop"]:
                close_pos(i, min(o[i], pos["stop"]), "stop")
                pos = None
                continue
            pos["bars"] += 1
            why = "sma5" if s5[i] is not None and c[i] > s5[i] else "15hari" if pos["bars"] >= MAX_BARS else None
            if why:
                pos["why"] = why
                if i + 1 < n:
                    pend_out = True
                else:
                    pos["exit"] = why  # dijual di pembukaan besok
        elif sig(i) and i + 1 < n:
            pend_in = True
    buy_now = pos is None and n > 0 and sig(n - 1)
    if pos:
        pos = {"d": pos["d"], "p": pos["p"], "stop": round(pos["stop"], 2), "bars": pos["bars"], "last": c[-1],
               "cur": round((c[-1] * (1 - SELL_FEE) / (pos["p"] * (1 + BUY_FEE)) - 1) * 100, 2), "exit": pos.get("exit") or None}
    return done, pos, buy_now


def run(data: Path, log=print) -> dict:
    files = sorted((data / "ohlc").glob("*.json"))
    load = lambda f: json.loads(f.read_text())
    ix = next((load(f) for f in files if f.stem == "IHSG"), None)
    if not ix:
        raise RuntimeError("data/ohlc/IHSG.json tidak ada")
    ic = [float(b[4]) for b in ix["b"]]
    im = sma(ic, IDX_LEN)
    idx_ok = {b[0]: (m is not None and v > m) for b, v, m in zip(ix["b"], ic, im)}
    out_file = data / "pbt.json"
    old = json.loads(out_file.read_text()) if out_file.exists() else {}
    start = old.get("start") or ix["b"][-1][0]
    trades, opened, now, recent = {}, [], [], []
    for f in files:
        if f.stem == "IHSG":
            continue
        j = load(f)
        bars = [b for b in j.get("b", []) if all(v is not None for v in b[1:5])]
        if len(bars) < WARMUP + 10:
            continue
        t = j.get("t") or f.stem
        done, pos, buy_now = trades_of(bars, idx_ok)
        if done:
            trades[t] = [x[:6] for x in done]
            recent += [[t] + x for x in done]
        if pos:
            opened.append({"t": t, **pos})
        if buy_now:
            now.append({"t": t, "p": float(bars[-1][4])})
    recent.sort(key=lambda x: x[3], reverse=True)
    live = [x for x in recent if x[1] >= start]
    lr = [x[5] for x in live]
    last = ix["b"][-1][0]
    out = {
        "date": last, "start": start,
        "rule": {"ema": EMA_LEN, "rsi": RSI_LEN, "rsiBuy": RSI_BUY, "exit": EXIT_LEN, "max": MAX_BARS, "stop": STOP * 100, "idx": IDX_LEN},
        "mkt": {"ok": bool(idx_ok.get(last)), "ihsg": ic[-1], "sma": round(im[-1], 2) if im[-1] else None},
        "test": TEST,
        "now": sorted(now, key=lambda x: x["t"]),
        "open": sorted(opened, key=lambda x: x["d"], reverse=True),
        "recent": recent[:40],
        "live": {"n": len(lr), "win": sum(v > 0 for v in lr), "avg": round(sum(lr) / len(lr), 2) if lr else None},
        "trades": trades,
    }
    out_file.write_text(json.dumps(out, separators=(",", ":")))
    log(f"Pullback Tren: {len(now)} sinyal beli, {len(opened)} posisi berjalan, IHSG {'di atas' if out['mkt']['ok'] else 'di bawah'} rata-rata {IDX_LEN} hari")
    return out


if __name__ == "__main__":
    run(Path(__file__).resolve().parent.parent / "data")
