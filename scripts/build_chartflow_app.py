"""Siapkan salinan screener untuk chartflow.my.id/app/<pasar>/ (dipakai langkah kirim FTP).

Pemakaian: python scripts/build_chartflow_app.py <id|us> <folder keluaran>
"""
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
market, out = sys.argv[1], Path(sys.argv[2])
GH = "https://sultanamra3-arch.github.io"
if out.exists():
    shutil.rmtree(out)
(out / "data").mkdir(parents=True)

s = (ROOT / "index.html").read_text(encoding="utf-8")
rep = [
    ('<link rel="manifest" href="/screener-saham/manifest.webmanifest">', '<link rel="manifest" href="/app.webmanifest">'),
    (f"{GH}/screener-saham-indonesia/", "/app/id/"),
    (f"{GH}/screener-saham/", "/app/us/"),
    ('location.replace("/screener-saham-indonesia/"+location.hash)', 'location.replace("/app/id/"+location.hash)'),
    ('<b>Screener Saham</b>', '<b>ChartFlow</b>'),
    ('<button type="button" class="iconbtn" id="theme"',
     '<a class="iconbtn" href="/api/logout.php" title="Keluar" aria-label="Keluar" style="text-decoration:none;color:inherit">🚪</a>\n      <button type="button" class="iconbtn" id="theme"'),
]
for a, b in rep:
    if a not in s:
        sys.exit(f"Pola tidak ditemukan di index.html: {a[:60]}")
    s = s.replace(a, b)
s = s.replace('localStorage.setItem("lastMarket","', 'localStorage.setItem("lastMarket","')  # tetap
(out / "index.html").write_text(s, encoding="utf-8")
shutil.copy(ROOT / "sw.js", out / "sw.js")
shutil.copytree(ROOT / "icons", out / "icons")
for f in ("stocks.json", "detail.json", "cycles.json", "series.json"):
    if (ROOT / "data" / f).exists():
        shutil.copy(ROOT / "data" / f, out / "data" / f)
print(f"Salinan {market} siap di {out}: {sum(1 for _ in out.rglob('*') if _.is_file())} file")
