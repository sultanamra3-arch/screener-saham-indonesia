"""Kalender dividen: tanggal ex-dividen berikutnya (pasti bila sudah diumumkan, selain itu perkiraan dari pola).

hist   : [["YYYY-MM-DD", jumlah per lembar], ...] riwayat ex-dividen (lama ke baru)
ex_info: "YYYY-MM-DD" atau None, tanggal ex-dividen dari Yahoo (bisa lampau atau mendatang)
"""
from __future__ import annotations

from datetime import date, timedelta
from statistics import median

HORIZON = 75  # hari ke depan yang ditampilkan


def _d(s):
    try:
        return date.fromisoformat(str(s)[:10])
    except Exception:
        return None


def _weekday(d: date) -> date:
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


def next_div(hist: list, ex_info, today: date) -> dict | None:
    h = [(_d(a), float(b)) for a, b in (hist or []) if _d(a) and b]
    h.sort()
    if not h or (today - h[-1][0]).days > 420:
        return None  # bukan pembayar dividen rutin
    recent = [a for a, _ in h if (today - a).days <= 400]
    gaps = [(recent[i + 1] - recent[i]).days for i in range(len(recent) - 1)]
    regular = len(recent) >= 4 and min(gaps) > 0 and max(gaps) / min(gaps) < 1.35  # kuartalan/bulanan teratur
    ex = _d(ex_info)
    if ex and ex >= today and (ex - today).days <= HORIZON:
        # jumlah: pembayaran sekitar setahun lalu, kalau tidak ada pakai yang terakhir
        yr = [b for a, b in h if abs((a + timedelta(days=365) - ex).days) <= 45]
        amt = h[-1][1] if regular or not yr else yr[-1]
        return {"ex": ex.isoformat(), "amt": round(amt, 4), "sure": True}
    cands = []
    for a, b in h:
        p = _weekday(a + timedelta(days=364 if a.weekday() < 5 else 365))
        # lewati bila pembayaran periode ini sudah terjadi (ada ex-date dalam 45 hari dari perkiraan)
        if any(abs((x - p).days) <= 45 and x > a for x, _ in h):
            continue
        if today <= p and (p - today).days <= HORIZON:
            cands.append((p, b))
    if regular:  # pembayar kuartalan/bulanan: terakhir + jarak median
        cands = []
        g = median(gaps)
        p = _weekday(h[-1][0] + timedelta(days=round(g)))
        while p < today:
            p = _weekday(p + timedelta(days=round(g)))
        if (p - today).days <= HORIZON:
            cands.append((p, h[-1][1]))
    if not cands:
        return None
    p, b = min(cands)
    if regular:
        b = h[-1][1]
    return {"ex": p.isoformat(), "amt": round(b, 4), "sure": False}
