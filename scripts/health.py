"""
Laporan kesehatan bulanan ke Telegram, plus pengingat daftar libur bursa untuk tahun depan.

  python scripts/health.py            # kirim laporan
  python scripts/health.py --dry-run  # cetak saja
"""
from __future__ import annotations

import json
import os
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
import notify_telegram as N  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
REPO = os.environ.get("GITHUB_REPOSITORY", "")
IS_ID = "indonesia" in REPO.lower() or (ROOT / "data" / "fund_cache.json").exists()
FLAG, MARKET = ("🇮🇩", "BEI") if IS_ID else ("🇺🇸", "bursa AS")
BULAN = ["Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli", "Agustus", "September", "Oktober", "November", "Desember"]


def gh(path: str):
    tok = os.environ.get("GITHUB_TOKEN")
    if not tok or not REPO:
        return None
    try:
        r = requests.get(f"https://api.github.com/repos/{REPO}{path}", timeout=30,
                         headers={"Authorization": f"Bearer {tok}", "Accept": "application/vnd.github+json"})
        return r.json() if r.status_code == 200 else None
    except Exception:
        return None


def pct(n, d):
    return f"{n * 100 // d}%" if d else "–"


def report(today: date | None = None) -> str:
    today = today or datetime.now(N.WIB).date()
    L = [f"🩺 {FLAG} {N.b('Laporan kesehatan screener — ' + BULAN[today.month - 1] + ' ' + str(today.year))}", ""]
    warn = 0

    # data terakhir
    d = json.loads((ROOT / "data" / "stocks.json").read_text())
    pdate = date.fromisoformat(d["priceDate"])
    age = (today - pdate).days
    ok_age = age <= 4
    warn += not ok_age
    L.append(f"{'✅' if ok_age else '⚠️'} Harga penutupan terakhir: {N.hari(d['priceDate'], True)} ({age} hari lalu)")

    s = d.get("stocks", [])
    n = len(s)
    price = sum(1 for o in s if isinstance(o.get("price"), (int, float)))
    fund = sum(1 for o in s if isinstance(o.get("pe"), (int, float)) or isinstance(o.get("pb"), (int, float)))
    sig = sum(1 for o in s if o.get("m"))
    L.append(f"{'✅' if price >= n * 0.95 else '⚠️'} {n} saham · harga {pct(price, n)} · fundamental {pct(fund, n)} · sinyal {pct(sig, n)}")
    warn += price < n * 0.95
    if IS_ID:
        lc = d.get("liqCount") or {}
        L.append(f"   Likuid {lc.get('L', 0)}, kurang likuid {lc.get('K', 0)}, tidak likuid {lc.get('T', 0)}")
        syr = d.get("syariahSource")
        L.append(f"{'✅' if syr else '⚠️'} Daftar syariah: {syr.replace('.aspx', '') if syr else 'tidak tersedia'}")
        warn += not syr
    elif d.get("hasNdx") is False:
        L.append("⚠️ Daftar Nasdaq-100 terakhir gagal diambil")
        warn += 1

    # run gagal 31 hari terakhir
    since = (datetime.now(timezone.utc) - timedelta(days=31)).strftime("%Y-%m-%d")
    runs = gh(f"/actions/runs?per_page=100&created=>{since}")
    if runs:
        rs = [r for r in runs.get("workflow_runs", []) if r.get("event") in ("schedule", "workflow_dispatch")]
        bad = [r for r in rs if r.get("conclusion") == "failure"]
        L.append(f"{'✅' if not bad else '⚠️'} Jadwal otomatis 31 hari: {len(rs)} kali jalan, {len(bad)} gagal")
        warn += bool(bad)

    # ukuran repo
    info = gh("")
    if info and isinstance(info.get("size"), int):
        mb = info["size"] / 1024
        L.append(f"{'✅' if mb < 800 else '⚠️'} Ukuran repo: {mb:,.0f} MB dari batas wajar ±1.000 MB".replace(",", "."))
        warn += mb >= 800

    # daftar libur tahun depan
    nxt = today.year + 1
    has_next = any(x.startswith(str(nxt)) for x in N.HOLIDAYS)
    if not has_next and today.month >= 11:
        L += ["", f"📅 {N.b(f'Daftar libur {MARKET} {nxt} belum dimasukkan.')} Minta Claude memperbaruinya di "
                  f"scripts/notify_telegram.py, supaya pengingat tidak terkirim di hari libur."]
        warn += 1
    elif not has_next:
        L.append(f"📅 Daftar libur {nxt} belum ada (akan diingatkan mulai November)")

    L += ["", "Semua normal 👍" if not warn else f"Ada {warn} hal yang perlu dicek.",
          f'🔗 <a href="{N.SITE}">Buka screener</a>']
    return "\n".join(L)


if __name__ == "__main__":
    msg = report()
    if "--dry-run" in sys.argv:
        print(msg)
    else:
        N.send(msg)
