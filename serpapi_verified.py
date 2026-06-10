#!/usr/bin/env python
"""
Verified, bookable accommodation prices via SerpAPI (Google Hotels engine).

Implements the two levels the free `trvl hotels` teaser cannot reach, plus the
tax/link hardening discovered in testing:

  (1) Verified read    - real per-night AND total price for the exact dates.
  (2) Deep-link hand-off - per-provider booking link for that hotel+dates.
  (+) Tax-aware ranking  - always compare on total_rate (taxes incl.), expose the
                           before-tax figure, and flag providers whose shown price
                           does NOT include taxes (they add them at checkout).
  (+) Link hardening     - drop google.com/travel/clk vacation-rental redirects
                           (they 404 fast); fall back to the property's official
                           site; always emit a stable Booking.com search deep-link;
                           optionally HTTP-validate links (--check-links).
  (+) Robustness         - on-disk response cache (re-runs cost zero quota),
                           retry with exponential backoff, and a clear exit on a
                           SerpAPI error payload instead of an opaque traceback.

`trvl serpapi` already does (1) but strips the property_token, so it cannot do (2).
This script calls SerpAPI directly: one list call, then one detail call per top
property (using property_token) to pull the real per-provider booking links.

Usage:
  set SERPAPI_KEY=...   (PowerShell:  $env:SERPAPI_KEY="...")
  python serpapi_verified.py "Ischia" 2026-07-30 2026-08-04 --adults 2 --top 8
  python serpapi_verified.py "Ischia" 2026-07-30 2026-08-04 --providers "Booking.com"
  python serpapi_verified.py "Ischia" 2026-07-30 2026-08-04 --check-links --no-cache

Notes:
  - Cached responses live in ./cache (keyed by request params, never the api_key).
  - Tourist tax is collected at the property and is in NO
    online total; it is left out entirely here rather than guessed at.
"""
import argparse, hashlib, json, os, sys, urllib.request, urllib.error, urllib.parse, time
from datetime import date

BASE = "https://serpapi.com/search.json"
CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache")


def _cache_path(params):
    """Stable on-disk key for a SerpAPI request, excluding the secret api_key."""
    safe = {k: v for k, v in params.items() if k != "api_key"}
    raw = json.dumps(safe, sort_keys=True)
    return os.path.join(CACHE_DIR, hashlib.sha256(raw.encode()).hexdigest()[:16] + ".json")


def call(params, use_cache=True, retries=3):
    """One SerpAPI call, hardened: disk cache (saves quota on re-runs), retry with
    exponential backoff on transient network/HTTP errors, and a clear exit if SerpAPI
    returns an error payload. Free tier is 250 searches/month — caching matters."""
    cpath = _cache_path(params)
    if use_cache and os.path.exists(cpath):
        with open(cpath, encoding="utf-8") as f:
            return json.load(f)

    last_err = None
    for attempt in range(retries):
        try:
            url = BASE + "?" + urllib.parse.urlencode(params)
            with urllib.request.urlopen(url, timeout=120) as r:
                data = json.load(r)
            if isinstance(data, dict) and data.get("error"):
                # SerpAPI signals quota/parameter problems in-band with HTTP 200.
                raise RuntimeError(data["error"])
            os.makedirs(CACHE_DIR, exist_ok=True)
            with open(cpath, "w", encoding="utf-8") as f:
                json.dump(data, f)
            return data
        except (urllib.error.URLError, TimeoutError, RuntimeError, ValueError) as e:
            last_err = e
            if attempt < retries - 1:
                wait = 2 ** attempt  # 1s, 2s, 4s
                print(f"  SerpAPI call failed ({e}); retrying in {wait}s "
                      f"[{attempt + 1}/{retries}]", file=sys.stderr)
                time.sleep(wait)
    sys.exit(f"SerpAPI call failed after {retries} attempts: {last_err}")


