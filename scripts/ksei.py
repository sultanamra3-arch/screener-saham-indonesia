"""Kepemilikan efek bulanan dari KSEI: porsi asing dan institusi (reksa dana, dana pensiun, asuransi) per saham.

Sumber: https://www.ksei.co.id/id/publikasi/data-dan-statistik/kepemilikan-efek (file Balancepos bulanan).
Cache: data/ksei.json -> {"months": [...], "data": {"YYYY-MM": {kode: [asing%, institusi%]}}}
"""
from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import requests

API = "https://www.ksei.co.id/api/securities_ownerships?locale=id"
H = {"User-Agent": "Mozilla/5.0 (screener-saham)", "Accept": "application/json"}
KEEP = 7
TH = 0.5  # perubahan bermakna (poin persen per bulan)


def _parse(txt: str) -> dict:
    lines = [l for l in txt.splitlines() if l.strip()]
    head = [h.strip() for h in lines[0].split("|")]
    idx = {h: i for i, h in enumerate(head) if h not in ("Total",)}
    tot = [i for i, h in enumerate(head) if h == "Total"]  # [total lokal, total asing]
    inst = [idx[k] for k in ("Local IS", "Local PF", "Local MF", "Foreign IS", "Foreign PF", "Foreign MF") if k in idx]
    out = {}
    for l in lines[1:]:
        c = l.split("|")
        if len(c) < len(head) or c[idx["Type"]].strip().upper() != "EQUITY":
            continue
        try:
            loc, fgn = float(c[tot[0]]), float(c[tot[1]])
            allv = loc + fgn
            if allv <= 0:
                continue
            ins = sum(float(c[i]) for i in inst)
            out[c[idx["Code"]].strip()] = [round(fgn / allv * 100, 3), round(ins / allv * 100, 3)]
        except (ValueError, IndexError):
            continue
    return out


def update(cache_file: Path, log=print) -> tuple[dict, bool]:
    cache = json.loads(cache_file.read_text()) if cache_file.exists() else {"months": [], "data": {}}
    new = False
    try:
        items = (requests.get(API, headers=H, timeout=30).json() or {}).get("data") or []
    except Exception as e:
        log(f"  KSEI: daftar file gagal ({str(e)[:80]})")
        return cache, False
    for it in items[:KEEP]:
        m = (it.get("date") or "")[:7]
        files = it.get("pdf_id") or it.get("pdf_en") or []
        if not m or m in cache["data"] or not files:
            continue
        try:
            raw = requests.get(files[0]["url"], headers=H, timeout=90).content
            z = zipfile.ZipFile(io.BytesIO(raw))
            txt = z.read(z.namelist()[0]).decode("utf-8", "replace")
            d = _parse(txt)
            if len(d) > 300:
                cache["data"][m] = d
                new = True
                log(f"  KSEI {m}: {len(d)} saham")
        except Exception as e:
            log(f"  KSEI {m}: gagal ({str(e)[:80]})")
    cache["months"] = sorted(cache["data"])[-KEEP:]
    cache["data"] = {m: cache["data"][m] for m in cache["months"]}
    cache_file.write_text(json.dumps(cache, separators=(",", ":")))
    return cache, new


def apply(rows: list[dict], cache: dict) -> None:
    ms = cache.get("months") or []
    if not ms:
        return
    last, prev = ms[-1], (ms[-2] if len(ms) > 1 else None)
    for r in rows:
        cur = cache["data"][last].get(r["ticker"])
        if not cur:
            continue
        ks = {"m": last, "f": cur[0], "i": cur[1]}
        p = cache["data"][prev].get(r["ticker"]) if prev else None
        if p:
            ks["df"], ks["di"] = round(cur[0] - p[0], 3), round(cur[1] - p[1], 3)
        r["ks"] = ks
        r["ksL"] = [[m, *cache["data"][m][r["ticker"]]] for m in ms if r["ticker"] in cache["data"][m]][-6:]
