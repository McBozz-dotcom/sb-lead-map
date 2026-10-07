"""Merge facts you look up yourself (calls, visits, LinkedIn, county records) from data/manual_enrichment.csv."""
import csv
import os

from .net import ROOT

PATH = os.path.join(ROOT, "data", "manual_enrichment.csv")
COLUMNS = ["id", "name", "owner_name", "year_founded", "employees", "revenue_usd", "phone", "website", "source", "notes"]


def ensure_template():
    """Create an empty CSV with the right headers so it's easy to start filling in."""
    if not os.path.exists(PATH):
        os.makedirs(os.path.dirname(PATH), exist_ok=True)
        with open(PATH, "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(COLUMNS)


def load():
    ensure_template()
    rows = {}
    with open(PATH, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            key = (row.get("id") or "").strip() or (row.get("name") or "").strip().lower()
            if key:
                rows[key] = row
    return rows


def apply(b, rows, retrieved):
    row = rows.get(b["id"]) or rows.get(b["name"].lower())
    if not row:
        return False
    src = "Manual: " + ((row.get("source") or "").strip() or "entered by you")
    for field in ("owner_name", "year_founded", "employees", "revenue_usd", "phone", "website"):
        val = (row.get(field) or "").strip()
        if not val:
            continue
        if field in ("year_founded", "employees", "revenue_usd"):
            try:
                val = int(float(val.replace(",", "").replace("$", "")))
            except ValueError:
                continue
        b[field] = val
        b["provenance"][field] = {"source": src, "status": "manual", "retrieved": retrieved}
    if (row.get("notes") or "").strip():
        b["research_notes"] = row["notes"].strip()
    return True
