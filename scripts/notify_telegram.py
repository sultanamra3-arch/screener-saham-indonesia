"""
Pesan Telegram ringkas untuk Screener Saham Indonesia (BEI). Hanya saham likuid.

  python scripts/notify_telegram.py             # ringkasan pagi (setelah data diperbarui)
  python scripts/notify_telegram.py --reminder  # pengingat order 08.15 WIB sebelum pra-pembukaan BEI
  python scripts/notify_telegram.py --failed    # peringatan bila pembaruan data gagal
  tambahkan --dry-run untuk mencetak pesan tanpa mengirim

Butuh secret TELEGRAM_BOT_TOKEN dan TELEGRAM_CHAT_ID. Jika belum diisi, pesan hanya dicetak.
"""
from __future__ import annotations

import html
import math
import json
import os
import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

ROOT = Path(__file__).resolve().parent.parent
DATA_FILE = ROOT / "data" / "stocks.json"
SITE = "https://sultanamra3-arch.github.io/screener-saham-indonesia/"
TOP = 5
WIB = ZoneInfo("Asia/Jakarta")
NAMES = {"value": "Value", "growth": "Growth", "quality": "Quality", "dividend": "Dividen",
         "canslim": "CAN SLIM", "momentum": "Momentum", "swing": "Swing"}
# Urutan prioritas tampil: jangka panjang dulu, swing (paling sering dan paling pendek) terakhir
ORDER = ["canslim", "value", "growth", "quality", "dividend", "momentum", "swing"]
HARI = ["Sen", "Sel", "Rab", "Kam", "Jum", "Sab", "Min"]
BULAN = ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des"]
# Hari libur Bursa Efek Indonesia 2026 (termasuk cuti bersama). Perbarui tiap akhir tahun.
HOLIDAYS = {
    "2026-01-01", "2026-01-16", "2026-02-16", "2026-02-17", "2026-03-18", "2026-03-19", "2026-03-20",
    "2026-03-23", "2026-03-24", "2026-04-03", "2026-05-01", "2026-05-14", "2026-05-15", "2026-05-27",
    "2026-05-28", "2026-06-01", "2026-06-16", "2026-08-17", "2026-08-25", "2026-12-24", "2026-12-25", "2026-12-31",
}


def usd(v) -> str:
    if not isinstance(v, (int, float)):
        return "–"
    return "Rp" + f"{v:,.0f}".replace(",", ".")


def pct(v) -> str:
    if not isinstance(v, (int, float)):
        return "–"
    s = f"{abs(v):.1f}".replace(".", ",")
    return ("+" if v > 0 else "−" if v < 0 else "") + s + "%"


def ribu(n) -> str:
    return f"{int(n):,}".replace(",", ".")


def b(t) -> str:
    return f"<b>{html.escape(str(t))}</b>"


def e(t) -> str:
    return html.escape(str(t or ""))


def hari(d: str, year=False) -> str:
    dt = date.fromisoformat(d)
    return f"{HARI[dt.weekday()]} {dt.day} {BULAN[dt.month - 1]}" + (f" {dt.year}" if year else "")


def plan_text(mid: str, st: dict) -> str:
    lv = st.get("lv") or {}
    if mid == "canslim":
        return f"stop {usd(lv.get('stop'))} · target {usd(lv.get('target'))} (awas ARB)"
    if mid == "swing":
        return f"jual saat tutup > SMA5 ({usd(lv.get('exit'))}), tanpa stop"
    if mid == "momentum":
        return "tanpa stop, dicek tiap awal bulan"
    if mid == "value":
        return f"target {usd(lv.get('target'))} (+50%) atau 2 tahun"
    if mid == "growth":
        return f"jual ≥ {usd(lv.get('target'))} (PEG 2)"
    if mid == "quality":
        return "tanpa stop/target, tahan selama kualitas terjaga"
    if mid == "dividend":
        return "tanpa stop/target, tahan selama dividen aman"
    return ""