def link_ok(url, timeout=8):
    """Best-effort liveness check for a booking link. Never raises — returns False on
    any error. Off by default (--check-links) because following ad-click redirects is
    slow and some providers reject HEAD from a script."""
    if not url:
        return False
    try:
        req = urllib.request.Request(url, method="HEAD",
                                     headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status < 400
    except Exception:
        return False


def rate_fields(d, key):
    """Pull shown total/per-night AND the before-tax figure for one rate block."""
    v = d.get(key) or {}
    return {
        "shown": v.get("lowest"),
        "shown_num": v.get("extracted_lowest"),
        "before_tax": v.get("before_taxes_fees"),
        "before_tax_num": v.get("extracted_before_taxes_fees"),
    }


def is_bookable_link(url):
    """True for working OTA links. Drop google.com/travel/clk vacation-rental
    redirects: they are ephemeral and 404 within hours."""
    if not url:
        return False
    return "/travel/clk" not in url


def tax_status(total_num, before_num):
    """Does the shown total already include taxes/fees, or are they added later?"""
    if total_num and before_num:
        gap = total_num - before_num
        if gap > 0.5:
            return "ok", f"taxes incl. (~EUR {gap:.0f} of total)"
        return "warn", "price EXCLUDES taxes - added at checkout"
    return "na", "tax breakdown n/a"


def nights_between(checkin, checkout):
    try:
        a = date.fromisoformat(checkin)
        b = date.fromisoformat(checkout)
        return max((b - a).days, 1)
    except ValueError:
        return 1


def booking_search_link(name, checkin, checkout, adults):
    """Stable, never-404 fallback: Booking.com search for the property+dates."""
    q = urllib.parse.urlencode({
        "ss": name or "", "checkin": checkin, "checkout": checkout,
        "group_adults": adults, "no_rooms": 1, "group_children": 0,
    })
    return "https://www.booking.com/searchresults.html?" + q


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("location")
    ap.add_argument("checkin")
    ap.add_argument("checkout")
    ap.add_argument("--adults", default="2")
    ap.add_argument("--currency", default="EUR")
    ap.add_argument("--top", type=int, default=8, help="how many cheapest properties to deep-resolve")
    ap.add_argument("--max-night", type=float, default=None, help="optional per-night budget filter (on verified total)")
    ap.add_argument("--providers", default=None,
                    help="comma-separated provider whitelist, e.g. 'Booking.com,Expedia.com'")
    ap.add_argument("--no-cache", action="store_true",
                    help="bypass the on-disk SerpAPI cache and force fresh calls")
    ap.add_argument("--check-links", action="store_true",
                    help="HTTP-validate each booking link (HEAD request) and drop dead ones; "
                         "slower, off by default")
    ap.add_argument("--gl", default="us",
                    help="SerpAPI country code for localised pricing (default: us). "
                         "Use 'it' for Italy, 'es' for Spain, etc.")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    use_cache = not args.no_cache

    key = os.environ.get("SERPAPI_KEY")
    if not key:
        sys.exit("SERPAPI_KEY not set")

    provider_whitelist = None
    if args.providers:
        provider_whitelist = {p.strip().lower() for p in args.providers.split(",") if p.strip()}

    nights = nights_between(args.checkin, args.checkout)
    common = dict(engine="google_hotels", q=args.location,
                  check_in_date=args.checkin, check_out_date=args.checkout,
                  adults=args.adults, currency=args.currency, gl=args.gl, hl="en", api_key=key)

    listing = call(common, use_cache=use_cache)
    props = listing.get("properties", [])

    def total_extract(p):
        return rate_fields(p, "total_rate")["shown_num"] or 9e18

    props = sorted(props, key=total_extract)

    results = []
    for p in props[:args.top]:
        token = p.get("property_token")
        night = rate_fields(p, "rate_per_night")
        tot = rate_fields(p, "total_rate")
        if args.max_night is not None and night["shown_num"] and night["shown_num"] > args.max_night:
            continue
        entry = {
            "name": p.get("name"),
            "stars": p.get("extracted_hotel_class"),
            "rating": p.get("overall_rating"),
            "list_per_night": night["shown"],
            "list_total": tot["shown"],
            "official_site": p.get("link"),
            "booking_search": booking_search_link(p.get("name"), args.checkin, args.checkout, args.adults),
            "providers": [],
        }
        if token:
            det = call({**common, "property_token": token}, use_cache=use_cache)
            entry["address"] = det.get("address")
            for pr in (det.get("featured_prices") or det.get("prices") or []):
                source = pr.get("source")
                if provider_whitelist and (source or "").lower() not in provider_whitelist:
                    continue
                pn = rate_fields(pr, "rate_per_night")
                pt = rate_fields(pr, "total_rate")
                link = pr.get("link")
                status, note = tax_status(pt["shown_num"], pt["before_tax_num"])
                kept = link if is_bookable_link(link) else None
                dead = False
                if kept and args.check_links and not link_ok(kept):
                    dead = True
                    kept = None
                entry["providers"].append({
                    "source": source,
                    "per_night": pn["shown"],
                    "total": pt["shown"],
                    "total_num": pt["shown_num"],
                    "total_before_tax": pt["before_tax"],
                    "tax_status": status,          # ok | warn | na
                    "tax_note": note,
                    "link": kept,
                    "link_dropped_404_risk": bool(link) and not is_bookable_link(link),
                    "link_dead": dead,             # only set when --check-links is on
                    "free_cancellation": pr.get("free_cancellation"),
                })
            time.sleep(0.3)

        # bookable = providers that kept a working link, ranked on tax-inclusive total.
        # Headline = cheapest all-in. If the cheapest is flagged as excluding taxes
        # (it will grow at checkout), step up to the cheapest provider that is already
        # all-in instead of crowning a misleading number.
        bookable = [pr for pr in entry["providers"] if pr["link"] and pr["total_num"]]
        bookable.sort(key=lambda pr: pr["total_num"])
        headline = bookable[0] if bookable else None
        if headline and headline["tax_status"] == "warn":
            all_in = [pr for pr in bookable if pr["tax_status"] != "warn"]
            if all_in:
                headline = all_in[0]

        entry["best_bookable"] = headline
        # Durable fallback. Ad-click (aclk) links are live now but expire; the Booking.com
        # search deep-link for this property+dates never 404s, so it is always exposed as a
        # stable alternative. Fallback order for the single headline link: working OTA link →
        # the property's own site (correct for vacation rentals not on an OTA) → stable Booking.
        entry["stable_link"] = entry["booking_search"]
        entry["booking_link"] = (headline["link"] if headline else None) or entry["official_site"] or entry["booking_search"]
        results.append(entry)

    out = args.out or f"results/serpapi_verified_{args.location.split(',')[0].strip().lower().replace(' ','_')}.json"
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"location": args.location, "checkin": args.checkin, "checkout": args.checkout,
                   "adults": args.adults, "currency": args.currency, "nights": nights,
                   "results": results}, f, indent=2, ensure_ascii=False)

    # human-friendly markdown with clickable booking links
    md_out = os.path.splitext(out)[0] + ".md"
    with open(md_out, "w", encoding="utf-8") as f:
        f.write(f"# Verified bookable prices — {args.location}\n\n")
        f.write(f"{args.checkin} → {args.checkout} · {args.adults} adults · {nights} nights · "
                f"prices in {args.currency}\n\n")
        f.write("Ranked on the verified total (taxes incl.). Tourist tax "
                "is collected at the property, is in no online total, and is left out here.\n\n")
        f.write("| Hotel | Class / rating | Best all-in total | Provider | Tax | Book | Stable |\n")
        f.write("|---|---|---|---|---|---|---|\n")
        for e in results:
            hl = e["best_bookable"]
            cls = (f"{e['stars']}★" if e["stars"] else "—") + (f" / {e['rating']}" if e["rating"] else "")
            if hl:
                total = hl["total"] or "—"
                src = hl["source"] or "—"
                tax = {"ok": "incl.", "warn": "⚠ adds tax", "na": "n/a"}[hl["tax_status"]]
            else:
                total, src, tax = "no OTA link", "official site", "—"
            link = e["booking_link"]
            book = f"[book]({link})" if link else "—"
            stable = f"[Booking]({e['stable_link']})" if e.get("stable_link") else "—"
            f.write(f"| {e['name']} | {cls} | {total} | {src} | {tax} | {book} | {stable} |\n")
        f.write("\n_Booking links land on the provider's page for these exact dates; the price is "
                "indicative until checkout. Vacation-rental redirect links that 404 have been dropped — "
                "those rows fall back to the property's own site._\n")
        f.write("\n_The **Stable** column is a Booking.com search deep-link for the property and dates. "
                "Use it if a **Book** ad-click link has expired (those can 404 after a day or two)._\n")
        f.write("\n_Tourist tax is paid in cash at the property, varies by "
                "municipality, and is in no online total — confirm the exact rate locally._\n")

    # console table
    print(f"\nVERIFIED PRICES - {args.location}  {args.checkin} -> {args.checkout}  "
          f"({args.adults} adults, {nights} nights)")
    print("Ranking on total_rate (taxes incl.). Tourist tax is paid at "
          "the property, is in no online total, and is left out here.\n")
    print(f"{'Hotel':32} {'list/night':>10} {'best (all-in)':>13}  provider / tax")
    print("-" * 100)
    for e in results:
        hl = e["best_bookable"]
        if hl:
            bb = hl["total"] or "-"
            src = hl["source"] or "-"
            tax = {"ok": "incl.", "warn": "ADDS TAX!", "na": "tax n/a"}[hl["tax_status"]]
        else:
            bb, src, tax = "(no OTA link)", "official site", "-"
        print(f"{(e['name'] or '')[:32]:32} {str(e['list_per_night']):>10} {str(bb):>13}  {src} / {tax}")
    print(f"\nFull JSON with booking links: {out}")


if __name__ == "__main__":
    main()
