"""Pull businesses from OpenStreetMap via the Overpass API (free, no key)."""
import json
import os
import re
import urllib.parse

from . import net
from .categories import CATEGORIES, categorize, pretty

# south, west, north, east — covers Goleta/Isla Vista through Santa Barbara, Montecito, Summerland, Carpinteria.
BBOX = (34.385, -119.905, 34.475, -119.47)

QUERY = """
[out:json][timeout:120];
(
  nwr["name"]["amenity"~"^(restaurant|fast_food|ice_cream|food_court|cafe|bar|pub|biergarten|dentist|doctors|clinic|veterinary|car_wash|driving_school)$"]({bbox});
  nwr["name"]["shop"]({bbox});
  nwr["name"]["craft"]({bbox});
  nwr["name"]["leisure"~"^(fitness_centre|sports_centre|dance)$"]({bbox});
  nwr["name"]["healthcare"]({bbox});
  nwr["name"]["office"~"^(estate_agent|insurance|lawyer|accountant|architect|tax_advisor|financial|financial_advisor|property_management|moving_company)$"]({bbox});
);
out center tags;
"""

SOCIAL_KEYS = ("contact:facebook", "facebook", "contact:instagram", "instagram")


def fetch_raw(bbox=BBOX):
    url = os.environ.get("OVERPASS_URL") or "https://overpass-api.de/api/interpreter"
    q = QUERY.format(bbox=",".join(str(x) for x in bbox))
    print(f"[overpass] querying {url} ...")
    data = net.get_json(url, data=urllib.parse.urlencode({"data": q}), timeout=180,
                        headers={"Content-Type": "application/x-www-form-urlencoded"})
    return data.get("elements", [])


def format_phone(raw):
    if not raw:
        return None
    first = re.split(r"[;,]", raw)[0]
    digits = re.sub(r"\D", "", first)
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    if len(digits) == 10:
        return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"
    return first.strip()


def normalize_url(url):
    if not url:
        return None
    url = url.split(";")[0].strip()
    if not re.match(r"^https?://", url, re.I):
        url = "http://" + url
    return url


def guess_city(tags, lon):
    city = tags.get("addr:city")
    if city:
        return city.strip(), True
    # Rough longitude bands; flagged as approximate in provenance.
    if lon < -119.79:
        return "Goleta", False
    if lon > -119.56:
        return "Carpinteria", False
    if lon > -119.66:
        return "Montecito/Summerland", False
    return "Santa Barbara", False


def parse_year(value):
    m = re.search(r"\b(18|19|20)\d{2}\b", value or "")
    return int(m.group(0)) if m else None


def element_to_business(el, retrieved):
    tags = el.get("tags", {})
    cat, subtype = categorize(tags)
    if not cat or not (tags.get("name") or "").strip():
        return None
    lat = el.get("lat") or el.get("center", {}).get("lat")
    lon = el.get("lon") or el.get("center", {}).get("lon")
    if lat is None or lon is None:
        return None

    src = f"OpenStreetMap ({el['type']}/{el['id']})"
    prov = {}

    def put(field, value, source=src, status="sourced", note=None):
        if value in (None, ""):
            return None
        prov[field] = {"source": source, "status": status, "retrieved": retrieved}
        if note:
            prov[field]["note"] = note
        return value

    street = " ".join(p for p in (tags.get("addr:housenumber"), tags.get("addr:street")) if p)
    city, city_tagged = guess_city(tags, lon)
    address = ", ".join(p for p in (street, tags.get("addr:unit") and f"#{tags['addr:unit']}", city,
                                    "CA", tags.get("addr:postcode")) if p) if street else None
    website = normalize_url(tags.get("website") or tags.get("contact:website") or tags.get("url"))
    social = next((normalize_url(tags[k]) for k in SOCIAL_KEYS if tags.get(k)), None)
    founded = parse_year(tags.get("start_date"))

    b = {
        "id": f"osm-{el['type']}-{el['id']}",
        "name": put("name", tags["name"].strip()),
        "category": put("category", cat, note="Mapped from OSM tags"),
        "category_label": CATEGORIES[cat],
        "subtype": pretty(subtype),
        "lat": lat,
        "lon": lon,
        "city": put("city", city, status="sourced" if city_tagged else "estimated",
                    note=None if city_tagged else "No addr:city tag; area guessed from map position"),
        "address": put("address", address),
        "phone": put("phone", format_phone(tags.get("phone") or tags.get("contact:phone"))),
        "website": put("website", website),
        "social_url": put("social_url", social),
        "email": put("email", tags.get("email") or tags.get("contact:email")),
        "opening_hours": put("opening_hours", tags.get("opening_hours")),
        "owner_name": None,
        "year_founded": put("year_founded", founded, note=f"OSM start_date tag: {tags.get('start_date')}") if founded else None,
        "employees": None,
        "chain": bool(tags.get("brand") or tags.get("brand:wikidata")),
        "brand": tags.get("brand"),
        "provenance": prov,
    }
    return b


def collect(retrieved, path=None):
    """Query Overpass, or parse a saved Overpass JSON export (e.g. from overpass-turbo.eu) if `path` is given."""
    if path:
        with open(path, encoding="utf-8") as f:
            elements = json.load(f).get("elements", [])
    else:
        elements = fetch_raw()
    out, seen = [], set()
    for el in elements:
        b = element_to_business(el, retrieved)
        if not b:
            continue
        key = (b["name"].lower(), round(b["lat"], 3), round(b["lon"], 3))
        if key in seen:
            continue
        seen.add(key)
        out.append(b)
    print(f"[overpass] {len(elements)} raw elements -> {len(out)} target businesses")
    return out