def signals(d: dict):
    day = d.get("priceDate")
    buys, sells, holds, first = [], [], 0, 0
    for o in d.get("stocks", []):
        if o.get("liq") != "L":
            continue
        npass = sum(1 for m in (o.get("m") or {}).values() if m.get("p"))
        for mid in ORDER:
            st = (o.get("m") or {}).get(mid) or {}
            s = st.get("s")
            if s == "buy" and st.get("b") == day:
                if st.get("first"):
                    first += 1
                else:
                    buys.append((o, mid, st, npass))
            elif s == "sell" and st.get("sd") == day:
                sells.append((o, mid, st, npass))
            elif s == "hold":
                holds += 1
    key = lambda x: (ORDER.index(x[1]), -x[3], -(x[0].get("mcap") or 0))
    buys.sort(key=key)
    sells.sort(key=key)
    return buys, sells, holds, first



def layak(o: dict, mid: str) -> bool:
    """Layak dibeli hari ini oleh orang yang belum punya (sama dengan status 'Layak beli' di website)."""
    st = (o.get("m") or {}).get(mid) or {}
    s, lv, p = st.get("s"), st.get("lv") or {}, o.get("price")
    if s == "buy":
        return True
    if s != "hold" or not p:
        return False
    if mid == "canslim":
        piv = st.get("bp") or lv.get("buy")
        return bool(piv) and p <= piv * 1.05
    if mid == "momentum":
        return (o.get("momRank") or 0) >= 90
    if mid == "swing":
        return bool(st.get("p"))
    return bool(st.get("p")) and (lv.get("buy") is None or p <= lv["buy"])

INV = ["value", "growth", "quality", "dividend"]


def market_regime(d: dict, c: dict) -> str:
    b = (c.get("breadth") or {}).get("above200")
    ok = (d.get("market") or {}).get("ok")
    if b is None:
        return "tertekan" if ok is False else "naik" if ok else "campuran"
    if b >= 60 and ok is not False:
        return "naik"
    if b < 40 or (ok is False and b < 50):
        return "tertekan"
    return "campuran"


RR_MIN, UP_MIN = 2, 4.0


_ftick = lambda v: (lambda t: math.floor(v / t) * t)(1 if v < 200 else 2 if v < 500 else 5 if v < 2000 else 10 if v < 5000 else 25)


