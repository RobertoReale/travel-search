import subprocess, json, os, sys

AIRPORTS = ["BGY", "MXP", "LIN"]          # the three Milan airports, searched separately
DESTS = {
    "NAP": "Naples (Ischia/Procida)",
    "BCN": "Barcelona",
    "CFU": "Corfu",
    "BDS": "Brindisi (Salento)",
    "SPU": "Split (Croatia)",
}
FROM, TO = "2026-07-22", "2026-08-01"      # latest departure Aug 1 + 5 nights = return Aug 6
MIN_N, MAX_N = 5, 5

os.environ["PYTHONIOENCODING"] = "utf-8"
outdir = os.path.join(os.path.dirname(__file__), "results")
os.makedirs(outdir, exist_ok=True)

rows = []          # (orig, dest, price, dep, ret)
raw = {}

for dest, label in DESTS.items():
    for orig in AIRPORTS:
        cmd = ["fli", "dates", orig, dest,
               "--round", "--min-duration", str(MIN_N), "--max-duration", str(MAX_N),
               "--from", FROM, "--to", TO, "--currency", "EUR", "--sort", "--format", "json"]
        try:
            p = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            data = json.loads(p.stdout)
        except Exception as e:
            print(f"  {orig}->{dest}: ERROR {e}")
            continue
        if not data.get("success") or not data.get("dates"):
            print(f"  {orig}->{dest}: no results")
            continue
        raw[f"{orig}-{dest}"] = data["dates"]
        best = min(data["dates"], key=lambda x: x["price"])
        rows.append((orig, dest, best["price"], best["departure_date"], best["return_date"]))
        print(f"  {orig}->{dest}: EUR {best['price']:.0f}  {best['departure_date']} -> {best['return_date']}")

rows.sort(key=lambda r: r[2])
with open(os.path.join(outdir, "flights_raw.json"), "w", encoding="utf-8") as f:
    json.dump(raw, f, indent=2)

lines = ["| # | Route | Roundtrip price | Depart | Return | Nights |",
         "|---|-------|-----------------|--------|--------|--------|"]
for i, (o, d, pr, dep, ret) in enumerate(rows, 1):
    lines.append(f"| {i} | {o} -> {d} ({DESTS[d]}) | EUR {pr:.0f} | {dep} | {ret} | 5 |")
table = "\n".join(lines)
with open(os.path.join(outdir, "flights.md"), "w", encoding="utf-8") as f:
    f.write("# Flight experiment - Milan summer, 5 nights, Jul 22-Aug 1 departures\n\n" + table + "\n")
print("\n" + table)
