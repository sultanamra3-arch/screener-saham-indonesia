"""Pemeriksaan halaman depan chartflow.my.id sebelum dikirim ke hosting.

Gagal (exit 1) bila halaman depan masih menyebut fitur yang sudah dihapus, belum menyebut fitur yang aktif,
memakai gambar yang tidak ada, atau changes.json rusak. Daftar fitur: chartflow/features.json.
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PUB = ROOT / "chartflow" / "public"
html = (PUB / "index.html").read_text(encoding="utf-8")
feat = json.loads((ROOT / "chartflow" / "features.json").read_text(encoding="utf-8"))
err = []
for f in feat["active"]:
    miss = [m for m in f["mention"] if m not in html]
    if miss:
        err.append(f"Fitur aktif belum disebut: {f['name']} ({', '.join(miss)})")
for f in feat["removed"]:
    hit = [m for m in f["forbid"] if m in html]
    if hit:
        err.append(f"Fitur yang sudah dihapus masih disebut: {f['name']} ({', '.join(hit)})")
for img in sorted(set(re.findall(r'src="(/img/[^"]+)"', html))):
    if not (PUB / img.lstrip("/")).exists():
        err.append(f"Gambar tidak ada: {img}")
try:
    ch = json.loads((PUB / "changes.json").read_text(encoding="utf-8"))
    assert isinstance(ch, list) and ch and all({"d", "t", "x"} <= set(x) for x in ch)
    if [x["d"] for x in ch] != sorted((x["d"] for x in ch), reverse=True):
        err.append("changes.json harus urut dari yang terbaru")
except Exception as e:
    err.append(f"changes.json rusak: {e}")
if err:
    print("Halaman depan ChartFlow belum sesuai fitur terbaru:\n- " + "\n- ".join(err))
    sys.exit(1)
print(f"Halaman depan ChartFlow sesuai: {len(feat['active'])} fitur aktif disebut, {len(feat['removed'])} fitur lama tidak ada.")