def support_section(d: dict, show_waits: bool = True) -> list[str]:
    f = ROOT / "data" / "cycles.json"
    if not f.exists():
        return []
    c = json.loads(f.read_text())
    w = c.get("watch") or {}
    if not w:
        return []
    reg = market_regime(d, c)
    st = d.get("stats") or {}
    bad = {m for m in ("canslim", "momentum", "swing") if (st.get(m) or {}).get("n", 0) >= 10 and (st.get(m) or {}).get("avg", 0) < 0}
    allow = INV if reg == "tertekan" else [m for m in ORDER if m not in bad]
    by = {o["ticker"]: o for o in d.get("stocks", [])}

    def sig(o, ms):
        mm = o.get("m") or {}
        bb = [NAMES[m] for m in ms if layak(o, m)]
        return bb, []

    rng = lambda z: usd(z["lo"]) if z["lo"] == z["hi"] else f"{usd(z['lo'])}–{usd(z['hi'])}"
    stocks = c.get("stocks") or {}

    def room(t, z):
        """R1 = resistance kuat/sedang terdekat; R:R = ruang ke R1 / jarak ke batas jebol; S2 = support berikutnya."""
        a = stocks.get(t) or {}
        p = z.get("price") or a.get("price")
        r1 = next((x for x in a.get("res") or [] if x["strength"] != "lemah"), None)
        risk = max(p - z["brk"], p * 0.005)
        rr = (r1["lo"] - p) / risk if r1 else None
        if r1 and (r1["lo"] / p - 1) * 100 < UP_MIN:
            rr = min(rr, RR_MIN - 0.01)  # ruang naik terlalu sempit
        s2 = next((x for x in a.get("sup") or [] if x["hi"] < z["lo"] and x["strength"] != "lemah"), None)
        rr2 = None
        if s2 and r1:
            rr2 = (r1["lo"] - s2["hi"]) / max(s2["hi"] - s2["lo"] * 0.99, s2["hi"] * 0.005)
            if (r1["lo"] / s2["hi"] - 1) * 100 < UP_MIN:
                rr2 = min(rr2, RR_MIN - 0.01)
        return r1, rr, s2, rr2

    def good(t, o, z, ms):
        if not o or not z or o.get("liq", "L") != "L" or z["strength"] == "lemah":
            return None
        bb, hh = sig(o, ms)
        return (bb, hh) if (bb or hh) else None

    items, waits = [], []
    fresh = set(w.get("new") or []) | set(w.get("lower") or [])
    for t, z in (w.get("in") or {}).items():
        o = by.get(t)
        g = good(t, o, z, allow)
        if not g:
            continue
        r1, rr, s2, rr2 = room(t, z)
        if rr is None or rr >= RR_MIN:
            if t in fresh:
                items.append((0 if z["strength"] == "kuat" else 1, -(rr or 9), t, o, z, g, r1, rr, t in (w.get("lower") or [])))
        elif s2 and (rr2 is None or rr2 >= RR_MIN):
            waits.append((-(rr2 or 9), t, o, s2, rr2))
    items.sort(key=lambda x: x[:3])
    waits.sort(key=lambda x: x[:2])
    L = []
    if items:
        L += ["", b(f"✅ Rencana beli: bisa dibeli sekarang ({min(len(items), 8)})")]
        for _, _, t, o, z, (bb, hh), r1, rr, low in items[:8]:
            s = " · ".join(x for x in (f"Layak beli: {', '.join(bb)}" if bb else "", f"Tahan: {', '.join(hh)}" if hh else "") if x)
            tgt = f"{usd(r1['lo'])} (R:R 1:{str(round(rr, 1)).replace('.', ',')})" if r1 else "terbuka (tak ada resistance kuat ≤30%)"
            L.append(f"{b(t)} beli ≤ {usd(o.get('price'))} · stop &lt; {usd(z['brk'])} · target {tgt} · support {rng(z)} ({z['strength']}){' · baru turun ke support berikutnya' if low else ''}")
            L.append(f"<i>{e(s)}</i>")
        if len(items) > 8:
            L.append(f"…dan {len(items) - 8} lainnya di tab Watchlist")
    if waits and show_waits:
        L += ["", b(f"⏳ Pasang antrean beli ({len(waits)})"),
              "<i>Ruang naik dari harga sekarang masih sempit; pasang order beli di harga ini.</i>"]
        L.append(" · ".join(f"{b(t)} {usd(s2['hi'])} (stop &lt; {usd(_ftick(s2['lo'] * 0.99))})" for _, t, o, s2, rr2 in waits[:6])
                 + (f" · +{len(waits) - 6} lainnya" if len(waits) > 6 else ""))
    brk = []
    for x in w.get("broken") or []:
        o = by.get(x["t"])
        if o and o.get("liq", "L") == "L":
            bb, hh = sig(o, ORDER)
            if bb or hh:
                brk.append((x, o))
    if brk:
        L += ["", b(f"⚠️ Support jebol ({min(len(brk), 5)})")]
        for x, o in brk[:5]:
            L.append(f"{b(x['t'])} {usd(x['price'])} · di bawah zona {rng(x)} ({pct(x['drop'])}). Tunda pembelian, evaluasi ulang.")
    return L



