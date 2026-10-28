"""Cek sekali: apakah data laporan keuangan Yahoo cukup untuk Piotroski F-Score (ID dan US)."""
import json, sys, time
import yfinance as yf

ROWS = {
    "ni": ["Net Income", "Net Income Common Stockholders"],
    "rev": ["Total Revenue", "Operating Revenue"],
    "gp": ["Gross Profit"],
    "ta": ["Total Assets"],
    "ltd": ["Long Term Debt", "Long Term Debt And Capital Lease Obligation"],
    "ca": ["Current Assets"],
    "cl": ["Current Liabilities"],
    "sh": ["Ordinary Shares Number", "Share Issued"],
    "cfo": ["Operating Cash Flow", "Cash Flow From Continuing Operating Activities"],
}
TESTS = {1: ["ni", "ta"], 2: ["cfo"], 3: ["ni", "ta"], 4: ["cfo", "ni"], 5: ["ltd", "ta"], 6: ["ca", "cl"], 7: ["sh"], 8: ["gp", "rev"], 9: ["rev", "ta"]}
NEED2 = {3, 5, 6, 7, 8, 9}  # butuh 2 tahun


def get(df, names, k):
    for n in names:
        if df is not None and n in df.index:
            v = df.loc[n].dropna()
            if len(v) > k:
                return float(v.iloc[k])
    return None


def probe(sym):
    tk = yf.Ticker(sym)
    try:
        fin, bs, cf = tk.financials, tk.balance_sheet, tk.cashflow
    except Exception as e:
        return {"err": str(e)[:80]}
    src = {"ni": fin, "rev": fin, "gp": fin, "ta": bs, "ltd": bs, "ca": bs, "cl": bs, "sh": bs, "cfo": cf}
    have = {f: [get(src[f], ROWS[f], k) is not None for k in (0, 1)] for f in ROWS}
    ok = [t for t, fs in TESTS.items() if all(have[f][0] and (t not in NEED2 or have[f][1]) for f in fs)]
    yrs = 0 if fin is None else len(fin.columns)
    return {"ok": ok, "n": len(ok), "yrs": yrs, "date": str(fin.columns[0].date()) if yrs else None}


def main(out):
    id_ = json.load(open("data/stocks.json"))["stocks"]
    us = json.load(open("us_stocks.json"))["stocks"]
    ids = [(o["ticker"], o["ticker"] + ".JK", o.get("sector") or "") for o in id_ if o.get("liq") == "L"]
    uss = [(o["ticker"], o["ticker"].replace(".", "-"), o.get("sector") or "") for o in us][:150]
    res = {"id": {}, "us": {}}
    for mk, lst in (("id", ids), ("us", uss)):
        for i, (t, sym, sec) in enumerate(lst):
            r = probe(sym); r["sec"] = sec
            res[mk][t] = r
            if i % 25 == 0:
                print(mk, i, len(lst), flush=True)
            time.sleep(0.3)
    summ = {}
    for mk in res:
        R = [r for r in res[mk].values() if "n" in r]
        bank = [r for r in R if "Financial" in r["sec"]]
        non = [r for r in R if "Financial" not in r["sec"]]
        summ[mk] = {"total": len(res[mk]), "ada_data": len(R), "semua9": sum(r["n"] == 9 for r in R), "min7": sum(r["n"] >= 7 for r in R),
                    "non_keuangan": len(non), "non_semua9": sum(r["n"] == 9 for r in non), "non_min7": sum(r["n"] >= 7 for r in non),
                    "keuangan": len(bank), "keu_min7": sum(r["n"] >= 7 for r in bank),
                    "per_tes": {t: sum(t in r["ok"] for r in R) for t in range(1, 10)},
                    "tahun_laporan_median": sorted(r["yrs"] for r in R)[len(R) // 2] if R else 0}
    json.dump({"summary": summ, "detail": res}, open(out, "w"), indent=1)
    print(json.dumps(summ, indent=1))


main(sys.argv[1])
