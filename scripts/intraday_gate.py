"""Gerbang update harga 30 menit: jalan hanya saat sesi BEI berlangsung.

Saat istirahat siang hanya jalan sekali (untuk ringkasan siang). Mencetak SKIP=0/1 untuk GITHUB_ENV.
"""
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))


def main():
    if os.environ.get("GITHUB_EVENT_NAME") == "workflow_dispatch":
        return "0"
    now = datetime.now(ZoneInfo("Asia/Jakarta"))
    try:
        import notify_telegram
        hol = notify_telegram.HOLIDAYS
    except Exception:
        hol = set()
    day, wd, hm = now.date().isoformat(), now.weekday(), now.hour * 60 + now.minute
    if wd >= 5 or day in hol:
        return "1"
    s1_end = 11 * 60 + 30 if wd == 4 else 12 * 60
    s2_start = 14 * 60 if wd == 4 else 13 * 60 + 30
    try:
        note = json.loads((ROOT / "data" / "intraday_note.json").read_text())
    except Exception:
        note = {}
    if 9 * 60 + 10 <= hm < s1_end + 5:
        return "0"
    if s1_end + 5 <= hm < s2_start + 10:  # istirahat: sekali saja untuk ringkasan siang
        return "1" if note.get("midday") == day else "0"
    if s2_start + 10 <= hm <= 16 * 60 + 20:
        return "0"
    return "1"


if __name__ == "__main__":
    print("SKIP=" + main())
