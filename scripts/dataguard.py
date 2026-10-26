"""Penjaga kualitas data: tandai angka yang tidak wajar supaya tidak ikut sinyal beli.

Saham yang ditandai mendapat r["dq"] (alasan singkat) dan status "Layak beli" diubah menjadi "Tunggu"
dengan alasan "data janggal". Ringkasannya ikut ke Telegram pengelola.
"""
from __future__ import annotations

import math

YIELD_MAX = 15.0     # dividend yield di atas ini hampir selalu salah hitung / dividen spesial
PAYOUT_MAX = 300.0
JUMP = 0.5           # harga naik/turun > 50% dalam sehari: biasanya stock split / data salah


def _num(v):
    return isinstance(v, (int, float)) and math.isfinite(v)


def check(r: dict, closes) -> list[str]:
    """Kembalikan alasan; alasan yang diawali "dividen:" hanya mematikan metode Dividen."""
    why = []
    y = r.get("div")
    if _num(y) and y > YIELD_MAX:
        why.append(f"dividen: yield {y:.1f}% (mungkin dividen spesial)".replace(".", ","))
    pe = r.get("pe")
    if _num(pe) and 0 < pe < 1:
        why.append(f"PER {pe:.2f}".replace(".", ","))
    po = r.get("payout")
    if _num(po) and po > PAYOUT_MAX:
        why.append(f"dividen: payout {po:.0f}% dari laba")
    if closes is not None and len(closes) >= 2:
        a, b = float(closes.iloc[-2]), float(closes.iloc[-1])
        if a > 0 and abs(b / a - 1) > JUMP:
            why.append(f"harga {'+' if b > a else '−'}{abs(b / a - 1) * 100:.0f}% dalam sehari (split/data salah?)")
    if _num(r.get("price")) and r["price"] <= 0:
        why.append("harga nol")
    return why


def apply(rows: list[dict], close) -> list[dict]:
    """Tandai baris yang janggal; kembalikan daftar [{t, why}] untuk ringkasan."""
    out = []
    for r in rows:
        t = r.get("ticker")
        cl = close[t].dropna() if close is not None and t in close else None
        why = check(r, cl)
        if not why:
            r.pop("dq", None)
            continue
        txt = "; ".join(w.replace("dividen: ", "") for w in why)
        r["dq"] = txt
        only_div = all(w.startswith("dividen:") for w in why)
        for mid, st in (r.get("m") or {}).items():
            if (not only_div or mid == "dividend") and st.get("s") == "buy":
                st["s"] = "wait"
                st["rs"] = "data janggal: " + txt
        out.append({"t": t, "why": txt, "liq": r.get("liq"), "div": only_div})
    return out
