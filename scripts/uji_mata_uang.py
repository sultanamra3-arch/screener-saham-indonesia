"""Uji baca-saja konversi mata uang memakai data Yahoo asli. Tidak menulis berkas apa pun."""
import sys

sys.dont_write_bytecode = True

import yfinance as yf

import fetch_data as fd

gagal = []
for code in ["AADI", "ADRO", "BYAN", "BREN", "CLAY", "BBCA", "TLKM"]:
    try:
        info = yf.Ticker(code + ".JK").info
        cur = info.get("financialCurrency")
        f = fd.fundamentals(code) or {}
        eps = (f.get("epsA") or [[None, None]])[-1]
        print(f"{code}: laporan={cur} harga={info.get('currentPrice')}")
        print(f"  mentah : bvps={info.get('bookValue')} pb={info.get('priceToBook')} fcf={info.get('freeCashflow')}")
        print(f"  hasil  : bvps={f.get('bvps')} pb={f.get('pb')} pfcf={f.get('pfcf')} eps_tahunan={eps} eps_12bln={f.get('eps')}")
        pb, pfcf = f.get("pb"), f.get("pfcf")
        if not cur or pb is None:
            gagal.append(f"{code}: mata uang atau PBV kosong")
        elif not 0.02 <= pb <= 150:
            gagal.append(f"{code}: PBV janggal {pb}")
        if pfcf is not None and pfcf > 2000:
            gagal.append(f"{code}: harga/arus kas bebas janggal {pfcf}")
    except Exception as e:
        gagal.append(f"{code}: {e}")
print("Kurs dipakai:", fd._KURS)
print("PERLU DICEK:" if gagal else "Tidak ada angka di luar batas wajar.", *gagal, sep="\n  ")
sys.exit(1 if gagal else 0)