def track_section(d: dict) -> list[str]:
    """Skor mingguan Rekam jejak Rencana beli (dikirim untuk sesi hari Jumat)."""
    f = ROOT / "data" / "plan_track.json"
    if not f.exists() or date.fromisoformat(d["priceDate"]).weekday() != 4:
        return []
    import plan_track
    st = json.loads(f.read_text())
    s = plan_track.score(st)
    wk = (date.fromisoformat(d["priceDate"]) - timedelta(days=6)).isoformat()
    w = plan_track.score(st, since=wk)
    run = [r for r in st.get("open", []) if r.get("in")]
    fmt = lambda x: ("+" if x >= 0 else "−") + f"{abs(x):.2f}".replace(".", ",") + "%"
    L = ["", b("📈 Rekam jejak Rencana beli")]
    if s.get("n"):
        L.append(f"Sejak {hari(st['start'], True)}: {s['n']} selesai · 🎯 {s['tg']} target · 🛑 {s['sl']} stop · ⏰ {s['tm']} · rata-rata {fmt(s['avg'])}")
    else:
        L.append(f"Dicatat sejak {hari(st['start'], True)}; belum ada transaksi yang selesai.")
    if w.get("n"):
        L.append(f"Minggu ini: {w['n']} selesai, rata-rata {fmt(w['avg'])}")
    if run:
        L.append(f"Berjalan: {len(run)} posisi, rata-rata {fmt(sum(r.get('cur', 0) for r in run) / len(run))}")
    return L


def extras_section(d: dict) -> list[str]:
    """Insider membeli (AS), arus asing KSEI (ID), dan pengingat ex-dividen."""
    from datetime import date as _date, timedelta as _td
    L = []
    rows = [o for o in d.get("stocks", []) if o.get("liq", "L") == "L"]
    today = _date.fromisoformat(d["priceDate"])
    prev = d.get("prevPriceDate") or (today - _td(days=3)).isoformat()
    # 👤 insider (hanya ada di data AS)
    new_ins = sorted([o for o in rows if o.get("ins") and o["ins"].get("f", "") > prev], key=lambda o: -o["ins"]["v"])
    if new_ins:
        L += ["", b(f"👤 Insider membeli — laporan baru ({len(new_ins)})")]
        for o in new_ins[:6]:
            i = o["ins"]
            lay = [NAMES[m] for m in ORDER if layak(o, m)]
            L.append(f"{b(o['ticker'])} {usd(o.get('price'))} · {i['p']} orang, total {usd(i['v'])}{' ⭐ beberapa orang sekaligus' if i.get('cl') else ''}"
                     + (f" · <i>Layak beli: {e(', '.join(lay))}</i>" if lay else ""))
    # 🌏 KSEI bulanan (hanya ada di data Indonesia)
    if d.get("ksNew"):
        ks = [o for o in rows if (o.get("ks") or {}).get("df") is not None]
        if ks:
            m = ks[0]["ks"]["m"]
            m = ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des"][int(m[5:7]) - 1] + " " + m[:4]
            up = sorted(ks, key=lambda o: -o["ks"]["df"])[:5]
            dn = sorted(ks, key=lambda o: o["ks"]["df"])[:5]
            L += ["", b(f"🌏 Kepemilikan asing bulan {m} (KSEI)")]
            L.append("Masuk: " + ", ".join(f"{o['ticker']} +{o['ks']['df']:.1f} poin".replace(".", ",") for o in up if o["ks"]["df"] > 0))
            L.append("Keluar: " + ", ".join(f"{o['ticker']} {o['ks']['df']:.1f} poin".replace(".", ",") for o in dn if o["ks"]["df"] < 0))
    # 📅 ex-dividen ≤ 5 hari (hanya tanggal pasti)
    soon = []
    for o in rows:
        dv = o.get("dv") or {}
        if not dv.get("sure"):
            continue
        dd = (_date.fromisoformat(dv["ex"]) - today).days
        st = (o.get("m") or {}).get("dividend") or {}
        if 1 <= dd <= 5 and (layak(o, "dividend") or st.get("s") in ("buy", "hold")):
            soon.append((dd, o, dv))
    if soon:
        L += ["", b("📅 Ex-dividen sebentar lagi (metode Dividen)")]
        for dd, o, dv in sorted(soon, key=lambda x: x[0])[:6]:
            ex = _date.fromisoformat(dv["ex"])
            cum = ex - _td(days=1)
            while cum.weekday() >= 5:
                cum -= _td(days=1)
            L.append(f"{b(o['ticker'])} ex {hari(dv['ex'])} · ±{usd(dv['amt'])}/lembar ({str(dv.get('y', 0)).replace('.', ',')}%) · beli paling lambat {hari(cum.isoformat())}")
    return L

