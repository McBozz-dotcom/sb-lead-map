"""Clearly-labeled revenue estimates. Never invents a number without a basis."""
import json
import os

_PATH = os.path.join(os.path.dirname(__file__), "benchmarks.json")


def load_benchmarks():
    with open(_PATH, encoding="utf-8") as f:
        return json.load(f)


def _round(x):
    step = 10_000 if x < 1_000_000 else 50_000
    return int(round(x / step) * step)


def estimate_revenue(business, bench=None):
    """Fill revenue fields on `business` in place.

    Order of preference:
      1. A revenue figure you entered yourself (manual CSV) -> shown as-is with your source.
      2. Employee count x industry revenue-per-employee -> 'Est.' range with the math shown.
      3. Nothing to go on -> left Unknown.
    """
    bench = bench or load_benchmarks()
    prov = business.setdefault("provenance", {})
    if business.get("revenue_usd"):
        business["revenue_low"] = business["revenue_high"] = business["revenue_usd"]
        return
    emp = business.get("employees")
    row = bench["categories"].get(business.get("category"))
    if not emp or not row:
        business["revenue_low"] = business["revenue_high"] = None
        return
    spread = bench.get("_spread", 0.3)
    mid = emp * row["revenue_per_employee"]
    business["revenue_low"] = _round(mid * (1 - spread))
    business["revenue_high"] = _round(mid * (1 + spread))
    prov["revenue"] = {
        "source": "Estimate",
        "status": "estimated",
        "note": (f"{emp} employees ({prov.get('employees', {}).get('source', 'unknown source')}) x "
                 f"~${row['revenue_per_employee']:,}/employee (U.S. avg for {row['naics']}, Census), "
                 f"±{int(spread * 100)}%. Not reported by the business."),
    }
