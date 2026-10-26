"""Rekam jejak "Rencana beli" (tab Watchlist).

Setiap update sore: catat saham yang muncul sebagai "Beli sekarang" / "Pasang antrean" (aturan sama dengan website),
lalu nilai dengan data candlestick (data/ohlc): kena target R1 (harga tertinggi menyentuh), kena stop (harga
penutupan di bawah stop), atau waktu habis (40 hari bursa). Antrean yang tidak tersentuh dalam 10 hari bursa = tidak terisi.
Hasil disimpan di data/plan_track.json dan ditampilkan di website.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

RR_MIN, UP_MIN = 2.0, 4.0
QUEUE_DAYS, HOLD_DAYS = 10, 40
DONE_KEEP = 400


def _floor_tick(v: float, idr: bool) -> float:
    if not idr:
        return math.floor(v * 100) / 100
    t = 1 if v < 200 else 2 if v < 500 else 5 if v < 2000 else 10 if v < 5000 else 25
    return math.floor(v / t) * t


def plans(d: dict, c: dict, allow: list[str], layak, idr: bool, liquid_only: bool) -> list[dict]:
    """Sama dengan planOf/planList di website."""
    w = c.get("watch") or {}
    stocks = c.get("stocks") or {}
    by = {o["ticker"]: o for o in d.get("stocks", [])}
    out = []
    for near, src in ((False, w.get("in") or {}), (True, w.get("near") or {})):
        for t, z in src.items():
            o, a = by.get(t), stocks.get(t)
            if not o or not a or z.get("strength") == "lemah" or not o.get("price"):
                continue
            if liquid_only and o.get("liq", "L") != "L":
                continue
            if not any(layak(o, m) for m in allow):
                continue
            p = o["price"]
            r1 = next((x for x in a.get("res") or [] if x["strength"] != "lemah"), None)

            def mk(kind, e, stop, zz):
                risk = max(e - stop, e * 0.005)
                up = (r1["lo"] / e - 1) * 100 if r1 else None
                rr = (r1["lo"] - e) / risk if r1 else None
                ok = r1 is None or (rr >= RR_MIN and up >= UP_MIN)
                return {"t": t, "k": kind, "e": e, "s": stop, "g": r1["lo"] if r1 else None,
                        "rr": None if rr is None else round(rr, 2), "z": zz.get("strength"), "ok": ok}

            pl = None
            if not near:
                x = mk("now", p, z["brk"], z)
                if x["ok"]:
                    pl = x
            else:
                x = mk("queue", z["hi"], z["brk"], z)
                if x["ok"] and z["hi"] < p:
                    pl = x
            if pl is None:
                below = sorted((s for s in a.get("sup") or [] if s["strength"] != "lemah" and s["hi"] < z["lo"]), key=lambda s: -s["hi"])
                if below:
                    s2 = below[0]
                    x = mk("queue", s2["hi"], _floor_tick(s2["lo"] * 0.99, idr), s2)
                    if x["ok"]:
                        pl = x
            if pl:
                pl.pop("ok")
                out.append(pl)
    return out


def _bars(ohlc_dir: Path, t: str) -> list:
    f = ohlc_dir / f"{t}.json"
    try:
        return json.loads(f.read_text())["b"]
    except Exception:
        return []


def _ret(e, x, fb, fs):
    return round((x * (1 - fs) / (e * (1 + fb)) - 1) * 100, 2)


def update(path: Path, ohlc_dir: Path, today: str, new_plans: list[dict], fees: tuple[float, float]) -> dict:
    fb, fs = fees
    st = json.loads(path.read_text()) if path.exists() else {}
    st.setdefault("start", today)
    st.setdefault("open", [])
    st.setdefault("done", [])
    still = []
    for r in st["open"]:
        bars = [b for b in _bars(ohlc_dir, r["t"]) if b[0] > r["chk"]]
        res = None
        for b in bars:
            dte, o, h, l, cl = b[0], b[1], b[2], b[3], b[4]
            r["chk"] = dte
            if r.get("in") is None:  # antrean belum terisi
                r["w"] = r.get("w", 0) + 1
                if l <= r["e"]:
                    r["in"], r["ip"] = dte, min(r["e"], o)
                    if cl < r["s"]:
                        res = ("stop", dte, cl)
                        break
                    continue
                if r["w"] >= QUEUE_DAYS:
                    res = ("nofill", dte, None)
                    break
                continue
            r["n"] = r.get("n", 0) + 1
            if r.get("g") and h >= r["g"]:
                res = ("target", dte, max(r["g"], o))
                break
            if cl < r["s"]:
                res = ("stop", dte, cl)
                break
            if r["n"] >= HOLD_DAYS:
                res = ("time", dte, cl)
                break
        if res:
            kind, dte, px = res
            r.update({"res": kind, "xd": dte, "xp": px})
            if px is not None:
                r["ret"] = _ret(r["ip"], px, fb, fs)
            st["done"].append(r)
        else:
            if bars and r.get("in"):
                r["last"] = bars[-1][4]
                r["cur"] = _ret(r["ip"], bars[-1][4], fb, fs)
            still.append(r)
    have = {r["t"] for r in still}
    for p in new_plans:
        if p["t"] in have:
            continue
        r = {**p, "d": today, "chk": today}
        if p["k"] == "now":
            r["in"], r["ip"] = today, p["e"]
        still.append(r)
        have.add(p["t"])
    st["open"] = still
    st["done"] = st["done"][-DONE_KEEP:]
    st["at"] = today
    path.write_text(json.dumps(st, separators=(",", ":")))
    return st


def score(st: dict, kind: str | None = None, since: str | None = None) -> dict:
    D = [r for r in st.get("done", []) if r["res"] != "nofill" and (kind is None or r["k"] == kind) and (since is None or r["xd"] >= since)]
    n = len(D)
    if not n:
        return {"n": 0}
    rets = [r["ret"] for r in D]
    return {"n": n, "tg": sum(r["res"] == "target" for r in D), "sl": sum(r["res"] == "stop" for r in D),
            "tm": sum(r["res"] == "time" for r in D), "avg": round(sum(rets) / n, 2), "win": sum(x > 0 for x in rets)}