def morning(d: dict) -> str | None:
    if d.get("newSession") is False:
        print("Tidak ada sesi bursa baru sejak pembaruan sebelumnya (libur BEI); pesan tidak dikirim.")
        return None
    day = d["priceDate"]
    buys, sells, holds, first = signals(d)
    L = [f"🇮🇩 {b('Screener Saham Indonesia — ' + hari(day))}",
         f"🟢 Sinyal beli baru: {len(buys)} · 🔴 Sinyal jual (bagi pemegang): {len(sells)}"]
    mk = d.get("market") or {}
    if mk.get("ok") is not None:
        L.append("IHSG: " + ("naik ✅" if mk["ok"] else "tertekan ⚠️ (CAN SLIM tidak membeli)"))
    pool = [o for o in d.get("stocks", []) if o.get("liq", "L") == "L"]
    nl = sum(1 for o in pool if any(layak(o, m) for m in ORDER))
    L.append(f"📋 Masih layak beli (sinyal lama + baru): {nl} saham — lihat website")
    if buys:
        L += ["", b(f"Beli ({min(len(buys), TOP)} teratas)")]
        for o, mid, st, _ in buys[:TOP]:
            L.append(f"{b(o['ticker'])} {usd(st.get('bp'))} · {plan_text(mid, st)}")
            L.append(f"<i>{e(NAMES[mid])}: {e(st.get('rs'))}</i>")
        if len(buys) > TOP:
            L.append(f"…dan {len(buys) - TOP} lainnya di website")
    if sells:
        L += ["", b(f"Jual ({min(len(sells), TOP)} teratas)")]
        for o, mid, st, _ in sells[:TOP]:
            L.append(f"{b(o['ticker'])} {usd(st.get('sp'))} · <i>{e(NAMES[mid])}: {e(st.get('rs'))}</i>")
        if len(sells) > TOP:
            L.append(f"…dan {len(sells) - TOP} lainnya di website")
    if not buys and not sells:
        L += ["", "Tidak ada sinyal beli atau jual baru hari ini."]
    try:
        L += support_section(d)
        L += extras_section(d)
        L += track_section(d)
    except Exception as ex:
        print(f"Bagian area support dilewati: {ex}")
    L += ["", "Hanya saham likuid (transaksi ≥ Rp5 miliar/hari). Harga sudah dibulatkan ke fraksi BEI.",
          f'🔗 <a href="{SITE}">Detail dan alasan lengkap di website</a>']
    return "\n".join(L)


