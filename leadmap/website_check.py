"""Grade each business's website so 'no website' / 'weak website' leads stand out.

Polite by design: honors robots.txt, identifies itself, fetches only the homepage
(first 300 KB), and waits between requests.
"""
import datetime
import re
import urllib.parse
import urllib.robotparser

from . import net

SOCIAL_HOSTS = ("facebook.com", "fb.com", "instagram.com", "yelp.com", "linktr.ee", "tiktok.com", "twitter.com", "x.com")
FREE_BUILDER_HOSTS = ("wixsite.com", "business.site", "square.site", "godaddysites.com", "weebly.com",
                      "wordpress.com", "blogspot.com", "carrd.co", "webnode.com", "jimdosite.com", "site123.me")

_limiter = net.RateLimiter(1.0)
_robots_cache = {}


def _host(url):
    return (urllib.parse.urlparse(url).hostname or "").lower()


def _matches(host, domains):
    return any(host == d or host.endswith("." + d) for d in domains)


def _robots_allows(url):
    parts = urllib.parse.urlparse(url)
    base = f"{parts.scheme}://{parts.netloc}"
    if base not in _robots_cache:
        rp = urllib.robotparser.RobotFileParser()
        try:
            status, _, _, body, _ = net.request(base + "/robots.txt", timeout=10, max_bytes=100_000)
            rp.parse(body.decode("utf-8", "replace").splitlines() if status < 400 else [])
        except Exception:
            rp.parse([])  # robots.txt unreachable -> treat as allowed, the page fetch will tell us more
        _robots_cache[base] = rp
    return _robots_cache[base].can_fetch(net.user_agent(), url)


def analyze_html(html, final_url, elapsed, this_year=None):
    """Pure function: return list of issue strings for a fetched homepage."""
    this_year = this_year or datetime.date.today().year
    issues = []
    if not final_url.lower().startswith("https://"):
        issues.append("No HTTPS")
    if not re.search(r'<meta[^>]+name=["\']?viewport', html, re.I):
        issues.append("Not mobile-friendly (no viewport tag)")
    years = [int(y) for y in re.findall(r"(?:©|&copy;|copyright)\s*(?:\d{4}\s*[-–]\s*)?((?:19|20)\d{2})", html, re.I)]
    if years and max(years) <= this_year - 3:
        issues.append(f"Outdated (latest © {max(years)})")
    if elapsed > 4:
        issues.append(f"Slow ({elapsed:.1f}s to load)")
    if len(re.sub(r"<[^>]+>", "", html).strip()) < 200:
        issues.append("Almost no content")
    return issues


def check(website, social_url=None):
    """Return dict(rating, issues, final_url, status). rating: none | weak | ok | unchecked."""
    if not website:
        return {"rating": "none", "issues": ["No website listed" + (" (social page only)" if social_url else "")]}
    host = _host(website)
    if _matches(host, SOCIAL_HOSTS):
        return {"rating": "weak", "issues": ["Social media page used as website"]}
    issues = []
    if _matches(host, FREE_BUILDER_HOSTS):
        issues.append("Free site-builder subdomain")
    try:
        if not _robots_allows(website):
            return {"rating": "unchecked", "issues": issues + ["Not checked (robots.txt disallows)"]}
        _limiter.wait()
        status, final_url, headers, body, elapsed = net.request(website, timeout=15, max_bytes=300_000,
                                                               headers={"Accept": "text/html"})
    except Exception as e:  # DNS failure, timeout, TLS error...
        return {"rating": "weak", "issues": issues + [f"Website unreachable ({type(e).__name__})"]}
    if status >= 400:
        return {"rating": "weak", "issues": issues + [f"Website returns HTTP {status}"]}
    if _matches(_host(final_url), SOCIAL_HOSTS):
        issues.append("Redirects to a social media page")
    html = body.decode("utf-8", "replace")
    issues += analyze_html(html, final_url, elapsed)
    return {"rating": "weak" if issues else "ok", "issues": issues, "final_url": final_url, "status": status}
