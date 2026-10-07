"""Optional: fill missing phone/website from Google Places API (New). Needs GOOGLE_PLACES_API_KEY."""
import json
import math
import os
import re

from . import net

URL = "https://places.googleapis.com/v1/places:searchText"
FIELDS = ",".join([
    "places.id", "places.displayName", "places.formattedAddress", "places.location",
    "places.nationalPhoneNumber", "places.websiteUri", "places.businessStatus",
    "places.rating", "places.userRatingCount",
])
_limiter = net.RateLimiter(0.2)


def _dist_m(lat1, lon1, lat2, lon2):
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1) * math.cos(math.radians(lat1))
    return 6_371_000 * math.hypot(dlat, dlon)


def _norm(s):
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def enabled():
    return bool(os.environ.get("GOOGLE_PLACES_API_KEY"))


def enrich(b, retrieved):
    key = os.environ["GOOGLE_PLACES_API_KEY"]
    _limiter.wait()
    body = {
        "textQuery": f"{b['name']} {b.get('city') or 'Santa Barbara'} CA",
        "maxResultCount": 3,
        "locationBias": {"circle": {"center": {"latitude": b["lat"], "longitude": b["lon"]}, "radius": 300.0}},
    }
    status, _, _, raw, _ = net.request(URL, data=body, headers={"X-Goog-Api-Key": key, "X-Goog-FieldMask": FIELDS})
    if status >= 400:
        raise RuntimeError(f"Google Places HTTP {status}: {raw[:200]!r}")
    places = json.loads(raw).get("places", [])
    match = None
    for p in places:
        loc = p.get("location", {})
        name = p.get("displayName", {}).get("text", "")
        close = _dist_m(b["lat"], b["lon"], loc.get("latitude", 0), loc.get("longitude", 0)) < 250
        same = _norm(name).startswith(_norm(b["name"])[:8]) or _norm(b["name"]).startswith(_norm(name)[:8])
        if close and same:
            match = p
            break
    if not match:
        return False
    src = f"Google Places ({match['id']})"
    prov = b["provenance"]
    for field, gkey in (("phone", "nationalPhoneNumber"), ("website", "websiteUri"), ("address", "formattedAddress")):
        if not b.get(field) and match.get(gkey):
            b[field] = match[gkey]
            prov[field] = {"source": src, "status": "sourced", "retrieved": retrieved}
    b["google_rating"] = match.get("rating")
    b["google_reviews"] = match.get("userRatingCount")
    b["business_status"] = match.get("businessStatus")
    if b["google_rating"] is not None:
        prov["google_rating"] = {"source": src, "status": "sourced", "retrieved": retrieved}
    return True