def reminder(d: dict, now: datetime | None = None) -> str | None:
    now = (now or datetime.now(WIB)).astimezone(WIB)
    today = now.date()
    if today.weekday() >= 5 or today.isoformat() in HOLIDAYS:
        print(f"BEI tutup hari ini ({today}); pengingat tidak dikirim.")
        return None
    pd_ = d.get("priceDate")
    if not pd_ or (today - date.fromisoformat(pd_)).days > 5:
        print("Data belum diperbarui; pengingat tidak dikirim.")
        return None
    buys, _, _, _ = signals(d)
    if not buys:
        print("Tidak ada sinyal beli baru; pengingat tidak dikirim.")
        return None
    L = [f"⏰ 🇮🇩 {b('BEI buka 09.00 WIB')} (pra-pembukaan 08.45)",
         f"Order dari sinyal {hari(pd_)} (harga beli = harga penutupan, 1 lot = 100 lembar):", ""]
    for o, mid, st, _ in buys[:8]:
        L.append(f"{b(o['ticker'])} beli sekitar {usd(st.get('bp'))} · {plan_text(mid, st)} ({NAMES[mid]})")
    if len(buys) > 8:
        L.append(f"…dan {len(buys) - 8} lainnya di website")
    L += ["", "Pasang stop loss dan target sebagai order otomatis bila aplikasi broker Anda mendukung."]
    return "\n".join(L)


def weekly(now: datetime | None = None) -> str | None:
    """Kalender siklus mingguan (Senin pagi) dari data/cycles.json."""
    f = ROOT / "data" / "cycles.json"
    if not f.exists():
        print("cycles.json belum ada; kalender mingguan tidak dikirim.")
        return None
    c = json.loads(f.read_text())
    today = (now or datetime.now(WIB)).astimezone(WIB).date()
    end = today + timedelta(days=6)
    n0 = lambda v: f"{v:,.0f}".replace(",", ".") if isinstance(v, (int, float)) else "–"
    L = [f"🗓 🇮🇩 {b('Kalender siklus ' + hari(today.isoformat()).split(' ', 1)[1] + ' – ' + hari(end.isoformat()).split(' ', 1)[1])}"]
    for name, a in (c.get("indices") or {}).items():
        rg = a.get("range") or {}
        L += ["", f"{b(name)} {n0(a.get('price'))}"]
        if rg.get("r68"):
            L.append(f"Rentang minggu ini (peluang 68%): {n0(rg['r68'][0])} – {n0(rg['r68'][1])}")
        sup, res = (a.get("sup") or [])[:1], (a.get("res") or [])[:1]
        if sup:
            L.append(f"Support: {n0(sup[0]['lo'])}–{n0(sup[0]['hi'])} ({sup[0]['strength']})")
        if res:
            L.append(f"Resistance: {n0(res[0]['lo'])}–{n0(res[0]['hi'])} ({res[0]['strength']})")
        raw = [x for x in a.get("rawan") or [] if today.isoformat() <= x["d"] <= end.isoformat()]
        for x in raw:
            L.append(f"⚠️ Tanggal rawan {hari(x['d'])}: {e(', '.join(x['why'][:3]))}")
        evs = [x for x in a.get("events") or [] if today.isoformat() <= x["d"] <= end.isoformat() and x["type"] in ("bulan", "planet")]
        if evs and name == next(iter(c["indices"])):
            L.append("Peristiwa: " + " · ".join(f"{e(x['what'])} {hari(x['d']).split(' ', 1)[1]}" for x in evs))
        t = (c.get("tests") or {}).get(name) or {}
        if t.get("time"):
            good = [k for sec in ("time", "price") for k, v in (t.get(sec) or {}).items() if v and v.get("verdict") == "berguna"]
            L.append("Uji riwayat: " + (f"terbukti berguna: {', '.join(good)}" if good else "belum ada unsur waktu atau Fibonacci yang lebih baik dari acak"))
        sc = ((c.get("score") or {}).get(name) or {}).get("dates") or {}
        if sc.get("n"):
            L.append(f"Papan skor: {sc['hit']} dari {sc['n']} tanggal rawan tepat (acak ±{sc.get('base')}%)")
    br = c.get("breadth") or {}
    if br.get("above200") is not None:
        L += ["", f"Kesehatan pasar: {str(br['above200']).replace('.', ',')}% saham di atas SMA200 "
                  + ("(mayoritas tren naik)" if br["above200"] >= 50 else "(mayoritas tren turun)")]
        try:
            mk = (json.loads((ROOT / "data" / "stocks.json").read_text()).get("market") or {}).get("ok")
        except Exception:
            mk = None
        b200 = br["above200"]
        if b200 >= 60 and mk is not False:
            L.append("💡 Saran: pasar sehat. Semua metode boleh dipakai; utamakan saham yang lolos di lebih dari satu metode.")
        elif b200 < 40 or (mk is False and b200 < 50):
            L.append("💡 Saran: pasar tertekan. Kurangi pembelian baru, beli bertahap, utamakan Dividen/Value/Quality, hindari CAN SLIM, Momentum, dan Swing.")
        else:
            L.append("💡 Saran: pasar campuran. Selektif, utamakan sinyal Beli di ≥ 2 metode, ukuran posisi lebih kecil.")
    L += ["", "Siklus waktu adalah alat bantu, bukan kepastian. Cek hasil uji di website.",
          f'🔗 <a href="{SITE}#cycles">Grafik dan kalender lengkap</a>']
    return "\n".join(L)


