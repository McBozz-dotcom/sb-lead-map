#!/usr/bin/env python3
"""Collect local-business leads for Santa Barbara, Goleta and Carpinteria.

    python collect.py                 # ~100 businesses (default preview size)
    python collect.py --limit 0       # everything OSM has in the area
    python collect.py --help          # all options

Writes data/businesses.json (read by the map) and data/businesses.csv.
"""
import argparse
import csv
import datetime
import json
import os
import sys
from collections import defaultdict

from leadmap import ca_sos, estimates, google_places, manual, net, overpass, scoring, website_check
from leadmap.categories import CATEGORIES

DATA = os.path.join(net.ROOT, "data")
CACHE = os.path.join(DATA, "cache")


def read_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def write_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=1, ensure_ascii=False)
    os.replace(tmp, path)


def pick_sample(businesses, limit):
    """Round-robin across categories so a small sample still shows every business type.
    Within a category, independents with a phone number come first."""
    if not limit or limit >= len(businesses):
        return businesses
    by_cat = defaultdict(list)
    for b in sorted(businesses, key=lambda b: (b["chain"], not b.get("phone"), b["name"].lower())):
        by_cat[b["category"]].append(b)
    out, i = [], 0
    while len(out) < limit and any(i < len(v) for v in by_cat.values()):
        for cat in CATEGORIES:
            if i < len(by_cat[cat]) and len(out) < limit:
                out.append(by_cat[cat][i])
        i += 1
    return out


def write_csv(path, businesses):
    cols = ["name", "category_label", "subtype", "city", "address", "phone", "website", "website_rating",
            "website_issues", "lead_score", "owner_name", "year_founded", "employees", "revenue_low",
            "revenue_high", "lat", "lon", "id", "sources"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for b in businesses:
            wc = b.get("website_check", {})
            row = dict(b, website_rating=wc.get("rating"), website_issues="; ".join(wc.get("issues", [])),
                       sources="; ".join(f"{k}: {v['source']} [{v['status']}]" for k, v in b["provenance"].items()))
            w.writerow(["" if row.get(c) is None else row.get(c) for c in cols])


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--limit", type=int, default=100, help="max businesses to keep (0 = all). Default 100")
    ap.add_argument("--include-chains", action="store_true", help="keep branded chains (excluded by default)")
    ap.add_argument("--from-file", metavar="JSON", help="use a saved Overpass JSON export instead of querying")
    ap.add_argument("--refresh", action="store_true", help="re-query OpenStreetMap instead of using the cache")
    ap.add_argument("--no-website-check", action="store_true", help="skip grading websites")
    ap.add_argument("--no-google", action="store_true", help="skip Google Places even if a key is set")
    ap.add_argument("--no-sos", action="store_true", help="skip CA Secretary of State even if a key is set")
    ap.add_argument("--debug-sos", action="store_true", help="print raw CA SOS API responses")
    args = ap.parse_args()

    net.load_env()
    today = datetime.date.today().isoformat()
    sources_used = []

    # 1. Discover businesses (OpenStreetMap). Cached so re-runs don't hammer the public server.
    raw_cache = os.path.join(CACHE, "osm_businesses.json")
    cached = read_json(raw_cache, None)
    if args.from_file:
        businesses = overpass.collect(today, args.from_file)
    elif cached and not args.refresh:
        print(f"[overpass] using cache from {cached['retrieved']} (pass --refresh to re-query)")
        businesses = cached["businesses"]
    else:
        try:
            businesses = overpass.collect(today)
        except Exception as e:
            sys.exit(f"Could not reach the Overpass API: {e}\n"
                     "Try again in a minute, or set OVERPASS_URL in .env to a mirror such as "
                     "https://overpass.kumi.systems/api/interpreter")
        write_json(raw_cache, {"retrieved": today, "businesses": businesses})
    sources_used.append("OpenStreetMap via Overpass API (ODbL)")

    if not args.include_chains:
        before = len(businesses)
        businesses = [b for b in businesses if not b["chain"]]
        print(f"[filter] dropped {before - len(businesses)} chain locations (use --include-chains to keep)")
    businesses = pick_sample(businesses, args.limit)
    print(f"[sample] keeping {len(businesses)} businesses")

    # 2. Optional enrichment from keyed APIs.
    if google_places.enabled() and not args.no_google:
        sources_used.append("Google Places API")
        hits = 0
        for i, b in enumerate(businesses, 1):
            try:
                hits += google_places.enrich(b, today)
            except Exception as e:
                print(f"[google] stopping: {e}")
                break
            print(f"\r[google] {i}/{len(businesses)} matched {hits}", end="", flush=True)
        print()
        businesses = [b for b in businesses if b.get("business_status") != "CLOSED_PERMANENTLY"]
    else:
        print("[google] GOOGLE_PLACES_API_KEY not set - skipping (optional)")

    if ca_sos.enabled() and not args.no_sos:
        sources_used.append("California Secretary of State business search API")
        ca_sos.DEBUG = args.debug_sos
        hits = 0
        for i, b in enumerate(businesses, 1):
            try:
                hits += ca_sos.enrich(b, today)
            except Exception as e:
                print(f"\n[ca_sos] stopping: {e}")
                break
            print(f"\r[ca_sos] {i}/{len(businesses)} matched {hits}", end="", flush=True)
        print()
    else:
        print("[ca_sos] CA_SOS_API_KEY not set - skipping owner/registration lookups (optional)")

    rows = manual.load()
    if rows:
        sources_used.append("Your manual research (data/manual_enrichment.csv)")
        n = sum(manual.apply(b, rows, today) for b in businesses)
        print(f"[manual] applied {n} rows from data/manual_enrichment.csv")

    # 3. Website grading (cached per URL for 30 days).
    web_cache_path = os.path.join(CACHE, "website_checks.json")
    web_cache = read_json(web_cache_path, {})
    if not args.no_website_check:
        for i, b in enumerate(businesses, 1):
            url = b.get("website")
            hit = web_cache.get(url) if url else None
            fresh = hit and (datetime.date.today() - datetime.date.fromisoformat(hit["checked"])).days < 30
            if fresh:
                result = hit
            else:
                result = website_check.check(url, b.get("social_url"))
                result["checked"] = today
                if url:
                    web_cache[url] = result
                    write_json(web_cache_path, web_cache)
            b["website_check"] = result
            b["provenance"]["website_check"] = {"source": "Automated homepage check" if url else "No website in any source",
                                                "status": "sourced", "retrieved": result["checked"]}
            print(f"\r[web] {i}/{len(businesses)} checked", end="", flush=True)
        print()
        sources_used.append("Automated website check (robots.txt respected)")

    # 4. Estimates and scores.
    bench = estimates.load_benchmarks()
    for b in businesses:
        estimates.estimate_revenue(b, bench)
        scoring.score(b)

    out = {
        "generated": today,
        "area": "Santa Barbara, Goleta, Carpinteria, CA",
        "sources": sources_used,
        "count": len(businesses),
        "businesses": businesses,
    }
    write_json(os.path.join(DATA, "businesses.json"), out)
    write_csv(os.path.join(DATA, "businesses.csv"), businesses)
    no_site = sum(1 for b in businesses if b.get("website_check", {}).get("rating") == "none")
    weak = sum(1 for b in businesses if b.get("website_check", {}).get("rating") == "weak")
    print(f"\nDone: {len(businesses)} businesses -> data/businesses.json  ({no_site} no website, {weak} weak website)")
    print("Next: python serve.py")


if __name__ == "__main__":
    main()
