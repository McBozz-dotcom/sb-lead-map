"""Optional: look up registration date / agent in the California Secretary of State
business search API (the official API behind bizfile Online).

Get a free subscription key at https://calicodev.sos.ca.gov/ (sign up -> subscribe to the
"BE Public Search" product). Put it in .env as CA_SOS_API_KEY.

Important limits, so nothing gets over-claimed:
  * Only corporations, LLCs and LPs are registered with the SOS. Sole proprietors and
    most "DBA" names are filed with the Santa Barbara County Clerk instead (no API).
  * We only accept an exact (normalized) name match with exactly one active entity.
    Many storefront names differ from the legal entity name, so most lookups will
    come back empty -- that's expected and is shown as "Unknown".
  * The registered agent is NOT necessarily the owner. It is stored separately and
    never copied into owner_name.
  * Registration date is when the legal entity was formed in (or registered to do
    business in) California; the business itself may be older.

The exact response shape of this API wasn't available when this was written, so the
parser looks for fields by name and `--debug-sos` prints raw responses. If it parses
nothing for you, run with --debug-sos and adjust FIELD_HINTS.
"""
import json
import os
import re
import urllib.parse

from . import net

DEFAULT_BASE = "https://calico.sos.ca.gov/cbc/v1/api"
SUFFIXES = r"\b(llc|l\.l\.c|inc|incorporated|corp|corporation|co|company|ltd|lp|llp|pc|dds|a professional corporation)\b"
FIELD_HINTS = {
    "name": ("entityname", "name"),
    "number": ("entitynumber", "entityid", "number"),
    "status": ("entitystatus", "status"),
    "date": ("registrationdate", "formationdate", "initialfilingdate", "filedate", "registrationdt"),
    "agent": ("agentname", "agent"),
    "officers": ("principals", "officers", "officer"),
}
_limiter = net.RateLimiter(1.0)
DEBUG = False


def enabled():
    return bool(os.environ.get("CA_SOS_API_KEY"))


def norm_name(s):
    s = (s or "").lower().replace("&", " and ")
    s = re.sub(SUFFIXES, " ", s)
    return re.sub(r"[^a-z0-9]", "", s)


def _find(d, kind):
    """Case/format-insensitive key lookup on a dict."""
    flat = {re.sub(r"[^a-z]", "", k.lower()): v for k, v in d.items()}
    for hint in FIELD_HINTS[kind]:
        if hint in flat and flat[hint] not in (None, "", []):
            return flat[hint]
    return None


def _records(payload):
    if isinstance(payload, list):
        return [r for r in payload if isinstance(r, dict)]
    if isinstance(payload, dict):
        for v in payload.values():
            if isinstance(v, list) and v and isinstance(v[0], dict):
                return v
    return []


def _get(path, params):
    base = os.environ.get("CA_SOS_API_BASE") or DEFAULT_BASE
    url = f"{base}/{path}?{urllib.parse.urlencode(params)}"
    _limiter.wait()
    status, _, _, body, _ = net.request(url, headers={"Ocp-Apim-Subscription-Key": os.environ["CA_SOS_API_KEY"]})
    if DEBUG:
        print(f"[ca_sos] GET {url} -> {status}\n{body[:1500].decode('utf-8', 'replace')}")
    if status == 404:
        return None
    if status >= 400:
        raise RuntimeError(f"CA SOS HTTP {status}: {body[:200]!r}")
    return json.loads(body)


def enrich(b, retrieved):
    """Returns True if a confident match was found and fields were filled."""
    payload = _get("BusinessEntityKeywordSearch", {"search-term": b["name"]})
    target = norm_name(b["name"])
    hits = []
    for r in _records(payload):
        if norm_name(str(_find(r, "name") or "")) != target:
            continue
        status = str(_find(r, "status") or "").lower()
        if status and "active" not in status:
            continue
        hits.append(r)
    if len(hits) != 1:
        return False  # none, or ambiguous -> leave Unknown rather than guess
    r = hits[0]
    num = _find(r, "number")
    src = f"CA Secretary of State (entity #{num})" if num else "CA Secretary of State"
    prov = b["provenance"]
    b["legal_entity"] = _find(r, "name")
    prov["legal_entity"] = {"source": src, "status": "sourced", "retrieved": retrieved,
                            "note": "Matched on exact normalized name; verify it's the same business."}
    m = re.search(r"(18|19|20)\d{2}", str(_find(r, "date") or ""))
    if m and not b.get("year_founded"):
        b["year_founded"] = int(m.group(0))
        prov["year_founded"] = {"source": src, "status": "sourced", "retrieved": retrieved,
                                "note": f"Entity registration date {_find(r, 'date')}; business may be older."}
    agent = _find(r, "agent")
    if isinstance(agent, (dict, list)):
        agent = json.dumps(agent)
    if agent:
        b["registered_agent"] = agent
        prov["registered_agent"] = {"source": src, "status": "sourced", "retrieved": retrieved,
                                    "note": "Agent for service of process - not necessarily the owner."}
    officers = _find(r, "officers")
    if officers and not b.get("owner_name"):
        names = officers if isinstance(officers, list) else [officers]
        text = "; ".join(str(_find(o, "name") or o) if isinstance(o, dict) else str(o) for o in names)
        b["owner_name"] = text
        prov["owner_name"] = {"source": src, "status": "sourced", "retrieved": retrieved,
                              "note": "Officer/manager listed with the SOS (Statement of Information)."}
    return True