def failed_message() -> str:
    run = "{}/{}/actions/runs/{}".format(os.environ.get("GITHUB_SERVER_URL", "https://github.com"),
                                         os.environ.get("GITHUB_REPOSITORY", "sultanamra3-arch/screener-saham"),
                                         os.environ.get("GITHUB_RUN_ID", ""))
    return ("⚠️ 🇮🇩 " + b("Screener Saham Indonesia: pembaruan data gagal") + "\n"
            "Website masih menampilkan data sebelumnya.\n"
            f'<a href="{run}">Lihat penyebabnya di GitHub</a>')


def split(msg: str, limit: int = 3900) -> list[str]:
    parts, cur = [], ""
    for line in msg.split("\n"):
        if len(cur) + len(line) + 1 > limit and cur:
            parts.append(cur)
            cur = ""
        cur = (cur + "\n" + line) if cur else line
    if cur:
        parts.append(cur)
    return parts


def send(msg: str):
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat:
        print("TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID belum diisi; pesan tidak dikirim.\n")
        print(msg)
        return
    for part in split(msg):
        r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                          json={"chat_id": chat, "text": part, "parse_mode": "HTML", "disable_web_page_preview": True},
                          timeout=30)
        if r.status_code != 200:
            try:
                desc = r.json().get("description", "")
            except Exception:
                desc = r.text[:200]
            sys.exit(f"Telegram menolak pesan (HTTP {r.status_code}): {desc}. Cek TELEGRAM_BOT_TOKEN dan "
                     "TELEGRAM_CHAT_ID, dan pastikan Anda sudah menekan Start di bot.")
    print(f"Terkirim ke Telegram ({len(split(msg))} pesan)")



def midday(d: dict) -> str | None:
    """Pesan siang: hanya bila ada saham layak beli yang baru masuk area support, atau support jebol."""
    it = d.get("intraday") or {}
    if not it or it.get("date") != datetime.now(WIB).date().isoformat():
        return None
    L = support_section(d, show_waits=False)
    if not L:
        print("Update siang: tidak ada hal penting, pesan tidak dikirim.")
        return None
    head = [f"⏱️ {b('Update siang — harga sementara sesi 1 (' + it.get('wib', '') + ' WIB)')}",
            "Untuk dipertimbangkan di sesi 2. Sinyal metode tetap final setelah bursa tutup."]
    return "\n".join(head + L + ["", f"🔗 <a href=\"{SITE}\">Buka website</a>"])

def main():
    if "--failed" in sys.argv:
        msg = failed_message()
    else:
        d = json.loads(DATA_FILE.read_text())
        msg = weekly() if "--weekly" in sys.argv else reminder(d) if "--reminder" in sys.argv else midday(d) if os.environ.get("INTRADAY") == "1" else morning(d)
    if not msg:
        return
    if "--dry-run" in sys.argv:
        print(msg)
    else:
        send(msg)


if __name__ == "__main__":
    main()
