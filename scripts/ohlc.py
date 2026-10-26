"""Data candlestick per saham untuk grafik (data/ohlc/<TICKER>.json), dimuat website hanya saat grafik dibuka.

Satu bar per baris supaya riwayat git kecil: [tanggal, open, high, low, close, volume].
"""
from __future__ import annotations

import json
import re
from pathlib import Path

BARS = 420  # ±1,7 tahun: cukup untuk MA200 di sepanjang grafik 1 tahun

_OHL: dict = {}


def keep(df) -> None:
    """Simpan kolom Open/High/Low dari hasil yf.download (dipanggil per batch)."""
    import pandas as pd
    for k in ("Open", "High", "Low"):
        if k in df:
            x = df[k]
            if isinstance(x, pd.Series):
                x = x.to_frame()
            _OHL.setdefault(k, []).append(x)


def slug(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9.]", "_", name)


def write(out_dir: Path, close, volume, cols: list[str], idx: dict[str, str], rename=None, decimals: int = 2) -> int:
    """cols = ticker saham; idx = {nama tampilan: kolom indeks}. Mengembalikan jumlah file."""
    import pandas as pd
    if close is None or not _OHL:
        return 0
    close = close.iloc[-(BARS + 30):]
    if volume is not None:
        volume = volume.reindex(close.index)
    ohl = {}
    for k, fr in _OHL.items():
        a = pd.concat(fr, axis=1)
        a = a.loc[:, ~a.columns.duplicated()]
        if rename:
            a.columns = [rename(c) for c in a.columns]
        ohl[k] = a.reindex(close.index)
    out_dir.mkdir(parents=True, exist_ok=True)
    rnd = (lambda v: int(round(v))) if decimals == 0 else (lambda v: round(float(v), decimals))
    want = {c: c for c in cols} | {slug(n): c for n, c in idx.items()}
    n = 0
    for fname, col in want.items():
        if col not in close:
            continue
        c = close[col]
        o, h, l = (ohl[k][col] if col in ohl.get(k, {}) else c for k in ("Open", "High", "Low"))
        v = volume[col] if volume is not None and col in volume else None
        rows = []
        for i, d in enumerate(close.index):
            cv = c.iloc[i]
            if pd.isna(cv):
                continue
            ov, hv, lv = o.iloc[i], h.iloc[i], l.iloc[i]
            ov = cv if pd.isna(ov) else ov
            hv = max(x for x in (hv, ov, cv) if not pd.isna(x))
            lv = min(x for x in (lv, ov, cv) if not pd.isna(x))
            vv = 0 if v is None or pd.isna(v.iloc[i]) else int(v.iloc[i])
            rows.append([d.strftime("%Y-%m-%d"), rnd(ov), rnd(hv), rnd(lv), rnd(cv), vv])
        rows = rows[-BARS:]
        if len(rows) < 30:
            continue
        txt = '{"t":' + json.dumps(fname) + ',"b":[\n' + ",\n".join(json.dumps(r, separators=(",", ":")) for r in rows) + "\n]}"
        (out_dir / f"{fname}.json").write_text(txt)
        n += 1
    for f in out_dir.glob("*.json"):  # buang saham yang sudah tidak dipantau
        if f.stem not in want:
            f.unlink()
    return n
