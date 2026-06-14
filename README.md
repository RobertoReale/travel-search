# travel-search — verified, bookable accommodation prices

Post-processing tools for a budget-travel pipeline: cheap flights via
[`fli`](https://github.com/punitarani/fli), accommodation via [`trvl`](https://github.com/MikkoParkkola/trvl), orchestrated
by an AI agent. The free `trvl`/Google Hotels feed shows **teaser** prices that
collapse at checkout (a real case: an Ischia hotel listed at €46/night was €269
when you actually tried to book). This repo fixes that.

It backs a three-part write-up:
- Part 1 — [*Building a budget-travel pipeline*](https://blog-roberto-reale.vercel.app/article/building-a-budget-travel-pipeline)
- Part 2 — [*A budget-travel pipeline, applied*](https://blog-roberto-reale.vercel.app/article/budget-travel-pipeline-applied)
- Part 3 — [*After the articles: an open source arc, two fixes, and the updated setup guide*](https://blog-roberto-reale.vercel.app/article/budget-travel-pipeline-fixed) ← **use the prompt from here**

> 💡 New here? Open [`prompt-builder.html`](prompt-builder.html) in your browser — a no-code form
> that writes the agent prompt for you. See [Prompt builder (GUI)](#prompt-builder-gui).

## What `serpapi_verified.py` does

`trvl serpapi` returns a verified per-night price but strips the `property_token`,
so it cannot build per-provider booking links. This script calls SerpAPI's Google
Hotels engine directly — one list call, then one detail call per top property — to
reach the levels the teaser can't:

1. **Verified read** — the real per-night *and* total price for the exact dates.
2. **Deep-link hand-off** — a per-provider booking link for that hotel + dates.

On top of that:

- **Tax-aware ranking.** Every provider is ranked on `total_rate` (the
  **tax-inclusive** total), never the per-night teaser. `tax_status()` cross-checks
  the total against the pre-tax figure and flags providers whose headline *excludes*
  taxes (they grow them at checkout: `⚠ adds tax`). When the cheapest provider is
  tax-exclusive, the script steps up to the cheapest genuinely all-in provider, so
  the number you compare is a true final total. See **[Two kinds of tax](#two-kinds-of-tax)**.
- **Link hardening.** Drops `google.com/travel/clk` vacation-rental redirects (they
  404 within hours), falls back to the property's official site, and always emits a
  durable Booking.com search deep-link (the **Stable** column) because `aclk`
  ad-click links can expire after a day or two. `--check-links` HTTP-validates them.
- **Robustness.** On-disk response cache (re-runs cost **zero** quota), retry with
  exponential backoff, and a clean exit on a SerpAPI error payload instead of a
  traceback.

## Requirements

- Python 3.9+ (standard library only — no third-party deps to run the script)
- A free SerpAPI key (250 searches/month, no card): https://serpapi.com
- `pytest` only if you want to run the tests

## Usage

```bash
# PowerShell
$env:SERPAPI_KEY="your_key_here"
# bash
export SERPAPI_KEY=your_key_here

python serpapi_verified.py "Ischia" 2026-07-30 2026-08-04 --adults 2 --top 8
python serpapi_verified.py "Barceloneta, Barcelona" 2026-08-01 2026-08-06 --check-links
python serpapi_verified.py "Ischia" 2026-07-30 2026-08-04 --providers "Booking.com,Expedia.com"
```

Output: a JSON file plus a human-readable Markdown table in `results/`, and a
console summary. Sample outputs are committed there.

### Useful flags

| Flag | Effect |
|---|---|
| `--top N` | how many cheapest properties to deep-resolve (default 8) |
| `--adults N` | occupancy (default 2) |
| `--max-night X` | drop properties above this verified per-night price |
| `--providers "A,B"` | whitelist specific OTAs |
| `--check-links` | HEAD-validate each booking link and drop dead ones |
| `--no-cache` | bypass the on-disk cache and force fresh calls |
| `--gl CC` | SerpAPI country code for localised pricing (default `us`; use `it` for Italy, `es` for Spain, etc.) |

## Two kinds of tax

These are different things and only the first affects comparability:

1. **OTA taxes & fees (VAT, service).** Some providers fold them into the headline
   price; others show a lower number and add them at checkout. The script handles
   this by ranking on `total_rate` and flagging/stepping past tax-exclusive
   providers — so every number you compare is already a final total.
2. **Tourist tax.** A flat local levy paid **in cash at the
   property**, that **no** online total includes, for **any** provider. It's the
   same for every provider at a given hotel, so it does **not** change the ranking.
   The script deliberately does **not** estimate it — rates vary by municipality and
   star class, so any single guessed number would be misleading. Confirm the exact
   rate locally and budget for it as a separate cash cost.

## Other files

- `run_experiment.py` — sweeps the Milan airports × candidate destinations through
  `fli` to produce the flight shortlist that feeds the accommodation search.
- `test_serpapi_verified.py` — unit tests for the pure parsing/ranking/tax/link
  helpers (no network): `python -m pytest test_serpapi_verified.py -q`.
- `.mcp.json` — the local MCP wiring for `fli` and `trvl`.

## Note on keys

The SerpAPI key is read from the `SERPAPI_KEY` environment variable only. It is
never written to disk, and the response cache key is computed with the api_key
field removed, so cached files contain no secret.

## Full AI Budget Travel Pipeline

This is the complete, runnable build behind the blog write-up: `fli` for flights, `trvl`
for accommodation, `serpapi_verified.py` for per-provider verified prices and booking deeplinks,
and an AI agent tying them together. A no-code **[prompt builder](#prompt-builder-gui)** is included to fill
in the template below.

### Prompt builder (GUI)

Hand-editing the bracketed template is error-prone. [`prompt-builder.html`](prompt-builder.html)
is a single self-contained page — **no install, no server, no dependencies**: open it in any
browser (double-click the file) and it gives you a form for every configurable field.

- Trip basics (airports, date window, stay length, travellers) and all optional filters —
  flights, accommodation, perks, rentals, verification — exactly as in the prompt template.
- Add/remove destination rows; pick dates with a calendar (auto-formatted into the prompt).
- The full prompt regenerates live on the right with a one-click **Copy** button; empty
  optional filters are omitted automatically.
- Enter your SerpAPI key to get the ready-to-paste `SERPAPI_KEY` export command (PowerShell
  and bash). The key is **never** written into the prompt — only into the env-var command —
  and is kept solely in your browser's local storage.
- Inputs persist between sessions; **Load example** fills the worked Milan-summer trip.

Copy the generated prompt, paste it into your agent running in the project folder, and run.

### Setup

Everything runs from a single project folder. The AI agent reads MCP configuration from `.mcp.json` in the working directory and activates servers automatically. The folder looks like this:

```
~/summer-vacation/
├── .mcp.json
└── results/
```

**Prerequisites:**

```bash
python3 --version   # 3.9 or later
node --version      # 18 or later — needed for npx
go version          # any recent version — needed for trvl
```

**fli, from the fork** — I contributed `--min-duration` / `--max-duration`
([PR #195](https://github.com/punitarani/fli/pull/195)) and `--return-time`
([PR #196](https://github.com/punitarani/fli/pull/196)) to upstream; both PRs are still open, so the project installs from my fork:

```bash
pip install git+https://github.com/RobertoReale/fli.git@feature/window-duration
fli dates --help    # verify --min-duration, --max-duration, and --return-time appear
```

*Windows only:* set `PYTHONIOENCODING=utf-8` before any `fli` command, or you'll get encoding errors on destination names.

**trvl:**

```bash
go install github.com/MikkoParkkola/trvl/cmd/trvl@latest
# or download a prebuilt binary from:
# https://github.com/MikkoParkkola/trvl/releases
trvl --help         # verify the install
```

**SerpAPI key (for verified prices):** sign up at [serpapi.com](https://serpapi.com/) — the free tier gives 250 searches/month with no credit card. Set the key in the environment before launching, so both `trvl serpapi` and the post-processing script can read it:

```bash
export SERPAPI_KEY="your_key_here"     # PowerShell: $env:SERPAPI_KEY="your_key_here"
trvl serpapi "Ischia" --checkin 2026-07-30 --checkout 2026-08-04 --currency EUR --format json
```

If the prices differ sharply from the free `trvl hotels` numbers, `trvl serpapi` corrects in the right direction — but for peak-season island destinations, expect a residual gap of 10–25 % between the Google Hotels minimum and the cheapest bookable room. For per-provider totals with direct booking links, run `serpapi_verified.py` (see below). As of trvl v1.9.2, `trvl prices <google_place_id>` with SerpAPI configured returns a verified per-provider matrix. The name-based fallback (`trvl prices "Hotel Name" --location "..."`) is now safer — v1.9.2 matches the returned hotel name against the requested name and returns `providers: null` on mismatch — but for automated pipelines, `trvl prices <place_id>` remains the reliable path.

**`.mcp.json`:**

```json
{
  "mcpServers": {
    "fli": {
      "command": "fli-mcp"
    },
    "trvl": {
      "command": "trvl",
      "args": ["mcp"]
    }
  }
}
```

Launch your AI agent from inside that directory — its working directory must be the
project folder, so the MCP servers and `results/` resolve correctly:

```bash
cd ~/summer-vacation
claude
```

Verify all three servers are connected:

```
/mcp
```

`fli` and `trvl` should show as `connected`. If any show `pending`, wait a few seconds and check again.

---

### The prompt

The template below works for any departure city, destination list, and date window. Replace the bracketed values before running.

```
Budget travel pipeline

TRIP VARIABLES
- Departure airports: [e.g. BGY, MXP, LIN] (fli needs airport codes, search each as a separate roundtrip)
- Overall availability: [e.g. Jul 22 – Aug 6] (earliest you can leave – latest you must be back)
- Stay duration: [e.g. 5] nights
- Travellers / Guests: [e.g. 2] adults
- Outbound flight from home: [e.g. before 16:00]
- Return flight from destination: [e.g. after 16:00]

ADVANCED FILTERS (Optional - Remove or modify as needed)

[Flights]
- Flight Stops: [e.g. NON_STOP, ONE_STOP, or ANY]
- Flight Class: [e.g. ECONOMY, BUSINESS]
- Airlines (Include/Exclude): [e.g. Exclude FR, Include U2]
- Airline Alliances: [e.g. SKYTEAM, STAR_ALLIANCE, ONEWORLD]
- Layover limits: [e.g. max 120 minutes]

[Accommodation - General]
- Property Type: [hotel, apartment, hostel, resort, bnb, villa, or ANY]
- Room Type: [entire_home, private_room, shared_room, hotel_room, or ANY]
- Quality minimums: [e.g. 3 stars, 8.0/10 user rating]
- Max budget: [e.g. max €150/night]
- Max distance from center: [e.g. 5 km]

[Accommodation - Perks & Rules]
- Meal Plan: [e.g. breakfast included, or ANY]
- Cancellation: [e.g. free cancellation only]
- Eco-certified: [e.g. TRUE or FALSE]

[Accommodation - Rentals specific (Airbnb/Apartments)]
- Minimum layout: [e.g. 2 bedrooms, 1 bathroom]
- Superhost only: [e.g. TRUE or FALSE]

[Accommodation - Verification & Safety]
- Trusted Providers (OTA Whitelist): [e.g. "Booking.com, Expedia.com" or "ALL"]
- Verify Links: [e.g. TRUE (drop dead links)]

DESTINATIONS (sea/beach access only)
- [IATA] ([City]) — [transit note, e.g. "ferry to Ischia ~1 hr"]
- [IATA] ([City]) — [access note]
...

Step 1 — Flights (fli MCP server)
Using the TRIP VARIABLES and ADVANCED FILTERS above:
- Search each Departure airport as a separate roundtrip using the search_dates tool.
- Calculate the outbound search window: start date = start of Overall availability. end date = end of Overall availability MINUS Stay duration. (e.g. If availability ends Aug 6 and stay is 5 nights, your end date is Aug 1).
- Map Stay duration, Travellers, and time preferences to the tool's arguments.
- Apply all specified [Flights] filters (Stops, Class, Airlines, Alliances, Layover) to the tool.
- Multiply the single adult fare by Travellers for the trip total.
Sort by cheapest roundtrip. Save all results to results/flights.md.

Step 2 — Accommodation (trvl MCP server, run searches in parallel)
For the top [e.g. 5] flight options, search accommodation at the actual destination (not the gateway airport city, if different):
- Guests: use Travellers variable.
- Dates: check-in = outbound flight date, check-out = return flight date.
- Filters: apply all [Accommodation] preferences (General, Perks, Rentals) to your search natively where the tool supports them.
- Budget: apply the Accommodation max budget to the verified total ÷ nights (if no budget is set, rank purely by total trip cost).

Use trvl serpapi (not trvl hotels) — the free trvl hotels prices are Google Hotels teasers,
not bookable rates. trvl serpapi routes through SerpAPI and returns verified prices
(price_confidence: verified). Rank on the SerpAPI-verified total, never the teaser.
If a Google place ID is available for a shortlisted hotel (visible in trvl hotels --format json),
use trvl prices <place_id> to get the per-provider matrix and OTA links.
Apply the "Trusted Providers" whitelist (if not ALL) and the "Verify Links" flag.
For each kept hotel, record the verified total (taxes incl.) and a working
per-provider booking link. Hotels returning providers: null need post-processing
with serpapi_verified.py for reliable booking deeplinks.

Save raw results per date window to results/hotels_[dates].json.

Step 3 — Evaluate

a) Anomalies: flag any result that bypassed the filters (e.g. a B&B appearing
   under a hotel/3-star filter, or a 0-star property passing a star minimum).
   Keep in the JSON for reference; exclude from the final ranking.

b) Price & tax: rank on the verified TOTAL (taxes included), never the per-night
   teaser. Prefer the all-in provider (Booking.com quotes taxes in; some others
   add them at checkout — flag those). Any local tourist tax (e.g. city tax) is paid in cash at the property, is in no online total, and is the
   same for every provider — note it as a separate cash cost, but do not estimate a
   figure or fold it into the ranking. Discard any hotel whose only links are
   vacation-rental redirects (google.com/travel/clk) that 404 — keep working OTA links.

c) Verify: web-search each candidate. Confirm it is currently operating. Collect
   review highlights — cleanliness, noise levels, distance from sea, recurring
   complaints.

d) Location: for each hotel, note which part of the destination it is in, distance
   to the nearest beach, and distance to the ferry port or airport. Assess
   whether the position suits a sea-access trip.

Step 4 — Final output

Rank all combinations by total trip cost (flight + verified accommodation total).
Exclude any option with a critical red flag. Present the top [N_FINAL] valid
options only — do not include filtered-out results in the final report.

For each valid option include:
- Total cost (flight + verified hotel total, itemised; note any property-collected
  tourist tax separately as a cash cost, without inventing a figure)
- Hotel: rating, review count, star category, key amenities
- Location: neighbourhood · minutes to nearest beach · minutes to ferry/transit
- Agent verdict (one sentence)
- Google Flights link for the flight
- Working per-provider hotel booking link (an OTA link that lands on the rate —
  not a generic search page, not a vacation-rental redirect)

Export to results/final-results.md.
```
