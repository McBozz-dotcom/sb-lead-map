# SB Lead Map

A GTA-style lead map of local small businesses in **Santa Barbara, Goleta and Carpinteria**, built for finding web-design and marketing clients. It's dark and neon, with radar-blip icons for each business type, a HUD sidebar, a radar minimap and a "wanted level" lead score.

- Click any blip to see the business name, type, phone, owner, years in business, revenue, website and address.
- **Every field shows where it came from**: `SOURCED` (from a named source), `EST.` (estimated, with the math), `MANUAL` (you entered it) or `UNKNOWN`. Nothing is guessed.
- **No website / weak website** detection: the best leads pulse on the map.
- Filters: business type, website quality, lead status, wanted level, years in business, revenue range, plus text search.
- Mark leads **New / Contacted / Interested / Not interested** and add notes. They're saved to `data/lead_status.json`.
- **Export CSV** of whatever is currently filtered.

## Quick start (2 commands)

Needs Python 3.9+. There's nothing to `pip install`; it uses only the standard library.

```bash
python collect.py      # pulls ~100 businesses from OpenStreetMap and grades their websites (~2 min)
python serve.py        # opens http://127.0.0.1:8000/web/
```

When you're happy with the preview, scale up:

```bash
python collect.py --refresh --limit 0     # every business OSM has in the area (likely 1,000+)
```

Other options: `python collect.py --help` (`--include-chains`, `--no-website-check`, `--from-file`, …).
Run the tests with `python -m unittest discover -s tests`.

## Data sources: what's free, what's paid

| Source | Gives you | Key? | Cost |
|---|---|---|---|
| **OpenStreetMap via Overpass API** (default) | name, type, location, address, phone, website, sometimes opening hours / founding year (`start_date`) | none | **Free** (ODbL; please don't hammer it, since results are cached in `data/cache/`) |
| **Website check** (built in) | no site / social-only / free builder / no HTTPS / not mobile-friendly / outdated © / slow / down | none | Free. Honors `robots.txt`, fetches only the homepage, 1 request/sec |
| **Google Places API (New)**, optional | fills missing phone/website/address, Google rating + review count, drops permanently closed places | `GOOGLE_PLACES_API_KEY` | **Paid** pay-as-you-go with a monthly free allowance; needs a billing account. Phone/website fields are a higher-priced tier, so check the [pricing page](https://developers.google.com/maps/billing-and-pricing/pricing) before a full run. Google's terms limit how long you can store its data, so re-pull rather than keeping it forever. |
| **CA Secretary of State API**, optional | legal entity name, registration date, registered agent (and officers if the API returns them) | `CA_SOS_API_KEY` | **Free** key from [calicodev.sos.ca.gov](https://calicodev.sos.ca.gov/) |
| **Your own research**: `data/manual_enrichment.csv` | owner name, founding year, employee count, revenue, anything else | — | Free |
| CARTO dark basemap tiles | the map background | none | Free for light, non-commercial use. See [CARTO's terms](https://carto.com/attributions). For heavy or commercial use, swap `TILE_URL` in `web/app.js` for a paid provider (Stadia, MapTiler, Mapbox). |

**Not used:**
- **Yelp Fusion** now requires a paid plan after a trial, and its terms bar storing Yelp data long-term. That conflicts with saving leads to a file.
- **Scraping bizfile Online's web pages.** The official API above is the allowed route.

### Setting up keys

```bash
cp .env.example .env     # then paste keys in. .env is git-ignored.
```

1. **Google Places**: go to [console.cloud.google.com](https://console.cloud.google.com/), create a project, turn on billing, enable **Places API (New)**, then create an API key under *APIs & Services → Credentials*. Restrict the key to Places API.
2. **CA SOS**: sign up at [calicodev.sos.ca.gov](https://calicodev.sos.ca.gov/), subscribe to the public business-entity search product and copy your primary key.
   *Heads up:* this integration follows the API's published search endpoint, but it hasn't been tested against the live API: the network where it was built couldn't reach it. If lookups come back empty, run `python collect.py --debug-sos` once to see the raw responses. The field names live in `FIELD_HINTS` in `leadmap/ca_sos.py`.

## The honest part: owner, founding year, revenue

- **Owner name** is not in any free business-listing API.
  - The CA SOS covers only LLCs and corporations, and gives the *registered agent*. That's often a lawyer or filing service, so it's shown separately and **never** labeled as owner.
  - Sole proprietors and DBAs are filed with the [Santa Barbara County Clerk-Recorder](https://www.countyofsb.org/) (fictitious business names), and there's no API for that.
  - The best route: use the **Find owner** and **CA bizfile** buttons in the side panel, or just ask when you call, then add the name to `data/manual_enrichment.csv`.
- **Years in business** comes from OSM `start_date` when tagged, or from the CA SOS registration date (labeled as such, because the business may be older than its LLC). Otherwise it's `Unknown`.
- **Revenue** isn't public for private businesses. The map shows an `Est.` range **only when an employee count is known**: employees × U.S. Census revenue-per-employee for that industry (`leadmap/benchmarks.json`), ±30%. The note under the number shows the math. With no employee count, it says `Unknown`.

### Adding your own research

`data/manual_enrichment.csv` is created on first run. Add a row per business, matched by `id` (shown at the bottom of the side panel) or by exact `name`:

```csv
id,name,owner_name,year_founded,employees,revenue_usd,phone,website,source,notes
osm-node-123456,Example Taqueria,Maria Example,2009,8,,,,Called 10/7,"Wants a new site, follow up Nov"
```

Then re-run `python collect.py`, which uses the cache, so it's fast. Those fields show as `MANUAL` with your source, and an employee count unlocks a revenue estimate.

## Lead score ("wanted level", 0–5 ★)

| Signal | Stars |
|---|---|
| No website listed | +3 |
| Weak website (Facebook/Instagram page as the site, no HTTPS, not mobile-friendly, outdated ©, free builder subdomain, down, slow) | +2 |
| Independent (not a chain) | +1 |
| Phone number available | +1 |
| Fewer than 25 Google reviews (with a Google key) | +1 |
| Chain location | capped at 1 |

Chains are dropped by default (`--include-chains` keeps them).

## Files

```
collect.py              data collection CLI → data/businesses.json + data/businesses.csv
serve.py                local web server + saves lead statuses (127.0.0.1 only)
leadmap/                overpass, website_check, google_places, ca_sos, manual, estimates, scoring
web/                    the map (Leaflet 1.9.4 vendored in web/vendor, no build step)
data/                   generated data, cache, your statuses and research (git-ignored)
tests/                  unit tests (synthetic fixtures only)
```

## Tips

- Press `/` to search and `Esc` to close the panel. Double-click a business-type chip to show only that type.
- Lead statuses are saved to disk when you use `python serve.py`. If you open the page any other way, they're kept in your browser only.
- OSM coverage is good for restaurants and shops, thinner for contractors and home services, which often have no storefront. Google Places, or adding them by hand, fills that gap.
