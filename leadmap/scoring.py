"""'Wanted level' lead score (0-5 stars): higher = more likely to need web/marketing help."""


def score(b):
    stars, reasons = 0, []
    web = b.get("website_check", {}).get("rating") or (None if b.get("website") else "none")
    if web == "none":
        stars += 3
        reasons.append("No website")
    elif web == "weak":
        stars += 2
        reasons.append("Weak website")
    if not b.get("chain"):
        stars += 1
        reasons.append("Independent (not a chain)")
    if b.get("phone"):
        stars += 1
        reasons.append("Phone number available")
    if b.get("google_reviews") is not None and b["google_reviews"] < 25:
        stars += 1
        reasons.append("Few Google reviews")
    if b.get("chain"):
        stars = min(stars, 1)
    b["lead_score"] = min(stars, 5)
    b["lead_reasons"] = reasons
    return b["lead_score"]
